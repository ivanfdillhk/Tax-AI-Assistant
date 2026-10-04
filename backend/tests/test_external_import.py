"""Tests for /api/import/external and /api/import/external/preview endpoints."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"


# --- Preview endpoint: provider detection + URL normalization ---
class TestExternalPreview:
    def test_preview_gdrive_provider(self):
        r = requests.post(f"{API}/import/external/preview",
                          json={"url": "https://drive.google.com/file/d/FAKE/view", "kind": "putusan"},
                          timeout=30)
        # GDrive FAKE should either succeed with provider name OR fail with 400 but mention Google Drive
        if r.status_code == 200:
            assert r.json().get("provider") == "Google Drive"
            assert "uc?export=download&id=FAKE" in r.json().get("direct_url", "")
        else:
            assert r.status_code == 400
            assert "Google Drive" in r.json().get("detail", "")

    def test_preview_dropbox_provider(self):
        r = requests.post(f"{API}/import/external/preview",
                          json={"url": "https://www.dropbox.com/s/abc/x.pdf?dl=0", "kind": "putusan"},
                          timeout=30)
        if r.status_code == 200:
            data = r.json()
            assert data.get("provider") == "Dropbox"
            assert "dl.dropboxusercontent.com" in data.get("direct_url", "")
            assert "dl=1" in data.get("direct_url", "")
        else:
            assert r.status_code == 400
            assert "Dropbox" in r.json().get("detail", "")

    def test_preview_public_url_text(self):
        r = requests.post(f"{API}/import/external/preview",
                          json={"url": "https://httpbin.org/robots.txt", "kind": "putusan"},
                          timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["provider"] == "URL Publik"
        assert data["detected_format"] == "TEKS"
        assert "robots.txt" in data["filename"]


# --- Import endpoint ---
class TestExternalImport:
    def test_import_public_text_as_peraturan(self):
        r = requests.post(f"{API}/import/external",
                          json={"url": "https://httpbin.org/robots.txt", "kind": "peraturan"},
                          timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("external_provider") == "URL Publik"
        assert "robots.txt" in data.get("external_filename", "")
        assert "id" in data
        # verify persisted
        peraturan_id = data["id"]
        g = requests.get(f"{API}/peraturan/{peraturan_id}", timeout=30)
        assert g.status_code == 200
        # cleanup
        requests.delete(f"{API}/peraturan/{peraturan_id}", timeout=15)

    def test_import_invalid_url_returns_400(self):
        r = requests.post(f"{API}/import/external",
                          json={"url": "https://this-domain-does-not-exist-xyz-abc.invalid/foo", "kind": "putusan"},
                          timeout=30)
        assert r.status_code == 400, f"Expected 400 got {r.status_code}: {r.text}"
        assert "detail" in r.json()
