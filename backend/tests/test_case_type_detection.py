"""Backend tests for automatic case_type detection on upload (Banding vs Peninjauan Kembali)."""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def created_ids():
    ids = []
    yield ids
    # cleanup
    for pid in ids:
        try:
            requests.delete(f"{API}/putusan/{pid}", timeout=15)
        except Exception:
            pass


def _upload(filename, content_bytes, content_type):
    files = {"file": (filename, content_bytes, content_type)}
    r = requests.post(f"{API}/putusan/upload", files=files, timeout=60)
    assert r.status_code == 200, f"upload failed {r.status_code}: {r.text[:300]}"
    return r.json()


def test_upload_pdf_pk_mahkamah_agung(created_ids):
    with open("/app/test_pk_putusan.pdf", "rb") as f:
        data = f.read()
    doc = _upload("TEST_pk_mahkamah_agung.pdf", data, "application/pdf")
    created_ids.append(doc["id"])
    assert doc["case_type"] == "Peninjauan Kembali", doc
    assert "1234" in doc["title"] and "B/PK/PJK" in doc["title"].replace(" ", ""), doc["title"]
    assert doc["year"] == 2024
    assert doc["tax_type"] == "PPN"
    # Persistence check
    g = requests.get(f"{API}/putusan/{doc['id']}", timeout=15)
    assert g.status_code == 200
    assert g.json()["case_type"] == "Peninjauan Kembali"


def test_upload_pdf_banding_pengadilan_pajak(created_ids):
    with open("/app/test_putusan_header.pdf", "rb") as f:
        data = f.read()
    doc = _upload("TEST_banding_header.pdf", data, "application/pdf")
    created_ids.append(doc["id"])
    assert doc["case_type"] == "Putusan Banding", doc


def test_upload_txt_banding_with_pk_mention(created_ids):
    """Banding text that mentions PK as closing remark must NOT be classified as PK."""
    txt = (
        "PUTUSAN PENGADILAN PAJAK\n"
        "Nomor PUT-123456.99/2023/PP/M.IA Tahun 2023\n"
        "Antara Pemohon Banding dan Terbanding Direktur Jenderal Pajak.\n"
        "Majelis Hakim mempertimbangkan sengketa PPN Masukan.\n"
        "Demikian putusan ini dibacakan.\n"
        "Para pihak dapat mengajukan permohonan peninjauan kembali ke Mahkamah Agung "
        "dalam jangka waktu 3 bulan.\n"
    ).encode("utf-8")
    doc = _upload("TEST_banding_mention_pk.txt", txt, "text/plain")
    created_ids.append(doc["id"])
    assert doc["case_type"] == "Putusan Banding", doc


def test_upload_txt_generic_defaults_to_banding(created_ids):
    txt = b"Lorem ipsum dolor sit amet. Dokumen umum tanpa sinyal apa pun.\n" * 5
    doc = _upload("TEST_generic.txt", txt, "text/plain")
    created_ids.append(doc["id"])
    assert doc["case_type"] == "Putusan Banding", doc
    assert doc["case_type"] != "Putusan Pajak"


def test_list_putusan_only_contains_two_case_types():
    r = requests.get(f"{API}/putusan", timeout=20)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    bad = [it for it in items if it.get("case_type") not in ("Putusan Banding", "Peninjauan Kembali")]
    assert bad == [], f"Found putusan with invalid case_type: {bad[:3]}"
