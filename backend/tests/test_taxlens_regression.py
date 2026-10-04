import os
import io
import zipfile
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


def test_search_filters_and_compare():
    response = requests.get(f"{BASE_URL}/api/putusan", params={"q": "PPN", "year": 2022, "tax_type": "PPN", "case_type": "Putusan Banding"}, timeout=30)
    assert response.status_code == 200
    results = response.json()
    assert results and results[0]["tax_type"] == "PPN"
    compare = requests.post(f"{BASE_URL}/api/putusan/compare", json={"first_id": results[0]["id"], "second_id": results[0]["id"]}, timeout=30)
    assert compare.status_code == 200
    assert compare.json()["first"]["id"] == results[0]["id"]


def test_txt_upload_extracts_metadata_and_content():
    response = requests.post(f"{BASE_URL}/api/putusan/upload", files={"file": ("TEST_2024_ppn.txt", b"PUTUSAN BANDing 2024\nPPN dan pertimbangan majelis", "text/plain")}, timeout=30)
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2024 and data["tax_type"] == "PPN"
    assert "pertimbangan" in data["body"]


def test_docx_upload_extracts_content():
    from docx import Document as DocxDocument
    docx = io.BytesIO()
    doc = DocxDocument()
    doc.add_paragraph("TEST putusan PPN 2025")
    doc.save(docx)
    response = requests.post(f"{BASE_URL}/api/putusan/upload", files={"file": ("TEST_2025.docx", docx.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}, timeout=30)
    assert response.status_code == 200
    assert "TEST putusan PPN 2025" in response.json()["body"]


def test_chat_stream_returns_tokens_and_citations():
    response = requests.post(f"{BASE_URL}/api/chat", json={"question": "Apa isu PPN yang diputus?", "document_id": "put-004106-2020"}, stream=True, timeout=90)
    assert response.status_code == 200
    body = "".join(response.iter_lines(decode_unicode=True))
    assert '"type": "token"' in body and '"type": "done"' in body and '"citations"' in body