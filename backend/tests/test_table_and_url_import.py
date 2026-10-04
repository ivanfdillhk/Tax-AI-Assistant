"""Tests for PDF table extraction and import-url with direct PDF URLs."""
import os
import re
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"


def test_upload_pdf_with_table():
    """Upload /app/test_table.pdf and verify [TABLE] block in response body."""
    with open("/app/test_table.pdf", "rb") as f:
        r = requests.post(f"{API}/putusan/upload", files={"file": ("test_table.pdf", f, "application/pdf")}, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()["body"]
    assert "[TABLE]" in body, f"No [TABLE] marker in body: {body[:500]}"
    assert "[/TABLE]" in body
    # Extract first table block
    m = re.search(r"\[TABLE\]\s*\n([\s\S]*?)\n\s*\[/TABLE\]", body)
    assert m, "Table block regex did not match"
    rows = m.group(1).split("\n")
    assert len(rows) >= 4, f"Expected header + 3 data rows, got {len(rows)}: {rows}"
    header = rows[0].split("\t")
    expected_headers = ["Pos", "Nilai Semula", "Koreksi", "Nilai Setelah"]
    for h in expected_headers:
        assert any(h in cell for cell in header), f"Missing header {h} in {header}"
    data_text = "\n".join(rows[1:])
    for label in ["DPP PPN", "PPN Keluaran", "Pajak Masukan"]:
        assert label in data_text, f"Missing data row '{label}' in {data_text}"


def test_import_url_direct_pdf():
    """Import a direct PDF URL via /putusan/import-url."""
    pdf_urls = [
        "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
        "https://www.africau.edu/images/default/sample.pdf",
    ]
    last_err = None
    for url in pdf_urls:
        try:
            r = requests.post(f"{API}/putusan/import-url", json={"url": url, "kind": "putusan"}, timeout=60)
            if r.status_code == 200:
                data = r.json()
                body = data["body"]
                # Dummy PDF content check for first URL
                if "dummy.pdf" in url:
                    assert "Dummy PDF" in body or "dummy" in body.lower(), f"Content missing: {body[:300]}"
                    assert data["title"].lower().startswith("dummy"), f"Title not derived from filename: {data['title']}"
                else:
                    assert len(body.strip()) > 20
                return
            else:
                last_err = f"{url} -> {r.status_code} {r.text[:200]}"
        except Exception as e:
            last_err = f"{url} -> {e}"
    pytest.fail(f"All PDF URLs failed. Last: {last_err}")


def test_import_url_html_still_works():
    """HTML URL import should still work (regression)."""
    r = requests.post(f"{API}/putusan/import-url", json={"url": "https://example.com", "kind": "putusan"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()["body"]
    assert "Example Domain" in body or len(body.strip()) > 20


def test_health_regression():
    """Basic health check."""
    r = requests.get(f"{API}/putusan", timeout=20)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
