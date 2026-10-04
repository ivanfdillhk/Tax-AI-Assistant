"""Test smart title + metadata detection on upload/import."""
import os
import io
import pytest
import requests

def _load_backend_url():
    url = os.environ.get('REACT_APP_BACKEND_URL')
    if not url:
        env_path = '/app/frontend/.env'
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith('REACT_APP_BACKEND_URL='):
                    url = line.split('=', 1)[1].strip()
                    break
    if not url:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return url.rstrip('/')

BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    return s


# --- Upload: PDF with putusan header ---
def test_upload_putusan_header_pdf(session):
    with open("/app/test_putusan_header.pdf", "rb") as fh:
        r = session.post(f"{API}/putusan/upload",
                         files={"file": ("test_putusan_header.pdf", fh, "application/pdf")})
    assert r.status_code == 200, r.text
    data = r.json()
    print("Upload header PDF response:", {k: data.get(k) for k in ["title", "tax_type", "case_type", "year", "panel"]})
    assert data["title"] == "PUT-004812.14/2021/PP/M.IIIA Tahun 2023", f"got title={data['title']!r}"
    assert data["tax_type"] == "PPh"
    assert data["case_type"] == "Putusan Banding"
    assert data["year"] == 2023
    assert data.get("panel") == "Majelis IIIA"


# --- Upload: plain text with no putusan number -> title falls back to filename stem ---
def test_upload_plain_text_fallback_title(session, tmp_path):
    content = b"Dokumen ringkas tanpa nomor putusan apa pun. Hanya catatan umum."
    r = session.post(f"{API}/putusan/upload",
                     files={"file": ("contoh_sederhana.txt", io.BytesIO(content), "text/plain")})
    assert r.status_code == 200, r.text
    data = r.json()
    print("Plain text response:", {k: data.get(k) for k in ["title", "tax_type", "case_type", "year"]})
    assert data["title"] == "contoh sederhana"


# --- Regression: /app/test_table.pdf (PPN keyword, no PUT nomor) ---
def test_upload_table_pdf_fallback(session):
    with open("/app/test_table.pdf", "rb") as fh:
        r = session.post(f"{API}/putusan/upload",
                         files={"file": ("test_table.pdf", fh, "application/pdf")})
    assert r.status_code == 200, r.text
    data = r.json()
    print("Table PDF response:", {k: data.get(k) for k in ["title", "tax_type", "case_type", "year"]})
    assert data["title"] == "test table"
    assert data["tax_type"] == "PPN"
    # year defaults to current year (2026) when no 'Tahun YYYY' in content
    assert isinstance(data["year"], int)


# --- Regression: import-url HTML still extracts <title> ---
def test_import_url_html_title(session):
    # Use example.com which has <title>Example Domain</title>
    r = session.post(f"{API}/putusan/import-url", json={"url": "https://example.com/", "kind": "putusan"})
    assert r.status_code == 200, r.text
    data = r.json()
    print("Import HTML URL title:", data.get("title"))
    assert "Example" in data["title"]


# --- Regression: import-url with direct PDF URL ---
def test_import_url_pdf(session):
    r = session.post(f"{API}/putusan/import-url",
                     json={"url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", "kind": "putusan"})
    assert r.status_code == 200, r.text
    data = r.json()
    print("Import PDF URL response:", {k: data.get(k) for k in ["title", "tax_type", "case_type", "year"]})
    # Sample.pdf has no PUT nomor so title falls back to filename stem
    assert "dummy" in data["title"].lower()


# --- import/external with a URL that returns PDF containing putusan header ---
# We serve the local test fixture via import-url since import/external expects a URL.
# Simulating via direct file path isn't possible; we rely on import-url pdf path already tested.
# Additionally test import/external with the sample.pdf (no header) to confirm pipeline works.
def test_import_external_sample_pdf(session):
    r = session.post(f"{API}/import/external",
                     json={"url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", "kind": "putusan"})
    assert r.status_code == 200, r.text
    data = r.json()
    print("Import external sample.pdf:", {k: data.get(k) for k in ["title", "external_provider", "external_filename"]})
    assert data["external_provider"] == "URL Publik"
    assert data["external_filename"].lower().endswith(".pdf")
