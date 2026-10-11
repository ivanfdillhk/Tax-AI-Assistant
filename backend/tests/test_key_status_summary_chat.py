"""Tests for new Tax AI features:
- GET /api/key-status
- POST /api/putusan/{id}/ai-summary (cache + refresh + 404 + no-asterisks)
- POST /api/chat SSE with model=gpt and model=gemini
"""
import json
import os
import re
import time
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except FileNotFoundError:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"
DOC_IDS = ["put-pph21-2023", "put-004106-2020"]


# ---------- /key-status ----------
def test_key_status_shape_and_no_leak():
    r = requests.get(f"{API}/key-status", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "search" in data and "assistant" in data
    assert data["search"]["env"] == "GEMINI_API_KEY"
    assert data["search"]["source"] in ("own", "emergent")
    for k in ("gpt", "gemini"):
        a = data["assistant"][k]
        assert a["source"] in ("own", "emergent")
        assert a["env"] in ("OPENAI_API_KEY", "GEMINI_API_KEY")
        assert a["label"]
    # with keys empty in backend/.env, both should be 'emergent'
    assert data["search"]["source"] == "emergent"
    assert data["assistant"]["gpt"]["source"] == "emergent"
    assert data["assistant"]["gemini"]["source"] == "emergent"
    # no key value leakage
    body = r.text
    for leak in ("sk-", "AIza", "EMERGENT_LLM_KEY"):
        # EMERGENT_LLM_KEY env name shouldn't appear either
        assert leak not in body, f"possible leak of {leak}"


# ---------- AI summary ----------
@pytest.mark.parametrize("model", ["gpt", "gemini"])
def test_ai_summary_generate_cache_refresh(model):
    doc_id = DOC_IDS[0]
    # fresh (refresh=true to invalidate any prior cache from previous test runs)
    r1 = requests.post(f"{API}/putusan/{doc_id}/ai-summary",
                       json={"model": model, "refresh": True}, timeout=120)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["cached"] is False
    assert d1["model"] == model
    assert d1["model_label"]
    assert d1["key_source"] in ("own", "emergent")
    s = d1["summary"]
    for key in ("pokok_sengketa", "amar_putusan", "pertimbangan_kunci", "dasar_hukum", "implikasi"):
        assert key in s
    assert isinstance(s["pertimbangan_kunci"], list)
    assert isinstance(s["dasar_hukum"], list)
    # no asterisks / markdown
    serialized = json.dumps(s, ensure_ascii=False)
    assert "*" not in serialized
    assert "#" not in serialized

    # second call should be cached
    r2 = requests.post(f"{API}/putusan/{doc_id}/ai-summary",
                       json={"model": model, "refresh": False}, timeout=30)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["cached"] is True
    assert d2["model"] == model
    assert d2["summary"] == s

    # refresh regenerates
    r3 = requests.post(f"{API}/putusan/{doc_id}/ai-summary",
                       json={"model": model, "refresh": True}, timeout=120)
    assert r3.status_code == 200
    assert r3.json()["cached"] is False


def test_ai_summary_404_unknown():
    r = requests.post(f"{API}/putusan/does-not-exist-xyz/ai-summary",
                      json={"model": "gpt", "refresh": False}, timeout=15)
    assert r.status_code == 404


# ---------- /chat SSE ----------
@pytest.mark.parametrize("model", ["gpt", "gemini"])
def test_chat_sse_stream(model):
    doc_id = DOC_IDS[1]
    payload = {"document_id": doc_id, "question": "Apa pokok sengketa putusan ini?", "model": model}
    with requests.post(f"{API}/chat", json=payload, stream=True, timeout=120) as r:
        assert r.status_code == 200, r.text
        assert "text/event-stream" in r.headers.get("content-type", "")
        tokens = []
        done = None
        started = time.time()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            if raw.startswith("data: "):
                evt = json.loads(raw[6:])
                if evt.get("type") == "token":
                    tokens.append(evt.get("content", ""))
                elif evt.get("type") == "done":
                    done = evt
                    break
            if time.time() - started > 90:
                break
    assert done is not None, "no done event received"
    assert "citations" in done and isinstance(done["citations"], list)
    assert len(tokens) > 0, "no token events streamed"
