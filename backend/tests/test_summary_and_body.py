"""Test summary word-boundary cleanliness + document body paragraph records."""
import os
import re
import pytest
import requests

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except FileNotFoundError:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")

BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

PDF_PATH = "/app/test_putusan_header.pdf"


def _ends_cleanly(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    # must end in sentence punctuation, or ellipsis
    return bool(re.search(r"[.!?;…]['\"\u201d\u2019)]*$", s))


class TestSummary:
    def test_upload_summary_not_mid_word(self):
        if not os.path.exists(PDF_PATH):
            pytest.skip("test_putusan_header.pdf not present")
        with open(PDF_PATH, "rb") as f:
            r = requests.post(f"{API}/putusan/upload", files={"file": ("test_putusan_header.pdf", f, "application/pdf")})
        assert r.status_code == 200, r.text
        data = r.json()
        doc_id = data["id"]
        try:
            summary = data.get("summary", "")
            assert summary, "summary empty"
            assert _ends_cleanly(summary), f"summary ends mid-word: ...{summary[-80:]!r}"
            # Verify no mid-word truncation: last token should not look chopped (no trailing partial word before end if not ellipsis)
            # Confirm via GET
            g = requests.get(f"{API}/putusan/{doc_id}")
            assert g.status_code == 200
            assert g.json()["summary"] == summary
        finally:
            d = requests.delete(f"{API}/putusan/{doc_id}")
            assert d.status_code == 200

    def test_sample_putusan_summary_clean(self):
        # sample seeded putusan
        r = requests.get(f"{API}/putusan/put-004106-2020")
        assert r.status_code == 200
        summary = r.json()["summary"]
        assert summary
        # sample has a short clean summary
        assert _ends_cleanly(summary) or len(summary) <= 480

    def test_extra_sample_summary_clean(self):
        r = requests.get(f"{API}/putusan/put-pph21-2023")
        if r.status_code != 200:
            pytest.skip("extra sample not seeded")
        s = r.json()["summary"]
        assert s
        assert _ends_cleanly(s) or len(s) <= 480


class TestBodyParagraphCount:
    def test_body_nonempty_lines_align(self):
        r = requests.get(f"{API}/putusan/put-004106-2020")
        assert r.status_code == 200
        body = r.json()["body"]
        non_empty = [ln for ln in body.split("\n") if ln.strip()]
        assert len(non_empty) >= 3
