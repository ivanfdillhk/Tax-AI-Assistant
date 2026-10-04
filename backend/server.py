from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Header, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import re
import requests
import json
from fastapi.responses import StreamingResponse
from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
import storage as object_storage
import web_search as web_search_module
import time
from fastapi import Query
from io import BytesIO
import base64
from PIL import Image as PILImage
from pypdf import PdfReader
import pdfplumber
from docx import Document as DocxDocument
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle, PageBreak, Flowable, Image as RLImage
from reportlab.lib.enums import TA_LEFT


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    document_id: str = "put-004106-2020"
    model: str = "gpt-5.6-terra"

class UrlImportRequest(BaseModel):
    url: str
    kind: str = "putusan"

class CompareRequest(BaseModel):
    first_id: str
    second_id: str

class StatusUpdateRequest(BaseModel):
    status: str
    dicabut_oleh: Optional[str] = None
    dicabut_tanggal: Optional[str] = None

class ExportCitation(BaseModel):
    id: str
    label: str
    text: str
    kind: Optional[str] = "paragraf"
    peraturan_id: Optional[str] = None

class ExportRequest(BaseModel):
    document_id: str
    question: str
    answer: str
    citations: List[ExportCitation] = []

class ExternalImportRequest(BaseModel):
    url: str
    kind: str = "putusan"

class BrandingRequest(BaseModel):
    firm_name: Optional[str] = None
    firm_address: Optional[str] = None
    tagline: Optional[str] = None
    logo_base64: Optional[str] = None  # data URL or raw base64

SAMPLE_PUTUSAN = {
    "id": "put-004106-2020",
    "slug": "25154-put-004106-2020-pp-16-m-ib-2022",
    "title": "PUT-004106.16/2020/PP/M.IB Tahun 2022",
    "case_type": "Putusan Banding",
    "tax_type": "PPN",
    "year": 2022,
    "court": "Pengadilan Pajak",
    "panel": "Majelis IB",
    "verdict": "Mengabulkan sebagian banding Pemohon Banding.",
    "summary": "Sengketa mengenai koreksi pajak masukan untuk pengeluaran yang tidak berkaitan dengan usaha dan faktur pajak sebelum memperoleh NSFP.",
    "source_url": "https://www.inapintar.ai/tax-knowledge/putusan/25154-put-004106-2020-pp-16-M-IB-2022",
    "body": """DEMI KEADILAN BERDASARKAN KETUHANAN YANG MAHA ESA\n\nPENGADILAN PAJAK\n\nmemeriksa dan memutus sengketa pajak pada tingkat pertama dan terakhir dengan Acara Biasa mengenai banding terhadap Keputusan Direktur Jenderal Pajak.\n\nSENGKETA\nSengketa berkaitan dengan koreksi Pajak Masukan atas pengeluaran yang tidak berkaitan dengan usaha dan faktur pajak yang diterbitkan sebelum diperolehnya Nomor Seri Faktur Pajak (NSFP), merujuk pada Pasal 9 ayat (8) UU PPN Nomor 42 Tahun 2009 dan PER-16/PJ/2014.\n\nPERTIMBANGAN MAJELIS\nMajelis berpendapat koreksi atas faktur sebelum NSFP tidak dapat dipertahankan sepanjang bukti pembayaran dan transaksi dapat dibuktikan, sejalan dengan Pasal 72 PMK 18/PMK.03/2021. Koreksi atas pengeluaran yang tidak berkaitan dengan usaha tetap dipertahankan.\n\nAMAR PUTUSAN\nMengabulkan sebagian permohonan banding dan mengubah Keputusan Direktur Jenderal Pajak sesuai pertimbangan tersebut.""",
    "created_at": "2024-01-15T00:00:00+00:00"
}

EXTRA_SAMPLE_PUTUSAN = [
    {"id": "put-pph21-2023", "slug": "put-pph21-perusahaan-2023", "title": "PUT-004812.14/2021/PP/M.IIIA Tahun 2023", "case_type": "Putusan Banding", "tax_type": "PPh", "year": 2023, "court": "Pengadilan Pajak", "panel": "Majelis IIIA",
     "verdict": "Menolak banding Pemohon.", "summary": "Sengketa pemotongan PPh Pasal 21 atas natura dan kenikmatan dalam masa transisi UU HPP.",
     "source_url": "https://www.inapintar.ai/tax-knowledge/putusan/put-pph21-perusahaan-2023",
     "body": "DEMI KEADILAN BERDASARKAN KETUHANAN YANG MAHA ESA\n\nPENGADILAN PAJAK\n\nSENGKETA\nKoreksi fiskus atas pemotongan PPh Pasal 21 berdasarkan Pasal 21 UU PPh Nomor 36 Tahun 2008 juncto UU 7/2021.\n\nPERTIMBANGAN MAJELIS\nMajelis mempertimbangkan tarif PPh orang pribadi dalam Pasal 17 UU 36/2008 yang diubah oleh UU 7/2021. Pemohon tidak dapat membuktikan sifat non-objek dari natura dimaksud.\n\nAMAR PUTUSAN\nMenolak banding dan mempertahankan ketetapan DJP.",
     "created_at": "2024-02-10T00:00:00+00:00"},
    {"id": "put-kup-keberatan-2021", "slug": "put-kup-keberatan-2021", "title": "PUT-003214.16/2019/PP/M.IIB Tahun 2021", "case_type": "Putusan Banding", "tax_type": "KUP", "year": 2021, "court": "Pengadilan Pajak", "panel": "Majelis IIB",
     "verdict": "Mengabulkan seluruhnya banding Pemohon.", "summary": "Sengketa prosedur pengajuan keberatan Pasal 25 UU KUP yang dinyatakan tidak memenuhi syarat formal.",
     "source_url": "https://www.inapintar.ai/tax-knowledge/putusan/put-kup-keberatan-2021",
     "body": "DEMI KEADILAN BERDASARKAN KETUHANAN YANG MAHA ESA\n\nPENGADILAN PAJAK\n\nSENGKETA\nFiskus menolak keberatan karena dianggap lewat waktu sesuai Pasal 25 UU KUP Nomor 28 Tahun 2007.\n\nPERTIMBANGAN MAJELIS\nMajelis menilai jangka waktu 3 bulan Pasal 25 UU 28/2007 belum terlampaui mengingat tanggal diterimanya SKPKB. Pasal 27 UU 28/2007 mengatur banding atas keputusan keberatan.\n\nAMAR PUTUSAN\nMengabulkan seluruhnya permohonan banding Pemohon.",
     "created_at": "2024-02-14T00:00:00+00:00"},
]

def paragraph_records(body: str):
    records = []
    counter = 0
    for text in body.split("\n"):
        stripped = text.strip()
        if not stripped:
            continue
        counter += 1
        records.append({"id": f"P{counter}", "text": stripped})
    return records

SAMPLE_PERATURAN = [
    {"id": "uu-42-2009", "jenis": "UU", "nomor": "42/2009", "tahun": 2009, "judul": "UU PPN & PPnBM", "status": "Berlaku", "tanggal_berlaku": "2010-04-01", "source_url": "https://peraturan.go.id/id/uu-no-42-tahun-2009",
     "body": "Pasal 9 ayat (8): Pajak Masukan tidak dapat dikreditkan atas pengeluaran yang tidak mempunyai hubungan langsung dengan kegiatan usaha.\nPasal 13 ayat (5): Faktur Pajak harus memenuhi syarat formal dan material.\nPasal 16B: Fasilitas PPN diberikan atas penyerahan tertentu sesuai Peraturan Pemerintah."},
    {"id": "uu-7-2021", "jenis": "UU", "nomor": "7/2021", "tahun": 2021, "judul": "UU Harmonisasi Peraturan Perpajakan (HPP)", "status": "Berlaku", "tanggal_berlaku": "2021-10-29", "source_url": "https://peraturan.go.id/id/uu-no-7-tahun-2021",
     "body": "Pasal 4A: Jenis barang dan jasa yang tidak dikenai PPN.\nPasal 7: Tarif PPN sebesar 11% berlaku mulai 1 April 2022 dan menjadi 12% paling lambat 1 Januari 2025.\nPasal 32A: Program Pengungkapan Sukarela (PPS) Wajib Pajak."},
    {"id": "uu-28-2007", "jenis": "UU", "nomor": "28/2007", "tahun": 2007, "judul": "UU Ketentuan Umum dan Tata Cara Perpajakan (KUP)", "status": "Berlaku", "tanggal_berlaku": "2008-01-01", "source_url": "https://peraturan.go.id/id/uu-no-28-tahun-2007",
     "body": "Pasal 13: Direktur Jenderal Pajak dapat menerbitkan Surat Ketetapan Pajak Kurang Bayar.\nPasal 25: Wajib Pajak dapat mengajukan keberatan dalam jangka waktu 3 bulan.\nPasal 27: Banding ke Pengadilan Pajak dilakukan paling lambat 3 bulan sejak keputusan keberatan."},
    {"id": "uu-36-2008", "jenis": "UU", "nomor": "36/2008", "tahun": 2008, "judul": "UU Pajak Penghasilan (PPh)", "status": "Berlaku", "tanggal_berlaku": "2009-01-01", "source_url": "https://peraturan.go.id/id/uu-no-36-tahun-2008",
     "body": "Pasal 4 ayat (2): Penghasilan tertentu dikenai PPh Final.\nPasal 17: Tarif PPh orang pribadi dan badan.\nPasal 21: Pemotongan PPh atas penghasilan sehubungan dengan pekerjaan, jasa, dan kegiatan."},
    {"id": "pmk-18-2021", "jenis": "PMK", "nomor": "18/PMK.03/2021", "tahun": 2021, "judul": "PMK Pelaksanaan UU Cipta Kerja Bidang PPh, PPN & PPnBM, serta KUP", "status": "Berlaku", "tanggal_berlaku": "2021-02-17", "source_url": "https://jdih.kemenkeu.go.id/download-file/27/18~PMK.03~2021Per.pdf",
     "body": "Pasal 60: Pajak Masukan sebelum pengukuhan PKP dapat dikreditkan dengan pedoman tertentu.\nPasal 72: Faktur Pajak yang diterbitkan sebelum pengusaha dikukuhkan sebagai PKP tetap dapat dikreditkan sepanjang memenuhi syarat.\nPasal 85: Ketentuan penagihan dan keberatan pajak."},
    {"id": "per-16-2014", "jenis": "PER-DJP", "nomor": "PER-16/PJ/2014", "tahun": 2014, "judul": "Tata Cara Pemberian Nomor Seri Faktur Pajak", "status": "Berlaku", "tanggal_berlaku": "2014-07-01", "source_url": "https://pajak.go.id/id/peraturan-direktur-jenderal-pajak-nomor-16pj2014",
     "body": "Pasal 2: PKP mengajukan permintaan Nomor Seri Faktur Pajak (NSFP) kepada Direktur Jenderal Pajak.\nPasal 9: Faktur Pajak yang diterbitkan sebelum PKP memperoleh NSFP merupakan Faktur Pajak tidak lengkap.\nPasal 11: Sanksi atas penerbitan Faktur Pajak tidak sesuai ketentuan."},
    {"id": "uu-18-2000", "jenis": "UU", "nomor": "18/2000", "tahun": 2000, "judul": "UU PPN & PPnBM (Perubahan Kedua UU 8/1983) - DICABUT oleh UU 42/2009", "status": "Dicabut", "tanggal_berlaku": "2001-01-01", "dicabut_oleh": "UU 42/2009", "dicabut_tanggal": "2010-04-01", "source_url": "https://peraturan.go.id/id/uu-no-18-tahun-2000",
     "body": "Pasal 9 ayat (8): Pajak Masukan tidak dapat dikreditkan atas pengeluaran yang tidak langsung terkait dengan usaha. (versi lama, dicabut)\nPasal 13: Faktur Pajak Standar wajib memuat identitas lengkap PKP. (versi lama, dicabut)"},
]

def peraturan_citation_label(record):
    return f"{record['jenis']} {record['nomor']}" if record['jenis'] in {"PMK", "PER-DJP", "SE-DJP", "PP"} else f"{record['jenis']} {record['nomor'].split('/')[0]}/{record['tahun']}"

def infer_peraturan_metadata(filename, content):
    name = Path(filename).stem.replace("_", " ").replace("-", " ")
    jenis_match = re.search(r"\b(UU|PP|PMK|PER-DJP|SE-DJP|PERPU)\b", f"{name} {content[:2000]}", re.I)
    nomor_match = re.search(r"(?:Nomor|No\.?)\s*([\w\.\-\/]+)", content[:3000], re.I)
    tahun_match = re.search(r"(?:Tahun\s+)?(19\d{2}|20\d{2})", f"{name} {content[:3000]}")
    return {
        "jenis": (jenis_match.group(1).upper() if jenis_match else "LAIN"),
        "nomor": (nomor_match.group(1) if nomor_match else name[:40]),
        "tahun": int(tahun_match.group(1)) if tahun_match else datetime.now(timezone.utc).year,
        "judul": name[:160],
        "status": "Berlaku",
        "tanggal_berlaku": None,
    }

def peraturan_from_text(filename, content, source_url):
    meta = infer_peraturan_metadata(filename, content)
    return {"id": str(uuid.uuid4()), **meta, "body": content[:120000], "source_url": source_url, "created_at": datetime.now(timezone.utc).isoformat()}

def _extract_putusan_nomor(content: str):
    """Try hard to find the real Pengadilan Pajak decision number from the first ~3000 chars."""
    head = re.sub(r"\s+", " ", content[:4000])
    patterns = [
        r"PUT[-.\s]*\d{4,6}[\d./\-]*\s*/\s*PP\s*/\s*M\.[A-Z]+(?:\s+Tahun\s+\d{4})?",
        r"PUT[-.\s]*\d{4,6}\.\d{1,3}\s*/\s*\d{4}\s*/\s*PP\s*/\s*M\.[A-Z]+(?:\s+Tahun\s+\d{4})?",
        r"Putusan\s+(?:Pengadilan\s+Pajak\s+)?Nomor\s+PUT[-.\s]*[\w./\-]+(?:\s+Tahun\s+\d{4})?",
        r"PUT[-.\s]*\d{4,6}[\d./\-]*",
    ]
    for pat in patterns:
        match = re.search(pat, head, re.I)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip().replace("Nomor PUT", "PUT")
    return None

def _extract_tax_type(content: str):
    head = content[:4000]
    for label, pattern in [
        ("PPN", r"\bPPN\b|Pajak Pertambahan Nilai"),
        ("PPh", r"\bPPh\b|Pajak Penghasilan"),
        ("PPnBM", r"\bPPnBM\b|Pajak Penjualan atas Barang Mewah"),
        ("PBB", r"\bPBB\b|Pajak Bumi dan Bangunan"),
        ("BPHTB", r"\bBPHTB\b|Bea Perolehan Hak"),
        ("Bea Masuk", r"\bBea Masuk\b"),
        ("Cukai", r"\bCukai\b"),
        ("KUP", r"\bKUP\b|Ketentuan Umum dan Tata Cara Perpajakan"),
    ]:
        if re.search(pattern, head, re.I):
            return label
    return "Pajak umum"

def _extract_case_type(content: str):
    head = content[:4000]
    if re.search(r"Peninjauan\s+Kembali", head, re.I): return "Peninjauan Kembali"
    if re.search(r"\bgugatan\b", head, re.I): return "Putusan Gugatan"
    if re.search(r"\bbanding\b", head, re.I): return "Putusan Banding"
    return "Putusan Pajak"

def _extract_panel(content: str):
    match = re.search(r"Majelis\s+([IVXLCDM]+[A-Z]?)", content[:4000])
    return f"Majelis {match.group(1)}" if match else None

def infer_metadata(filename: str, content: str):
    nomor = _extract_putusan_nomor(content)
    fallback_name = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    tahun_match = re.search(r"Tahun\s+(19\d{2}|20\d{2})", content[:4000], re.I)
    year_match = tahun_match or re.search(r"(?:19|20)\d{2}", f"{fallback_name} {content[:3000]}")
    year = int(year_match.group(1) if tahun_match else year_match.group()) if year_match else datetime.now(timezone.utc).year
    meta = {
        "title": nomor or fallback_name,
        "year": year,
        "tax_type": _extract_tax_type(content),
        "case_type": _extract_case_type(content),
    }
    panel = _extract_panel(content)
    if panel: meta["panel"] = panel
    return meta

def document_from_text(filename: str, content: str, source_url: str):
    metadata = infer_metadata(filename, content)
    return {**SAMPLE_PUTUSAN, "id": str(uuid.uuid4()), "slug": str(uuid.uuid4()), **metadata, "summary": content[:280].replace("\n", " "), "body": content[:120000], "source_url": source_url, "created_at": datetime.now(timezone.utc).isoformat()}

# Add your routes to the router instead of directly to app
async def save_uploaded_file(raw: bytes, filename: str, content_type: str, linked_type: str, linked_id: str):
    """Persist original file bytes to object storage + a reference record in Mongo.

    Returns the file record dict, or None if storage is unavailable (upload still
    succeeds without the original attachment)."""
    try:
        safe_name = filename or "dokumen"
        ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else "bin"
        file_id = str(uuid.uuid4())
        path = f"{object_storage.APP_NAME}/uploads/{linked_type}/{file_id}.{ext}"
        ct = content_type or object_storage.guess_content_type(safe_name)
        result = object_storage.put_object(path, raw, ct)
        record = {
            "id": file_id,
            "storage_path": result["path"],
            "original_filename": safe_name,
            "content_type": ct,
            "size": result.get("size", len(raw)),
            "linked_type": linked_type,
            "linked_id": linked_id,
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.files.insert_one(record.copy())
        record.pop("_id", None)
        return record
    except Exception as exc:
        logger.error("save_uploaded_file failed (%s): %s", filename, exc)
        return None
@api_router.get("/")
async def root():
    return {"message": "TaxLens API ready"}

@api_router.get("/putusan/{document_id}")
async def get_putusan(document_id: str):
    document = await db.putusan.find_one({"id": document_id}, {"_id": 0})
    if document:
        return document
    if document_id in {SAMPLE_PUTUSAN["id"], SAMPLE_PUTUSAN["slug"]}:
        return SAMPLE_PUTUSAN
    raise HTTPException(status_code=404, detail="Putusan tidak ditemukan")

@api_router.get("/putusan")
async def list_putusan(q: Optional[str] = None, year: Optional[str] = None, tax_type: Optional[str] = None, case_type: Optional[str] = None):
    query = {}
    if q:
        query["$or"] = [{"title": {"$regex": q, "$options": "i"}}, {"body": {"$regex": q, "$options": "i"}}, {"summary": {"$regex": q, "$options": "i"}}]
    year_int = int(year) if year and year.strip().isdigit() else None
    if year_int: query["year"] = year_int
    if tax_type: query["tax_type"] = tax_type
    if case_type: query["case_type"] = case_type
    documents = await db.putusan.find(query, {"_id": 0}).sort("year", -1).to_list(50)
    sample_text = " ".join(str(value) for value in SAMPLE_PUTUSAN.values())
    sample_matches = (not q or q.lower() in sample_text.lower()) and (not year_int or year_int == SAMPLE_PUTUSAN["year"]) and (not tax_type or tax_type.lower() == SAMPLE_PUTUSAN["tax_type"].lower()) and (not case_type or case_type.lower() == SAMPLE_PUTUSAN["case_type"].lower())
    if not documents and sample_matches:
        documents = [SAMPLE_PUTUSAN]
    return documents

@api_router.post("/putusan/compare")
async def compare_putusan(payload: CompareRequest):
    first = await get_putusan(payload.first_id)
    second = await get_putusan(payload.second_id)
    return {"first": first, "second": second, "differences": {"tax_type": first.get("tax_type") != second.get("tax_type"), "case_type": first.get("case_type") != second.get("case_type"), "verdict": first.get("verdict") != second.get("verdict")}}

@api_router.post("/putusan/upload")
async def upload_putusan(file: UploadFile = File(...)):
    raw = await file.read()
    filename = file.filename or "putusan.txt"
    try:
        if filename.lower().endswith(".pdf"):
            content = _extract_pdf_structured(raw)
        elif filename.lower().endswith(".docx"):
            content = "\n".join(paragraph.text for paragraph in DocxDocument(BytesIO(raw)).paragraphs)
        else:
            content = raw.decode("utf-8", errors="ignore")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Dokumen tidak dapat dibaca: {exc}")
    if not content.strip():
        raise HTTPException(status_code=400, detail="File kosong")
    document = document_from_text(filename, content, "File pengguna")
    file_record = await save_uploaded_file(raw, filename, file.content_type, "putusan", document["id"])
    if file_record:
        document["file_id"] = file_record["id"]
        document["original_filename"] = file_record["original_filename"]
    await db.putusan.insert_one(document.copy())
    document.pop("_id", None)
    return document

@api_router.post("/putusan/import-url")
async def import_public_url(payload: UrlImportRequest):
    try:
        response = requests.get(payload.url, timeout=20, headers={"User-Agent": "TaxLens/1.0"}, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=400, detail=f"Sumber tidak dapat diakses: {exc}")
    content_type = response.headers.get("Content-Type", "").lower()
    url_lower = payload.url.lower().split("?")[0]
    saved_file = None  # (bytes, filename, content_type) when a real file was fetched
    try:
        if "pdf" in content_type or url_lower.endswith(".pdf"):
            text = _extract_pdf_structured(response.content)
            fname = _external_filename(response, payload.url)
            if not fname.lower().endswith(".pdf"):
                fname += ".pdf"
            title = fname.rsplit(".", 1)[0]
            saved_file = (response.content, fname, "application/pdf")
        elif "wordprocessingml" in content_type or url_lower.endswith(".docx"):
            text = "\n".join(paragraph.text for paragraph in DocxDocument(BytesIO(response.content)).paragraphs)
            fname = _external_filename(response, payload.url)
            if not fname.lower().endswith(".docx"):
                fname += ".docx"
            title = fname.rsplit(".", 1)[0]
            saved_file = (response.content, fname, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        else:
            text = re.sub(r"<[^>]+>", " ", response.text)
            text = re.sub(r"\s+", " ", text).strip()
            title_match = re.search(r"<title>(.*?)</title>", response.text, re.I | re.S)
            title = title_match.group(1).strip() if title_match else ("peraturan-publik" if payload.kind == "peraturan" else "putusan-publik")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Isi URL tidak dapat diproses: {exc}")
    if not text.strip():
        raise HTTPException(status_code=400, detail="Isi URL kosong atau tidak terbaca")
    linked_type = "peraturan" if payload.kind == "peraturan" else "putusan"
    if payload.kind == "peraturan":
        document = peraturan_from_text(title, text, payload.url)
    else:
        document = document_from_text(title, text, payload.url)
    if saved_file:
        file_record = await save_uploaded_file(saved_file[0], saved_file[1], saved_file[2], linked_type, document["id"])
        if file_record:
            document["file_id"] = file_record["id"]
            document["original_filename"] = file_record["original_filename"]
    collection = db.peraturan if payload.kind == "peraturan" else db.putusan
    await collection.insert_one(document.copy())
    document.pop("_id", None)
    return document

@api_router.get("/files")
async def list_files(linked_type: Optional[str] = None, linked_id: Optional[str] = None):
    query = {"is_deleted": False}
    if linked_type:
        query["linked_type"] = linked_type
    if linked_id:
        query["linked_id"] = linked_id
    cursor = db.files.find(query, {"_id": 0}).sort("created_at", -1).limit(1000)
    return await cursor.to_list(length=1000)


@api_router.get("/files/{file_id}/download")
async def download_file(file_id: str, inline: bool = False):
    record = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    try:
        data, content_type = object_storage.get_object(record["storage_path"])
    except Exception as exc:
        logger.error("download_file failed for %s: %s", file_id, exc)
        raise HTTPException(status_code=502, detail="Gagal mengambil file dari penyimpanan")
    filename = record.get("original_filename", "dokumen")
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=record.get("content_type") or content_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@api_router.delete("/files/{file_id}")
async def delete_file(file_id: str):
    result = await db.files.update_one({"id": file_id, "is_deleted": False}, {"$set": {"is_deleted": True}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    return {"id": file_id, "is_deleted": True}


def _normalize_external_url(url):
    url = url.strip()
    if "drive.google.com" in url:
        m = re.search(r"/d/([a-zA-Z0-9_-]+)", url) or re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
        if m:
            return (f"https://drive.google.com/uc?export=download&id={m.group(1)}", "Google Drive")
    if "dropbox.com" in url:
        direct = re.sub(r"[?&]dl=0", "", url)
        direct = direct + ("&dl=1" if "?" in direct else "?dl=1")
        direct = direct.replace("www.dropbox.com", "dl.dropboxusercontent.com")
        return (direct, "Dropbox")
    if "onedrive.live.com" in url or "1drv.ms" in url or "sharepoint.com" in url:
        sep = "&" if "?" in url else "?"
        return (f"{url}{sep}download=1", "OneDrive")
    return (url, "URL Publik")

def _external_filename(response, url):
    cd = response.headers.get("Content-Disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?\"?([^\";]+)\"?', cd)
    if m:
        return re.sub(r"%20", " ", m.group(1))
    base = url.split("?")[0].rstrip("/").split("/")[-1]
    return base or "dokumen-eksternal"

def _extract_pdf_structured(raw_bytes):
    """Extract PDF content preserving tables as [TABLE]...[/TABLE] blocks with tab-separated rows."""
    parts = []
    try:
        with pdfplumber.open(BytesIO(raw_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.find_tables() or []
                table_bboxes = [tbl.bbox for tbl in tables]
                # Extract non-table text first
                def not_in_table(obj):
                    for (x0, y0, x1, y1) in table_bboxes:
                        if obj["x0"] >= x0 and obj["x1"] <= x1 and obj["top"] >= y0 and obj["bottom"] <= y1:
                            return False
                    return True
                page_text = page.filter(not_in_table).extract_text() or ""
                if page_text.strip():
                    parts.append(page_text.strip())
                for tbl in tables:
                    rows = tbl.extract() or []
                    cleaned = ["\t".join((cell or "").strip().replace("\n", " ") for cell in row) for row in rows if any(cell for cell in row)]
                    if cleaned:
                        parts.append("[TABLE]\n" + "\n".join(cleaned) + "\n[/TABLE]")
    except Exception:
        # Fallback: pypdf flat text if pdfplumber fails
        return "\n".join((p.extract_text() or "") for p in PdfReader(BytesIO(raw_bytes)).pages)
    return "\n\n".join(parts)

def _extract_text_from_binary(filename, content_type, raw_bytes, html_text):
    lower = filename.lower(); ct = (content_type or "").lower()
    if lower.endswith(".pdf") or "pdf" in ct:
        return _extract_pdf_structured(raw_bytes)
    if lower.endswith(".docx") or "wordprocessingml" in ct:
        return "\n".join(paragraph.text for paragraph in DocxDocument(BytesIO(raw_bytes)).paragraphs)
    if "html" in ct:
        text = re.sub(r"<[^>]+>", " ", html_text)
        return re.sub(r"\s+", " ", text).strip()
    return raw_bytes.decode("utf-8", errors="ignore")

@api_router.post("/import/external/preview")
async def preview_external(payload: ExternalImportRequest):
    direct_url, provider = _normalize_external_url(payload.url)
    try:
        response = requests.get(direct_url, timeout=12, headers={"User-Agent": "TaxLens/1.0", "Range": "bytes=0-2048"}, allow_redirects=True, stream=True)
        headers = response.headers
        response.close()
    except requests.RequestException as exc:
        raise HTTPException(status_code=400, detail=f"Tidak dapat mengakses {provider}: {exc}")
    filename = _external_filename(response, direct_url)
    content_type = headers.get("Content-Type", "unknown")
    length_header = headers.get("Content-Length") or headers.get("Content-Range", "").split("/")[-1]
    size_kb = int(int(length_header) / 1024) if length_header and length_header.isdigit() else None
    detected = "PDF" if filename.lower().endswith(".pdf") or "pdf" in content_type.lower() else ("DOCX" if filename.lower().endswith(".docx") or "wordprocessingml" in content_type.lower() else ("HTML" if "html" in content_type.lower() else "TEKS"))
    return {"provider": provider, "filename": filename, "content_type": content_type, "size_kb": size_kb, "detected_format": detected, "direct_url": direct_url}

@api_router.post("/import/external")
async def import_external(payload: ExternalImportRequest):
    direct_url, provider = _normalize_external_url(payload.url)
    try:
        response = requests.get(direct_url, timeout=30, headers={"User-Agent": "TaxLens/1.0"}, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=400, detail=f"Tidak dapat mengambil file dari {provider}: {exc}")
    filename = _external_filename(response, direct_url)
    try:
        content = _extract_text_from_binary(filename, response.headers.get("Content-Type", ""), response.content, response.text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Gagal memproses {filename}: {exc}")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Isi file kosong atau tidak terbaca")
    source_label = f"{provider} · {payload.url}"
    if payload.kind == "peraturan":
        document = peraturan_from_text(filename, content, source_label)
        await db.peraturan.insert_one(document.copy())
    else:
        document = document_from_text(filename, content, source_label)
        await db.putusan.insert_one(document.copy())
    document.pop("_id", None)
    document["external_provider"] = provider
    document["external_filename"] = filename
    return document

@api_router.get("/peraturan")
async def list_peraturan(q: Optional[str] = None, jenis: Optional[str] = None, tahun: Optional[str] = None, status: Optional[str] = None):
    query = {}
    if q:
        query["$or"] = [{"judul": {"$regex": q, "$options": "i"}}, {"body": {"$regex": q, "$options": "i"}}, {"nomor": {"$regex": q, "$options": "i"}}]
    tahun_int = int(tahun) if tahun and tahun.strip().isdigit() else None
    if tahun_int: query["tahun"] = tahun_int
    if jenis: query["jenis"] = jenis
    if status: query["status"] = status
    docs = await db.peraturan.find(query, {"_id": 0}).sort("tahun", -1).to_list(100)
    return docs

@api_router.get("/peraturan/{peraturan_id}")
async def get_peraturan(peraturan_id: str):
    doc = await db.peraturan.find_one({"id": peraturan_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Peraturan tidak ditemukan")
    return doc

@api_router.patch("/peraturan/{peraturan_id}/status")
async def update_peraturan_status(peraturan_id: str, payload: StatusUpdateRequest):
    if payload.status not in {"Berlaku", "Dicabut", "Diubah"}:
        raise HTTPException(status_code=400, detail="Status harus Berlaku, Dicabut, atau Diubah")
    update = {"status": payload.status}
    update["dicabut_oleh"] = payload.dicabut_oleh if payload.status != "Berlaku" else None
    update["dicabut_tanggal"] = payload.dicabut_tanggal if payload.status != "Berlaku" else None
    result = await db.peraturan.update_one({"id": peraturan_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Peraturan tidak ditemukan")
    doc = await db.peraturan.find_one({"id": peraturan_id}, {"_id": 0})
    return doc

@api_router.get("/peraturan/{peraturan_id}/putusan")
async def peraturan_related_putusan(peraturan_id: str):
    reg = await db.peraturan.find_one({"id": peraturan_id}, {"_id": 0})
    if not reg:
        raise HTTPException(status_code=404, detail="Peraturan tidak ditemukan")
    # Build patterns matching the peraturan: nomor + "jenis <nomor-pokok>/<tahun>"
    patterns = [re.escape(reg["nomor"])]
    nomor_pokok = reg["nomor"].split("/")[0]
    patterns.append(rf"{re.escape(reg['jenis'])}[^.\n]{{0,30}}?\b{re.escape(nomor_pokok)}\s*(?:Tahun\s*)?{reg['tahun']}\b")
    patterns.append(rf"{re.escape(reg['jenis'])}\s*{re.escape(reg['nomor'])}")
    combined = re.compile("|".join(patterns), re.I)
    all_putusan = await db.putusan.find({}, {"_id": 0}).to_list(500)
    # Include SAMPLE_PUTUSAN if not already seeded
    if not any(item["id"] == SAMPLE_PUTUSAN["id"] for item in all_putusan):
        all_putusan.append(SAMPLE_PUTUSAN)
    hits = []
    for put in all_putusan:
        haystack = f"{put.get('title','')} {put.get('summary','')} {put.get('body','')}"
        matches = combined.findall(haystack)
        if matches:
            hits.append({"id": put["id"], "title": put["title"], "year": put.get("year"), "tax_type": put.get("tax_type"), "case_type": put.get("case_type"), "match_count": len(matches)})
    hits.sort(key=lambda item: item["match_count"], reverse=True)
    return {"peraturan": {"id": reg["id"], "nomor": reg["nomor"], "jenis": reg["jenis"], "judul": reg["judul"], "status": reg.get("status", "Berlaku")}, "putusan": hits}

@api_router.post("/peraturan/upload")
async def upload_peraturan(file: UploadFile = File(...)):
    raw = await file.read()
    filename = file.filename or "peraturan.txt"
    try:
        if filename.lower().endswith(".pdf"):
            content = _extract_pdf_structured(raw)
        elif filename.lower().endswith(".docx"):
            content = "\n".join(paragraph.text for paragraph in DocxDocument(BytesIO(raw)).paragraphs)
        else:
            content = raw.decode("utf-8", errors="ignore")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Dokumen tidak dapat dibaca: {exc}")
    if not content.strip():
        raise HTTPException(status_code=400, detail="File kosong")
    doc = peraturan_from_text(filename, content, "File pengguna")
    file_record = await save_uploaded_file(raw, filename, file.content_type, "peraturan", doc["id"])
    if file_record:
        doc["file_id"] = file_record["id"]
        doc["original_filename"] = file_record["original_filename"]
    await db.peraturan.insert_one(doc.copy())
    doc.pop("_id", None)
    return doc

def _match_peraturan_passages(peraturan_items, question, document_body):
    tokens = {term.lower() for term in re.split(r"\W+", f"{question} {document_body[:1500]}") if len(term) > 3}
    hits = []
    for reg in peraturan_items:
        for line in reg["body"].split("\n"):
            line_tokens = {w.lower() for w in re.split(r"\W+", line) if len(w) > 3}
            score = len(tokens & line_tokens)
            if score >= 2:
                hits.append((score, reg, line.strip()))
    hits.sort(key=lambda item: item[0], reverse=True)
    return hits[:3]

@api_router.post("/chat")
async def chat(payload: ChatRequest):
    document = await get_putusan(payload.document_id)
    provider_model = "gpt-5.6-terra" if payload.model != "gemini-3-flash" else "gemini-3-flash-preview"
    paragraphs = paragraph_records(document["body"])
    peraturan_items = await db.peraturan.find({"status": "Berlaku"}, {"_id": 0}).to_list(100)
    reg_hits = _match_peraturan_passages(peraturan_items, payload.question, document["body"])
    reg_citations = []
    seen_reg_ids = set()
    for _score, reg, line in reg_hits:
        label = peraturan_citation_label(reg)
        cid = f"REG-{reg['id']}"
        if cid in seen_reg_ids:
            continue
        seen_reg_ids.add(cid)
        reg_citations.append({"id": cid, "label": label, "text": line[:160], "kind": "peraturan", "peraturan_id": reg["id"]})
    para_citations = [{"id": item["id"], "label": item["id"], "text": item["text"][:120], "kind": "paragraf"} for item in paragraphs if any(term.lower() in item["text"].lower() for term in payload.question.split() if len(term) > 3)][:4] or [{"id": item["id"], "label": item["id"], "text": item["text"][:120], "kind": "paragraf"} for item in paragraphs[:2]]
    citations = para_citations + reg_citations
    peraturan_block = "\n".join(f"[{peraturan_citation_label(reg)}] {line}" for _score, reg, line in reg_hits) or "(tidak ada peraturan terkait yang cocok)"
    prompt = (f"Konteks putusan pajak:\nJudul: {document['title']}\nRingkasan: {document['summary']}\nIsi bernomor:\n"
              + "\n".join(f"[{item['id']}] {item['text']}" for item in paragraphs[:80])
              + f"\n\nDasar peraturan terkait:\n{peraturan_block}")
    system = "Anda adalah asisten analis putusan pajak Indonesia. Jawab dalam Bahasa Indonesia. Gunakan konteks putusan dan dasar peraturan yang disediakan. Setiap klaim penting wajib diberi sitasi inline: paragraf putusan sebagai [P4] dan peraturan sebagai [UU 42/2009] atau [PMK 18/PMK.03/2021]. Jangan memberi nasihat hukum final."
    async def event_stream():
        chat_session = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"taxlens-{uuid.uuid4()}", system_message=system).with_model("openai", provider_model)
        user_message = UserMessage(text=f"{prompt}\n\nPertanyaan pengguna: {payload.question}")
        async for event in chat_session.stream_message(user_message):
            if isinstance(event, TextDelta):
                yield f"data: {json.dumps({'type': 'token', 'content': event.content})}\n\n"
            elif isinstance(event, StreamDone):
                yield f"data: {json.dumps({'type': 'done', 'source': document['title'], 'citations': citations})}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

async def _get_branding():
    doc = await db.branding.find_one({"id": "default"}, {"_id": 0})
    return doc or {"id": "default", "firm_name": None, "firm_address": None, "tagline": None, "logo_base64": None}

def _decode_logo(logo_base64):
    if not logo_base64:
        return None
    try:
        raw = logo_base64.split(",", 1)[1] if logo_base64.startswith("data:") else logo_base64
        data = base64.b64decode(raw)
        # Validate it is a readable image by fully loading via PIL
        with PILImage.open(BytesIO(data)) as pil:
            pil.load()
            if pil.mode in ("P", "RGBA"):
                pil = pil.convert("RGBA")
            else:
                pil = pil.convert("RGB")
            output = BytesIO()
            pil.save(output, format="PNG")
            output.seek(0)
            return output
    except Exception:
        return None

def _branding_image_flowable(branding, max_height_mm=14):
    buf = _decode_logo(branding.get("logo_base64"))
    if not buf:
        return None
    try:
        image = RLImage(buf, height=max_height_mm*mm, width=max_height_mm*mm*3, kind="proportional")
        return image
    except Exception:
        return None

@api_router.get("/branding")
async def get_branding():
    return await _get_branding()

@api_router.post("/branding")
async def update_branding(payload: BrandingRequest):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    update["id"] = "default"; update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.branding.update_one({"id": "default"}, {"$set": update}, upsert=True)
    doc = await db.branding.find_one({"id": "default"}, {"_id": 0})
    return doc

@api_router.delete("/branding/logo")
async def delete_branding_logo():
    await db.branding.update_one({"id": "default"}, {"$set": {"logo_base64": None}}, upsert=True)
    return {"ok": True}

def _escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _append_letterhead(story, branding, kicker_style, firm_style, firm_small_style, tagline_text):
    firm_name = (branding.get("firm_name") or "").strip()
    firm_address = (branding.get("firm_address") or "").strip()
    firm_tagline = (branding.get("tagline") or "").strip()
    image = _branding_image_flowable(branding)
    text_block = []
    if firm_name:
        text_block.append(Paragraph(_escape_html(firm_name), firm_style))
    if firm_address:
        text_block.append(Paragraph(_escape_html(firm_address), firm_small_style))
    if firm_tagline:
        text_block.append(Paragraph(f"<i>{_escape_html(firm_tagline)}</i>", firm_small_style))
    text_block.append(Paragraph(tagline_text, kicker_style))
    if image:
        header = Table([[image, text_block]], colWidths=[32*mm, None])
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0)]))
        story.append(header)
    else:
        for item in text_block:
            story.append(item)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 4))

def _md_inline(text):
    """Convert inline markdown to ReportLab mini-HTML (after escaping)."""
    t = _escape_html(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"__(.+?)__", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", t)
    return t


def _render_markdown_pdf(text, story, body_style, heading_style):
    """Render a markdown answer into ReportLab flowables (headings, lists, bold/italic)."""
    bullet_style = ParagraphStyle("mdBullet", parent=body_style, leftIndent=14, spaceAfter=3)
    for raw in (text or "").split("\n"):
        stripped = raw.strip()
        if not stripped:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            story.append(Paragraph(_md_inline(m.group(2)), heading_style))
            continue
        if re.match(r"^([-*_]\s*){3,}$", stripped):
            story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0")))
            continue
        m = re.match(r"^[-*•]\s+(.*)$", stripped)
        if m:
            story.append(Paragraph(f"•&nbsp;&nbsp;{_md_inline(m.group(1))}", bullet_style))
            continue
        m = re.match(r"^(\d+)[.)]\s+(.*)$", stripped)
        if m:
            story.append(Paragraph(f"{m.group(1)}.&nbsp;&nbsp;{_md_inline(m.group(2))}", bullet_style))
            continue
        story.append(Paragraph(_md_inline(stripped), body_style))


def _md_inline_docx(paragraph, text):
    """Add runs to a docx paragraph honouring bold/italic/code markdown."""
    tokens = re.split(r"(\*\*.+?\*\*|__.+?__|\*.+?\*|_.+?_|`.+?`)", text or "")
    for tok in tokens:
        if not tok:
            continue
        if (tok.startswith("**") and tok.endswith("**")) or (tok.startswith("__") and tok.endswith("__")):
            run = paragraph.add_run(tok[2:-2]); run.bold = True
        elif (tok.startswith("*") and tok.endswith("*")) or (tok.startswith("_") and tok.endswith("_")):
            run = paragraph.add_run(tok[1:-1]); run.italic = True
        elif tok.startswith("`") and tok.endswith("`"):
            run = paragraph.add_run(tok[1:-1]); run.font.name = "Consolas"
        else:
            paragraph.add_run(tok)


def _render_markdown_docx(docx, text):
    """Render a markdown answer into docx paragraphs (headings, lists, bold/italic)."""
    for raw in (text or "").split("\n"):
        stripped = raw.strip()
        if not stripped:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            _docx_add_heading(docx, m.group(2), size=12)
            continue
        m = re.match(r"^[-*•]\s+(.*)$", stripped)
        if m:
            _md_inline_docx(docx.add_paragraph(style="List Bullet"), m.group(1))
            continue
        m = re.match(r"^(\d+)[.)]\s+(.*)$", stripped)
        if m:
            _md_inline_docx(docx.add_paragraph(style="List Number"), m.group(2))
            continue
        _md_inline_docx(docx.add_paragraph(), stripped)


def _make_pdf_footer(firm_name):
    """Return an onPage callback that draws a letterhead footer with page numbers."""
    label = (firm_name or "TaxLens").strip()[:90]

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
        canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(18 * mm, 9 * mm, label)
        canvas.drawCentredString(A4[0] / 2, 9 * mm, "TaxLens · dokumen untuk berkas sengketa")
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Halaman {doc.page}")
        canvas.restoreState()

    return _footer


@api_router.post("/export/dasar-hukum")
async def export_dasar_hukum(payload: ExportRequest):
    document = await get_putusan(payload.document_id)
    paragraphs = paragraph_records(document["body"])
    paragraph_by_id = {item["id"]: item["text"] for item in paragraphs}
    peraturan_ids = [cite.peraturan_id for cite in payload.citations if cite.kind == "peraturan" and cite.peraturan_id]
    peraturan_docs = {}
    if peraturan_ids:
        for reg in await db.peraturan.find({"id": {"$in": peraturan_ids}}, {"_id": 0}).to_list(50):
            peraturan_docs[reg["id"]] = reg
    branding = await _get_branding()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm, title=f"Dasar Hukum - {document['title']}")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=4, textColor=colors.HexColor("#0f172a"))
    kicker = ParagraphStyle("Kicker", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.HexColor("#0f766e"), spaceAfter=2)
    firm_style = ParagraphStyle("Firm", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=colors.HexColor("#0f172a"))
    firm_small = ParagraphStyle("FirmSmall", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#475569"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#1e293b"))
    body = ParagraphStyle("Body", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=4, textColor=colors.HexColor("#1f2937"))
    small = ParagraphStyle("Small", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#64748b"))
    quote = ParagraphStyle("Quote", parent=body, leftIndent=10, borderPadding=6, backColor=colors.HexColor("#f8fafc"), borderColor=colors.HexColor("#e2e8f0"), borderWidth=0.5, spaceAfter=6)
    reg_quote = ParagraphStyle("RegQuote", parent=quote, backColor=colors.HexColor("#fff7ed"), borderColor=colors.HexColor("#fed7aa"))

    story = []
    _append_letterhead(story, branding, kicker, firm_style, firm_small, "TAXLENS · DASAR HUKUM JAWABAN AI")
    story.append(Paragraph(_escape_html(document["title"]), title_style))
    meta_table = Table([
        ["Jenis Sengketa", document.get("case_type", "-"), "Jenis Pajak", document.get("tax_type", "-")],
        ["Badan Peradilan", document.get("court", "-"), "Majelis", document.get("panel", "-")],
        ["Tahun", str(document.get("year", "-")), "Diekspor", datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")],
    ], colWidths=[32*mm, 50*mm, 32*mm, 50*mm])
    meta_table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748b")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#64748b")),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0")))

    story.append(Paragraph("1. Pertanyaan", h2))
    story.append(Paragraph(_escape_html(payload.question), body))

    story.append(Paragraph("2. Jawaban AI (GPT 5.6 Terra)", h2))
    _render_markdown_pdf(payload.answer, story, body, h2)

    para_cites = [c for c in payload.citations if c.kind != "peraturan"]
    reg_cites = [c for c in payload.citations if c.kind == "peraturan"]

    if para_cites:
        story.append(Paragraph("3. Kutipan Paragraf Putusan", h2))
        for cite in para_cites:
            full = paragraph_by_id.get(cite.id, cite.text)
            story.append(Paragraph(f"<b>[{_escape_html(cite.label)}]</b> {_escape_html(full)}", quote))

    if reg_cites:
        story.append(Paragraph("4. Dasar Peraturan yang Dirujuk", h2))
        for cite in reg_cites:
            reg = peraturan_docs.get(cite.peraturan_id)
            if reg:
                header = f"<b>{_escape_html(cite.label)}</b> — {_escape_html(reg['judul'])} <font color='#64748b'>({reg.get('status','Berlaku')})</font>"
                story.append(Paragraph(header, body))
                story.append(Paragraph(_escape_html(cite.text), reg_quote))
                if reg.get("source_url"):
                    story.append(Paragraph(f"Sumber: <font color='#2563eb'>{_escape_html(reg['source_url'])}</font>", small))
                story.append(Spacer(1, 4))
            else:
                story.append(Paragraph(f"<b>{_escape_html(cite.label)}</b> — {_escape_html(cite.text)}", quote))

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph(f"Dokumen ini dihasilkan otomatis oleh TaxLens AI pada {datetime.now(timezone.utc).strftime('%d %B %Y %H:%M UTC')}. Jawaban AI bersifat referensi analitik dan wajib diverifikasi terhadap peraturan serta putusan asli. Peraturan yang berstatus Dicabut dikecualikan dari dasar jawaban.", small))

    _footer = _make_pdf_footer(branding.get("firm_name"))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    buffer.seek(0)
    filename = f"dasar-hukum-{document.get('slug') or document['id']}.pdf"
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

def _docx_add_heading(doc, text, level=1, color="#1e293b", size=14):
    paragraph = doc.add_paragraph()
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color.lstrip("#"))
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.paragraph_format.space_after = Pt(4)
    return paragraph

@api_router.post("/export/dasar-hukum-docx")
async def export_dasar_hukum_docx(payload: ExportRequest):
    document = await get_putusan(payload.document_id)
    paragraphs = paragraph_records(document["body"])
    paragraph_by_id = {item["id"]: item["text"] for item in paragraphs}
    peraturan_ids = [c.peraturan_id for c in payload.citations if c.kind == "peraturan" and c.peraturan_id]
    peraturan_docs = {}
    if peraturan_ids:
        for reg in await db.peraturan.find({"id": {"$in": peraturan_ids}}, {"_id": 0}).to_list(50):
            peraturan_docs[reg["id"]] = reg
    branding = await _get_branding()

    docx = DocxDocument()
    for section in docx.sections:
        section.top_margin = Cm(2); section.bottom_margin = Cm(2); section.left_margin = Cm(2); section.right_margin = Cm(2)

    logo_buf = _decode_logo(branding.get("logo_base64"))
    if logo_buf:
        logo_para = docx.add_paragraph()
        try:
            logo_run = logo_para.add_run(); logo_run.add_picture(logo_buf, height=Cm(1.4))
        except Exception:
            pass
    firm_name = (branding.get("firm_name") or "").strip()
    if firm_name:
        fp = docx.add_paragraph(); fr = fp.add_run(firm_name); fr.bold = True; fr.font.size = Pt(12); fr.font.color.rgb = RGBColor.from_string("0F172A")
    firm_address = (branding.get("firm_address") or "").strip()
    if firm_address:
        ap = docx.add_paragraph(); ar = ap.add_run(firm_address); ar.font.size = Pt(9); ar.font.color.rgb = RGBColor.from_string("475569")
    firm_tagline = (branding.get("tagline") or "").strip()
    if firm_tagline:
        tp = docx.add_paragraph(); tr = tp.add_run(firm_tagline); tr.italic = True; tr.font.size = Pt(9); tr.font.color.rgb = RGBColor.from_string("475569")

    kicker = docx.add_paragraph(); run = kicker.add_run("TAXLENS · DASAR HUKUM JAWABAN AI"); run.bold = True; run.font.size = Pt(8); run.font.color.rgb = RGBColor.from_string("0F766E")
    title = docx.add_paragraph(); run = title.add_run(document["title"]); run.bold = True; run.font.size = Pt(16); run.font.color.rgb = RGBColor.from_string("0F172A")

    table = docx.add_table(rows=3, cols=4); table.style = "Light Grid Accent 1"
    rows_data = [["Jenis Sengketa", document.get("case_type", "-"), "Jenis Pajak", document.get("tax_type", "-")],
                 ["Badan Peradilan", document.get("court", "-"), "Majelis", document.get("panel", "-")],
                 ["Tahun", str(document.get("year", "-")), "Diekspor", datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")]]
    for row_idx, row in enumerate(rows_data):
        for col_idx, value in enumerate(row):
            cell = table.rows[row_idx].cells[col_idx]
            cell.text = str(value)
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(9)
                if col_idx in (0, 2):
                    run.font.color.rgb = RGBColor.from_string("64748B")
                else:
                    run.bold = True

    _docx_add_heading(docx, "1. Pertanyaan", size=12)
    docx.add_paragraph(payload.question)
    _docx_add_heading(docx, "2. Jawaban AI (GPT 5.6 Terra)", size=12)
    _render_markdown_docx(docx, payload.answer)

    para_cites = [c for c in payload.citations if c.kind != "peraturan"]
    reg_cites = [c for c in payload.citations if c.kind == "peraturan"]

    if para_cites:
        _docx_add_heading(docx, "3. Kutipan Paragraf Putusan", size=12)
        for cite in para_cites:
            full = paragraph_by_id.get(cite.id, cite.text)
            paragraph = docx.add_paragraph()
            label_run = paragraph.add_run(f"[{cite.label}] "); label_run.bold = True; label_run.font.color.rgb = RGBColor.from_string("1D4ED8")
            paragraph.add_run(full)
            paragraph.paragraph_format.left_indent = Cm(0.5)

    if reg_cites:
        _docx_add_heading(docx, "4. Dasar Peraturan yang Dirujuk", size=12)
        for cite in reg_cites:
            reg = peraturan_docs.get(cite.peraturan_id)
            header = docx.add_paragraph()
            label_run = header.add_run(cite.label); label_run.bold = True; label_run.font.color.rgb = RGBColor.from_string("B45309")
            if reg:
                header.add_run(f" — {reg['judul']} ({reg.get('status','Berlaku')})")
                quote = docx.add_paragraph(cite.text); quote.paragraph_format.left_indent = Cm(0.5)
                if reg.get("source_url"):
                    src = docx.add_paragraph(); src_run = src.add_run(f"Sumber: {reg['source_url']}"); src_run.font.size = Pt(8); src_run.font.color.rgb = RGBColor.from_string("64748B")
            else:
                header.add_run(f" — {cite.text}")

    footer = docx.add_paragraph(); run = footer.add_run(f"Dokumen ini dihasilkan otomatis oleh TaxLens AI pada {datetime.now(timezone.utc).strftime('%d %B %Y %H:%M UTC')}. Jawaban AI bersifat referensi analitik dan wajib diverifikasi. Peraturan Dicabut dikecualikan dari dasar jawaban."); run.font.size = Pt(8); run.font.color.rgb = RGBColor.from_string("64748B")

    buffer = BytesIO(); docx.save(buffer); buffer.seek(0)
    filename = f"dasar-hukum-{document.get('slug') or document['id']}.docx"
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

class BookmarkFlowable(Flowable):
    def __init__(self, key, title, level=0):
        super().__init__(); self.key = key; self.title_text = title; self.level = level
    def wrap(self, w, h):
        return (0, 0)
    def draw(self):
        self.canv.bookmarkPage(self.key)
        self.canv.addOutlineEntry(self.title_text, self.key, level=self.level, closed=False)

@api_router.post("/export/bundel")
async def export_bundel(payload: ExportRequest):
    document = await get_putusan(payload.document_id)
    paragraphs = paragraph_records(document["body"])
    peraturan_ids = [c.peraturan_id for c in payload.citations if c.kind == "peraturan" and c.peraturan_id]
    peraturan_docs = []
    if peraturan_ids:
        peraturan_docs = await db.peraturan.find({"id": {"$in": peraturan_ids}}, {"_id": 0}).to_list(50)
    related = []
    for reg in peraturan_docs:
        try:
            related_resp = await peraturan_related_putusan(reg["id"])
            related.append((reg, related_resp.get("putusan", [])))
        except Exception:
            related.append((reg, []))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm, title=f"Bundel - {document['title']}")
    styles = getSampleStyleSheet()
    kicker = ParagraphStyle("K", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, textColor=colors.HexColor("#0f766e"), spaceAfter=2)
    cover_title = ParagraphStyle("CT", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=colors.HexColor("#0f172a"), spaceAfter=10)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=15, leading=19, spaceBefore=8, spaceAfter=10, textColor=colors.HexColor("#0f172a"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=10, spaceAfter=5, textColor=colors.HexColor("#1e293b"))
    body = ParagraphStyle("Body", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=4, textColor=colors.HexColor("#1f2937"))
    small = ParagraphStyle("Small", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#64748b"))
    quote = ParagraphStyle("Quote", parent=body, leftIndent=10, borderPadding=6, backColor=colors.HexColor("#f8fafc"), borderColor=colors.HexColor("#e2e8f0"), borderWidth=0.5, spaceAfter=5)
    firm_style = ParagraphStyle("Firm", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=colors.HexColor("#0f172a"))
    firm_small = ParagraphStyle("FirmSmall", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#475569"))
    branding = await _get_branding()

    story = []
    # Cover
    story.append(BookmarkFlowable("cover", "Sampul & Jawaban AI", level=0))
    _append_letterhead(story, branding, kicker, firm_style, firm_small, "TAXLENS · BUNDEL PENELITIAN PAJAK")
    story.append(Paragraph("Dasar Hukum & Yurisprudensi", cover_title))
    story.append(Paragraph(_escape_html(document["title"]), h1))
    story.append(Paragraph(f"<b>Jenis Sengketa:</b> {document.get('case_type','-')} &nbsp;·&nbsp; <b>Jenis Pajak:</b> {document.get('tax_type','-')} &nbsp;·&nbsp; <b>Tahun:</b> {document.get('year','-')}", body))
    story.append(Paragraph(f"<b>Badan Peradilan:</b> {document.get('court','-')} &nbsp;·&nbsp; <b>Majelis:</b> {document.get('panel','-')}", body))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph("Pertanyaan", h2))
    story.append(Paragraph(_escape_html(payload.question), body))
    story.append(Paragraph("Jawaban AI (GPT 5.6 Terra)", h2))
    _render_markdown_pdf(payload.answer, story, body, h2)

    # Putusan utama
    story.append(PageBreak())
    story.append(BookmarkFlowable("putusan", "Putusan Utama", level=0))
    story.append(Paragraph("PUTUSAN UTAMA", kicker))
    story.append(Paragraph(_escape_html(document["title"]), h1))
    if document.get("summary"):
        story.append(Paragraph(f"<i>{_escape_html(document['summary'])}</i>", small))
        story.append(Spacer(1, 6))
    for item in paragraphs:
        story.append(Paragraph(f"<b>[{item['id']}]</b> {_escape_html(item['text'])}", body))
    if document.get("source_url"):
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Sumber: <font color='#2563eb'>{_escape_html(document['source_url'])}</font>", small))

    # Peraturan dasar
    if peraturan_docs:
        story.append(PageBreak())
        story.append(BookmarkFlowable("peraturan", "Peraturan Dasar", level=0))
        story.append(Paragraph("PERATURAN DASAR YANG DIRUJUK", kicker))
        story.append(Paragraph("Dasar Hukum", h1))
        for idx, reg in enumerate(peraturan_docs):
            key = f"reg-{idx}"
            story.append(BookmarkFlowable(key, f"{reg['jenis']} {reg['nomor']} — {reg['judul'][:80]}", level=1))
            story.append(Paragraph(f"{_escape_html(reg['jenis'])} {_escape_html(reg['nomor'])} <font color='#64748b'>· {reg.get('status','Berlaku')}</font>", h2))
            story.append(Paragraph(_escape_html(reg['judul']), body))
            story.append(Paragraph(f"<b>Tahun:</b> {reg.get('tahun','-')} &nbsp;·&nbsp; <b>Berlaku sejak:</b> {reg.get('tanggal_berlaku') or '-'}", small))
            story.append(Spacer(1, 4))
            for line in reg["body"].split("\n"):
                if line.strip():
                    story.append(Paragraph(_escape_html(line), quote))
            if reg.get("source_url"):
                story.append(Paragraph(f"Sumber: <font color='#2563eb'>{_escape_html(reg['source_url'])}</font>", small))
            story.append(Spacer(1, 8))

    # Yurisprudensi
    if related:
        story.append(PageBreak())
        story.append(BookmarkFlowable("yurisprudensi", "Yurisprudensi Terkait", level=0))
        story.append(Paragraph("YURISPRUDENSI TERKAIT", kicker))
        story.append(Paragraph("Putusan yang Merujuk Peraturan Dasar", h1))
        for reg, items in related:
            story.append(Paragraph(f"<b>{_escape_html(reg['jenis'])} {_escape_html(reg['nomor'])}</b> — {_escape_html(reg['judul'][:120])}", h2))
            if not items:
                story.append(Paragraph("<i>Belum ada putusan dalam katalog yang merujuk peraturan ini.</i>", small))
                continue
            for item in items:
                story.append(Paragraph(f"<b>{_escape_html(item['title'])}</b> — {_escape_html(item.get('tax_type','-'))} · {item.get('year','-')} · {_escape_html(item.get('case_type','-'))} · {item.get('match_count',0)}× dirujuk", body))

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph(f"Bundel ini dihasilkan otomatis oleh TaxLens AI pada {datetime.now(timezone.utc).strftime('%d %B %Y %H:%M UTC')}. Peraturan berstatus Dicabut tidak dimasukkan sebagai dasar hukum. Jawaban AI wajib diverifikasi terhadap dokumen asli.", small))

    _footer = _make_pdf_footer(branding.get("firm_name"))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    buffer.seek(0)
    filename = f"bundel-penelitian-{document.get('slug') or document['id']}.pdf"
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@api_router.post("/export/bundel-docx")
async def export_bundel_docx(payload: ExportRequest):
    document = await get_putusan(payload.document_id)
    paragraphs = paragraph_records(document["body"])
    peraturan_ids = [c.peraturan_id for c in payload.citations if c.kind == "peraturan" and c.peraturan_id]
    peraturan_docs = []
    if peraturan_ids:
        peraturan_docs = await db.peraturan.find({"id": {"$in": peraturan_ids}}, {"_id": 0}).to_list(50)
    related = []
    for reg in peraturan_docs:
        try:
            related_resp = await peraturan_related_putusan(reg["id"])
            related.append((reg, related_resp.get("putusan", [])))
        except Exception:
            related.append((reg, []))
    branding = await _get_branding()

    docx = DocxDocument()
    for section in docx.sections:
        section.top_margin = Cm(2); section.bottom_margin = Cm(2); section.left_margin = Cm(2); section.right_margin = Cm(2)

    logo_buf = _decode_logo(branding.get("logo_base64"))
    if logo_buf:
        logo_para = docx.add_paragraph()
        try:
            logo_para.add_run().add_picture(logo_buf, height=Cm(1.4))
        except Exception:
            pass
    firm_name = (branding.get("firm_name") or "").strip()
    if firm_name:
        p = docx.add_paragraph(); r = p.add_run(firm_name); r.bold = True; r.font.size = Pt(12); r.font.color.rgb = RGBColor.from_string("0F172A")
    firm_address = (branding.get("firm_address") or "").strip()
    if firm_address:
        p = docx.add_paragraph(); r = p.add_run(firm_address); r.font.size = Pt(9); r.font.color.rgb = RGBColor.from_string("475569")
    firm_tagline = (branding.get("tagline") or "").strip()
    if firm_tagline:
        p = docx.add_paragraph(); r = p.add_run(firm_tagline); r.italic = True; r.font.size = Pt(9); r.font.color.rgb = RGBColor.from_string("475569")

    p = docx.add_paragraph(); r = p.add_run("TAXLENS · BUNDEL PENELITIAN PAJAK"); r.bold = True; r.font.size = Pt(8); r.font.color.rgb = RGBColor.from_string("0F766E")
    p = docx.add_paragraph(); r = p.add_run("Dasar Hukum & Yurisprudensi"); r.bold = True; r.font.size = Pt(20); r.font.color.rgb = RGBColor.from_string("0F172A")
    p = docx.add_paragraph(); r = p.add_run(document["title"]); r.bold = True; r.font.size = Pt(14); r.font.color.rgb = RGBColor.from_string("0F172A")
    meta = docx.add_paragraph()
    meta.add_run(f"Jenis Sengketa: {document.get('case_type','-')}  ·  Jenis Pajak: {document.get('tax_type','-')}  ·  Tahun: {document.get('year','-')}\n")
    meta.add_run(f"Badan Peradilan: {document.get('court','-')}  ·  Majelis: {document.get('panel','-')}")
    for run in meta.runs:
        run.font.size = Pt(9); run.font.color.rgb = RGBColor.from_string("475569")

    _docx_add_heading(docx, "Pertanyaan", size=12)
    docx.add_paragraph(payload.question)
    _docx_add_heading(docx, "Jawaban AI (GPT 5.6 Terra)", size=12)
    _render_markdown_docx(docx, payload.answer)

    docx.add_page_break()
    _docx_add_heading(docx, "Putusan Utama", size=15, color="#0F172A")
    p = docx.add_paragraph(); r = p.add_run(document["title"]); r.bold = True; r.font.size = Pt(12)
    if document.get("summary"):
        p = docx.add_paragraph(); r = p.add_run(document["summary"]); r.italic = True; r.font.size = Pt(9); r.font.color.rgb = RGBColor.from_string("64748B")
    for item in paragraphs:
        para = docx.add_paragraph()
        lbl = para.add_run(f"[{item['id']}] "); lbl.bold = True; lbl.font.color.rgb = RGBColor.from_string("1D4ED8")
        para.add_run(item["text"])
    if document.get("source_url"):
        p = docx.add_paragraph(); r = p.add_run(f"Sumber: {document['source_url']}"); r.font.size = Pt(8); r.font.color.rgb = RGBColor.from_string("64748B")

    if peraturan_docs:
        docx.add_page_break()
        _docx_add_heading(docx, "Dasar Hukum", size=15, color="#0F172A")
        for reg in peraturan_docs:
            p = docx.add_paragraph(); r = p.add_run(f"{reg['jenis']} {reg['nomor']} · {reg.get('status','Berlaku')}"); r.bold = True; r.font.size = Pt(12); r.font.color.rgb = RGBColor.from_string("1E293B")
            docx.add_paragraph(reg["judul"])
            p = docx.add_paragraph(); r = p.add_run(f"Tahun: {reg.get('tahun','-')}  ·  Berlaku sejak: {reg.get('tanggal_berlaku') or '-'}"); r.font.size = Pt(9); r.font.color.rgb = RGBColor.from_string("64748B")
            for line in (reg.get("body") or "").split("\n"):
                if line.strip():
                    q = docx.add_paragraph(line); q.paragraph_format.left_indent = Cm(0.5)
            if reg.get("source_url"):
                p = docx.add_paragraph(); r = p.add_run(f"Sumber: {reg['source_url']}"); r.font.size = Pt(8); r.font.color.rgb = RGBColor.from_string("64748B")

    if related:
        docx.add_page_break()
        _docx_add_heading(docx, "Yurisprudensi Terkait", size=15, color="#0F172A")
        for reg, items in related:
            p = docx.add_paragraph(); r = p.add_run(f"{reg['jenis']} {reg['nomor']} — {reg['judul'][:120]}"); r.bold = True; r.font.size = Pt(11); r.font.color.rgb = RGBColor.from_string("1E293B")
            if not items:
                p = docx.add_paragraph(); r = p.add_run("Belum ada putusan dalam katalog yang merujuk peraturan ini."); r.italic = True; r.font.size = Pt(9); r.font.color.rgb = RGBColor.from_string("64748B")
                continue
            for item in items:
                docx.add_paragraph(
                    f"{item['title']} — {item.get('tax_type','-')} · {item.get('year','-')} · {item.get('case_type','-')} · {item.get('match_count',0)}× dirujuk",
                    style="List Bullet",
                )

    footer = docx.add_paragraph(); r = footer.add_run(f"Bundel ini dihasilkan otomatis oleh TaxLens AI pada {datetime.now(timezone.utc).strftime('%d %B %Y %H:%M UTC')}. Peraturan berstatus Dicabut tidak dimasukkan sebagai dasar hukum. Jawaban AI wajib diverifikasi terhadap dokumen asli."); r.font.size = Pt(8); r.font.color.rgb = RGBColor.from_string("64748B")

    buffer = BytesIO(); docx.save(buffer); buffer.seek(0)
    filename = f"bundel-penelitian-{document.get('slug') or document['id']}.docx"
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks

class AiSearchRequest(BaseModel):
    q: str


@api_router.get("/search")
async def web_search_endpoint(
    q: str = Query(..., min_length=1, max_length=400),
    page: int = Query(1, ge=1, le=10),
    page_size: int = Query(10, ge=1, le=20),
    type: str = Query("web"),
):
    """Real-time web search engine (Gemini Google Search grounding)."""
    kind = type if type in ("web", "news", "pdf") else "web"
    started = time.perf_counter()
    try:
        data = await web_search_module.web_search(q.strip(), kind=kind)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("web search failed")
        raise HTTPException(status_code=502, detail="Pencarian web gagal. Coba lagi.")
    all_results = data["results"]
    total = len(all_results)
    start = (page - 1) * page_size
    end = start + page_size
    page_results = all_results[start:end]
    elapsed = round(time.perf_counter() - started, 2)
    return {
        "query": q,
        "type": kind,
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": max(1, (total + page_size - 1) // page_size),
        "searchTime": elapsed,
        "results": page_results,
    }


@api_router.post("/ai-search")
async def ai_search_endpoint(payload: AiSearchRequest):
    """AI answer grounded on real web sources, with citations."""
    question = (payload.q or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Pertanyaan tidak boleh kosong.")
    started = time.perf_counter()
    try:
        data = await web_search_module.ai_search(question)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("ai search failed")
        raise HTTPException(status_code=502, detail="AI Search gagal. Coba lagi.")
    return {
        "query": question,
        "answer": data["answer"],
        "sources": data["sources"],
        "searchTime": round(time.perf_counter() - started, 2),
    }


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def seed_peraturan():
    try:
        object_storage.init_storage()
        logger.info("Object storage initialized")
    except Exception as exc:
        logger.error("Object storage init failed: %s", exc)
    now_iso = datetime.now(timezone.utc).isoformat()
    for reg in SAMPLE_PERATURAN:
        existing = await db.peraturan.find_one({"id": reg["id"]}, {"_id": 0})
        if existing is None:
            await db.peraturan.insert_one({**reg, "created_at": now_iso})
    for put in [SAMPLE_PUTUSAN, *EXTRA_SAMPLE_PUTUSAN]:
        existing = await db.putusan.find_one({"id": put["id"]}, {"_id": 0})
        if existing is None:
            await db.putusan.insert_one(put.copy())
    logger.info("Peraturan & putusan samples ensured in database")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()