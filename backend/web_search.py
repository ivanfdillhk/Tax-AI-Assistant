"""Real-time web search + AI search powered by Gemini Google Search grounding.

Uses the EMERGENT_LLM_KEY via emergentintegrations. Gemini performs an actual
Google Search and returns grounding citations (real source URLs). We extract
those citations, resolve the Google grounding-redirect URLs to the real final
URLs, and shape them into Google-like search results. No URLs are fabricated.
"""
import os
import re
import uuid
import asyncio
import time
import logging
from urllib.parse import urlparse

import httpx
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("web_search")

GEMINI_MODEL = "gemini-2.5-flash"

# Priority (not a filter) — tax/government sources ranked first when present.
PRIORITY_DOMAINS = [
    "pajak.go.id",
    "jdih.kemenkeu.go.id",
    "peraturan.bpk.go.id",
    "mahkamahagung.go.id",
    "setpp.kemenkeu.go.id",
    "kemenkeu.go.id",
    "peraturan.go.id",
]

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _clean_domain(url: str) -> str:
    try:
        net = urlparse(url).netloc.lower()
        return net[4:] if net.startswith("www.") else net
    except Exception:
        return ""


def _favicon(domain: str) -> str:
    if not domain:
        return ""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"


def _priority_rank(domain: str) -> int:
    for idx, dom in enumerate(PRIORITY_DOMAINS):
        if domain == dom or domain.endswith("." + dom):
            return idx
    return len(PRIORITY_DOMAINS) + 1


_BAD_TITLE_RE = re.compile(
    r"^(just a moment|attention required|access denied|error|forbidden|403|404|"
    r"page not found|are you a robot|checking your browser|loading|client challenge|"
    r"one moment|please wait|security check|bot verification)\b",
    re.I,
)


def _good_title(title: str) -> bool:
    t = (title or "").strip()
    if not t or len(t) < 3:
        return False
    if _BAD_TITLE_RE.search(t):
        return False
    return True


_PLAIN_RULE = (
    " Tulis dalam teks biasa TANPA format markdown: jangan gunakan tanda bintang (*), "
    "garis bawah ganda, atau tanda pagar (#). Untuk daftar gunakan simbol '•' di awal baris."
)


def clean_markdown(text: str) -> str:
    """Strip markdown artefacts (asterisks, headings, backticks) from LLM text."""
    if not text:
        return ""
    t = text.replace("\r\n", "\n")
    t = re.sub(r"`+", "", t)
    t = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]*", "", t)
    t = re.sub(r"(?m)^([ \t]*)[*+\-][ \t]+", r"\1• ", t)
    t = t.replace("**", "").replace("__", "")
    t = t.replace("*", "")
    t = re.sub(r"•[ \t]+", "• ", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


_CACHE = {}
_CACHE_TTL = 600  # seconds
_CACHE_MAX = 100


def _cache_get(key):
    hit = _CACHE.get(key)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]
    _CACHE.pop(key, None)
    return None


def _cache_set(key, value):
    if len(_CACHE) >= _CACHE_MAX:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
        _CACHE.pop(oldest, None)
    _CACHE[key] = (time.time(), value)


async def _grounded_call(system_message: str, user_text: str, session_prefix: str):
    """Call Gemini with Google Search grounding. Returns (content, annotations)."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")
    chat = (
        LlmChat(api_key=key, session_id=f"{session_prefix}-{uuid.uuid4()}", system_message=system_message)
        .with_model("gemini", GEMINI_MODEL)
        .with_tools([{"googleSearch": {}}])
    )
    resp = None
    for attempt in range(3):
        try:
            resp = await chat.send_message_with_tools(UserMessage(text=user_text))
            break
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if attempt < 2 and ("concurrent" in msg or "429" in msg) and "budget" not in msg:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            raise
    content = resp.content or ""
    raw = resp.raw
    try:
        data = raw if isinstance(raw, dict) else raw.model_dump()
    except Exception:
        try:
            data = raw.dict()
        except Exception:
            data = {}
    annotations = []
    try:
        annotations = data["choices"][0].get("message", {}).get("annotations") or []
    except Exception:
        annotations = []
    return content, annotations


# The LLM key plan may not allow parallel requests, so supplementary calls run
# sequentially within a total time budget (keeps us under the ~60s gateway timeout).
SEARCH_TIME_BUDGET = 32.0
MIN_CALL_WINDOW = 9.0


async def _sequential_calls(specs, budget: float = SEARCH_TIME_BUDGET):
    """specs: list of (system, user_text, prefix). First call is mandatory (errors raise);
    later calls run only while time budget remains, failures are skipped."""
    started = time.perf_counter()
    results = []
    for idx, (system, user_text, prefix) in enumerate(specs):
        if idx == 0:
            results.append(await _grounded_call(system, user_text, prefix))
            continue
        remaining = budget - (time.perf_counter() - started)
        if remaining < MIN_CALL_WINDOW:
            logger.info("search budget exhausted; skipped %d supplementary call(s)", len(specs) - idx)
            break
        try:
            results.append(await asyncio.wait_for(_grounded_call(system, user_text, prefix), timeout=remaining))
        except Exception as exc:  # noqa: BLE001
            logger.info("supplementary search call skipped: %s", str(exc)[:200])
    return results


def _fix_marker_positions(text: str) -> str:
    """Move citation markers that landed at the start of a line back to the end of the previous line."""
    if not text:
        return text
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\n([ \t]*(?:•[ \t]*)?)((?:\[\d+\])+)", r"\2\n\1", text)
    return text


def _ordered_unique_citations(annotations):
    """Return list of dicts {url, title, snippet, start, end} unique by url,
    ordered by first appearance (start_index)."""
    items = []
    for a in annotations:
        if a.get("type") != "url_citation":
            continue
        uc = a.get("url_citation") or {}
        url = uc.get("url")
        if not url:
            continue
        items.append(
            {
                "url": url,
                "title": (uc.get("title") or "").strip(),
                "start": uc.get("start_index") or 0,
                "end": uc.get("end_index") or 0,
            }
        )
    items.sort(key=lambda x: x["start"])
    seen = {}
    ordered = []
    for it in items:
        if it["url"] in seen:
            continue
        seen[it["url"]] = True
        ordered.append(it)
    return ordered


async def _resolve_one(cx: httpx.AsyncClient, url: str):
    """Follow the grounding redirect to the real URL and grab the page <title>.
    Reads only the first chunk of the body to stay fast."""
    final_url = url
    page_title = None
    try:
        async with cx.stream("GET", url, follow_redirects=True, headers={"User-Agent": _UA}) as r:
            final_url = str(r.url)
            ctype = r.headers.get("content-type", "")
            if "text/html" in ctype:
                collected = b""
                async for chunk in r.aiter_bytes():
                    collected += chunk
                    if len(collected) > 40000:
                        break
                html = collected.decode("utf-8", errors="ignore")
                m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                if m:
                    page_title = re.sub(r"\s+", " ", m.group(1)).strip()[:180]
    except Exception as exc:  # noqa: BLE001
        logger.info("resolve failed for %s: %s", url[:60], exc)
    return url, final_url, page_title


async def _resolve_all(redirect_urls):
    resolved = {}
    if not redirect_urls:
        return resolved
    async with httpx.AsyncClient(timeout=httpx.Timeout(9.0, connect=5.0), follow_redirects=True) as cx:
        tasks = [_resolve_one(cx, u) for u in redirect_urls]
        for coro in asyncio.as_completed(tasks):
            try:
                orig, final, title = await coro
                resolved[orig] = (final, title)
            except Exception:  # noqa: BLE001
                continue
    return resolved


def _snippet_from_content(content: str, start: int, end: int, fallback: str = "") -> str:
    try:
        if content and 0 <= start < end <= len(content):
            seg = clean_markdown(content[start:end]).replace("•", "").strip()
            seg = re.sub(r"\s+", " ", seg)
            if len(seg) > 320:
                seg = seg[:317].rstrip() + "…"
            if seg:
                return seg
    except Exception:
        pass
    return fallback


def _resolve_display(final_url: str, ann_title: str):
    """Return (domain, display_url) handling unresolved grounding redirects."""
    domain = _clean_domain(final_url)
    if not domain or domain.endswith("vertexaisearch.cloud.google.com"):
        domain = ann_title or domain
        display = ann_title or final_url
    else:
        display = final_url
    return domain, display


def _build_results(content, citations, resolved, apply_priority=True):
    results = []
    seen_final = set()
    for rank0, c in enumerate(citations):
        final_url, page_title = resolved.get(c["url"], (c["url"], None))
        if final_url in seen_final:
            continue
        seen_final.add(final_url)
        domain, display = _resolve_display(final_url, c["title"])
        if _good_title(page_title):
            title = page_title
        elif c["title"]:
            title = c["title"]
        else:
            title = domain or "Tautan"
        snippet = _snippet_from_content(content, c["start"], c["end"], fallback="")
        results.append(
            {
                "title": title,
                "url": final_url,
                "displayUrl": display,
                "snippet": snippet,
                "source": domain,
                "favicon": _favicon(domain),
                "_order": rank0,
            }
        )
    if apply_priority:
        results.sort(key=lambda r: (_priority_rank(r["source"]), r["_order"]))
    for i, r in enumerate(results):
        r["rank"] = i + 1
        r.pop("_order", None)
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def web_search(query: str, kind: str = "web"):
    """Perform a real web search. kind in {web, news, pdf}.
    Returns the full (unpaginated) list of real results."""
    if kind == "news":
        system = (
            "Anda adalah mesin pencari berita TaxLens. Gunakan Google Search untuk menemukan "
            "artikel berita TERBARU dan relevan untuk kueri pengguna. Utamakan sumber berita "
            "tepercaya. Untuk setiap artikel, tulis satu kalimat ringkas tentang isinya dan SITASI sumbernya. "
            "Sertakan sebanyak mungkin artikel berbeda (minimal 10 bila tersedia). Jangan mengarang URL."
        )
        user = f"Berita terbaru tentang: {query}"
    elif kind == "pdf":
        system = (
            "Anda adalah mesin pencari dokumen TaxLens. Gunakan Google Search untuk menemukan DOKUMEN "
            "resmi (PDF) seperti peraturan, putusan, surat edaran, atau makalah yang relevan dengan kueri. "
            "Utamakan sumber resmi pemerintah Indonesia bila kueri terkait pajak, namun jangan membatasi. "
            "Untuk setiap dokumen, tulis satu kalimat ringkas tentang isinya dan SITASI sumbernya (URL dokumen). "
            "Sertakan sebanyak mungkin dokumen berbeda. Jangan mengarang URL."
        )
        user = f"Dokumen PDF resmi tentang: {query}"
    else:
        system = (
            "Anda adalah mesin pencari web TaxLens, sebuah search engine nyata. Gunakan Google Search "
            "untuk menemukan halaman web paling relevan, otoritatif, dan masih aktif untuk kueri pengguna. "
            "Jika kueri terkait pajak Indonesia, utamakan sumber resmi (pajak.go.id, jdih.kemenkeu.go.id, "
            "peraturan.bpk.go.id, mahkamahagung.go.id) — tetapi JANGAN membatasi hanya ke situs itu; "
            "sertakan juga berita, jurnal, konsultan, perusahaan, dan situs umum yang relevan. "
            "Untuk SETIAP halaman relevan, tulis satu kalimat ringkas tentang isinya dan SITASI sumbernya. "
            "Sertakan minimal 15 sumber berbeda bila tersedia. Jangan pernah mengarang URL."
        )
        user = query

    if kind == "news":
        users = [user, f"Perkembangan dan analisis terkini seputar: {query}"]
    elif kind == "pdf":
        users = [user, f"{query} filetype:pdf dokumen resmi atau makalah"]
    else:
        users = [
            user,
            f"{query} — peraturan resmi, penjelasan otoritas, dan putusan terkait",
            f"{query} — artikel, berita, analisis konsultan, dan pembahasan praktis",
        ]

    cache_key = (kind, query.strip().lower())
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    ok = await _sequential_calls([(system + _PLAIN_RULE, u, "tlx-web") for u in users])

    per_call = [(content, _ordered_unique_citations(ann)) for content, ann in ok]
    resolved = await _resolve_all([c["url"] for _, cits in per_call for c in cits])

    merged = []
    seen_final = set()
    for call_idx, (content, cits) in enumerate(per_call):
        for r in _build_results(content, cits, resolved, apply_priority=False):
            if r["url"] in seen_final:
                continue
            seen_final.add(r["url"])
            r["_key"] = (r["rank"], call_idx)
            merged.append(r)
    merged.sort(key=lambda r: (_priority_rank(r["source"]), r["_key"]))
    for i, r in enumerate(merged):
        r["rank"] = i + 1
        r.pop("_key", None)

    data = {"overview": clean_markdown(ok[0][0]), "results": merged}
    if merged:
        _cache_set(cache_key, data)
    return data


async def ai_search(question: str):
    """Answer a question using Gemini grounded on real web sources.
    Returns answer with inline [n] citation markers + numbered sources."""
    system = (
        "Anda adalah TaxLens AI, asisten riset yang menjawab berdasarkan hasil pencarian web nyata. "
        "Gunakan Google Search untuk menemukan sumber yang relevan dan tepercaya. Jawab dalam Bahasa "
        "Indonesia secara jelas dan ringkas. Setiap klaim penting WAJIB bersumber pada hasil pencarian. "
        "Jika kueri terkait pajak Indonesia, utamakan sumber resmi (pajak.go.id, jdih.kemenkeu.go.id, "
        "peraturan.bpk.go.id, mahkamahagung.go.id), namun jangan membatasi. Jangan mengarang fakta atau URL. "
        "Jika informasi tidak ditemukan, katakan dengan jujur."
    ) + _PLAIN_RULE
    extra_system = (
        "Anda adalah mesin pencari sumber TaxLens. Gunakan Google Search untuk menemukan sebanyak "
        "mungkin halaman berbeda yang relevan dan tepercaya untuk pertanyaan pengguna (minimal 8 bila tersedia): "
        "peraturan resmi, situs pemerintah, artikel, berita, dan analisis konsultan. Untuk setiap halaman "
        "tulis satu kalimat ringkas dan SITASI sumbernya. Jangan mengarang URL."
    ) + _PLAIN_RULE
    calls = await _sequential_calls([
        (system, question, "tlx-ai"),
        (extra_system, question, "tlx-ai-src"),
        (extra_system, f"{question} — dasar hukum dan peraturan resmi terkait", "tlx-ai-src"),
    ])
    content, annotations = calls[0]
    extra_citations = []
    for c in calls[1:]:
        extra_citations.extend(_ordered_unique_citations(c[1]))
    citations = _ordered_unique_citations(annotations)
    resolved = await _resolve_all([c["url"] for c in citations] + [c["url"] for c in extra_citations])

    # Map each redirect url -> final url, then number by unique FINAL url (first appearance)
    redirect_to_final = {c["url"]: resolved.get(c["url"], (c["url"], None))[0] for c in citations}
    final_to_num = {}
    sources = []
    for c in citations:
        final_url, page_title = resolved.get(c["url"], (c["url"], None))
        if final_url in final_to_num:
            continue
        num = len(final_to_num) + 1
        final_to_num[final_url] = num
        domain, display = _resolve_display(final_url, c["title"])
        if _good_title(page_title):
            title = page_title
        elif c["title"]:
            title = c["title"]
        else:
            title = domain or "Sumber"
        sources.append(
            {
                "number": num,
                "title": title,
                "url": final_url,
                "displayUrl": display,
                "source": domain,
                "favicon": _favicon(domain),
                "cited": True,
            }
        )

    # Supplementary (related) sources, numbered after the cited ones
    for c in extra_citations:
        final_url, page_title = resolved.get(c["url"], (c["url"], None))
        if final_url in final_to_num:
            continue
        num = len(final_to_num) + 1
        final_to_num[final_url] = num
        domain, display = _resolve_display(final_url, c["title"])
        if _good_title(page_title):
            title = page_title
        elif c["title"]:
            title = c["title"]
        else:
            title = domain or "Sumber"
        sources.append(
            {
                "number": num,
                "title": title,
                "url": final_url,
                "displayUrl": display,
                "source": domain,
                "favicon": _favicon(domain),
                "cited": False,
            }
        )

    # Insert inline [n] markers at end_index positions (descending to keep offsets valid)
    markers = {}
    for a in annotations:
        if a.get("type") != "url_citation":
            continue
        uc = a.get("url_citation") or {}
        url = uc.get("url")
        if not url or url not in redirect_to_final:
            continue
        num = final_to_num.get(redirect_to_final[url])
        if not num:
            continue
        end = min(uc.get("end_index") or 0, len(content))
        markers.setdefault(end, [])
        if num not in markers[end]:
            markers[end].append(num)

    answer = content
    for end in sorted(markers, reverse=True):
        tag = "".join(f"[{n}]" for n in sorted(markers[end]))
        answer = answer[:end] + tag + answer[end:]

    return {"answer": _fix_marker_positions(clean_markdown(answer)), "sources": sources}
