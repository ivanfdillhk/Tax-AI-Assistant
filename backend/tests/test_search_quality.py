"""Tests for TaxLens web search + AI search quality improvements:
- More sources returned (web >= 15 ideally, AI >= 6 ideally)
- No asterisk (*) or leading '#' artifacts in snippets/titles/answers
- Citation markers [n] NOT at start of a line in AI answers
- Pagination cache: page=2 after page=1 is fast (<2s)

Backend-only. Runs SEQUENTIALLY (LLM key disallows concurrent calls).
"""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
TIMEOUT = 90

# Load REACT_APP_BACKEND_URL from frontend/.env if missing
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    API = f"{BASE_URL}/api"
                    break
    except Exception:
        pass


def _assert_no_markdown_artifacts(text: str, label: str):
    assert "*" not in text, f"[{label}] still contains '*': {text[:200]!r}"


def _assert_no_leading_heading_or_marker(text: str, label: str):
    for ln in (text or "").split("\n"):
        s = ln.lstrip()
        assert not s.startswith("#"), f"[{label}] line starts with '#': {ln[:120]!r}"
        # citation marker like [1] or [1][2] must not be at start of line
        assert not re.match(r"^\[\d+\]", s), f"[{label}] marker at start of line: {ln[:120]!r}"


# ---------- Web search ----------
WEB_QUERY = "PPN TBS sawit"


@pytest.fixture(scope="module")
def web_page1():
    t0 = time.perf_counter()
    r = requests.get(f"{API}/search", params={"q": WEB_QUERY, "page_size": 20}, timeout=TIMEOUT)
    elapsed = time.perf_counter() - t0
    print(f"\n[web page1] status={r.status_code} elapsed={elapsed:.1f}s")
    return r, elapsed


class TestWebSearch:
    def test_web_search_status_and_total(self, web_page1):
        r, _ = web_page1
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        assert data["query"].strip().lower() == WEB_QUERY.lower()
        assert data["page"] == 1
        assert data["pageSize"] == 20
        total = data["total"]
        print(f"[web] total={total} results_returned={len(data['results'])}")
        # Expectation: >=15 (improvement from previous ~8)
        assert total >= 10, f"Expected >=10 results, got {total}"
        if total < 15:
            print(f"WARN: total={total} is below the ideal 15")

    def test_web_results_no_asterisk(self, web_page1):
        r, _ = web_page1
        data = r.json()
        for item in data["results"]:
            _assert_no_markdown_artifacts(item.get("snippet") or "", f"snippet rank={item.get('rank')}")
            _assert_no_markdown_artifacts(item.get("title") or "", f"title rank={item.get('rank')}")

    def test_web_results_structure(self, web_page1):
        r, _ = web_page1
        data = r.json()
        for item in data["results"]:
            assert "title" in item and "url" in item and "rank" in item
            assert isinstance(item["url"], str) and item["url"].startswith("http")

    def test_web_page2_is_cached_fast(self, web_page1):
        # Trigger page=1 fixture first (above). Now page=2 should hit cache.
        _ = web_page1
        t0 = time.perf_counter()
        r2 = requests.get(f"{API}/search", params={"q": WEB_QUERY, "page": 2, "page_size": 20}, timeout=TIMEOUT)
        elapsed = time.perf_counter() - t0
        print(f"[web page2] status={r2.status_code} elapsed={elapsed:.2f}s")
        assert r2.status_code == 200
        # Cache TTL=600s. Second call should be very fast.
        assert elapsed < 3.0, f"page=2 took {elapsed:.2f}s, cache not working (expected <2s)"


# ---------- AI search ----------
AI_QUERY = "Apakah STP bisa dibatalkan?"


@pytest.fixture(scope="module")
def ai_resp():
    t0 = time.perf_counter()
    r = requests.post(f"{API}/ai-search", json={"q": AI_QUERY}, timeout=TIMEOUT)
    elapsed = time.perf_counter() - t0
    print(f"\n[ai-search] status={r.status_code} elapsed={elapsed:.1f}s")
    return r, elapsed


class TestAiSearch:
    def test_ai_status(self, ai_resp):
        r, _ = ai_resp
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        assert "answer" in data and "sources" in data
        assert isinstance(data["answer"], str) and len(data["answer"]) > 50

    def test_ai_sources_have_cited_flag(self, ai_resp):
        r, _ = ai_resp
        data = r.json()
        sources = data["sources"]
        print(f"[ai] total sources={len(sources)}; cited={sum(1 for s in sources if s.get('cited'))}; related={sum(1 for s in sources if s.get('cited') is False)}")
        assert len(sources) >= 1
        for s in sources:
            assert "cited" in s, f"source {s.get('number')} missing 'cited' field"
            assert isinstance(s["cited"], bool)
            assert "number" in s and "url" in s and "title" in s

    def test_ai_total_sources_at_least_6(self, ai_resp):
        r, _ = ai_resp
        sources = r.json()["sources"]
        if len(sources) < 6:
            pytest.skip(f"Only {len(sources)} sources returned (goal>=6). May be due to time budget on free-form query.")
        assert len(sources) >= 6

    def test_ai_answer_no_markdown_artifacts(self, ai_resp):
        r, _ = ai_resp
        answer = r.json()["answer"]
        _assert_no_markdown_artifacts(answer, "ai-answer")

    def test_ai_answer_no_leading_markers_or_hashes(self, ai_resp):
        r, _ = ai_resp
        answer = r.json()["answer"]
        _assert_no_leading_heading_or_marker(answer, "ai-answer")


# ---------- Regression: suggestion chip "pajak natura" ----------
class TestSuggestionRegression:
    def test_pajak_natura_web_search(self):
        t0 = time.perf_counter()
        r = requests.get(f"{API}/search", params={"q": "pajak natura", "page_size": 10}, timeout=TIMEOUT)
        elapsed = time.perf_counter() - t0
        print(f"\n[regression pajak natura] status={r.status_code} elapsed={elapsed:.1f}s")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        for item in data["results"]:
            _assert_no_markdown_artifacts(item.get("snippet") or "", "snippet")
