# Tax AI Assistant (TaxLens) — PRD

## Original Problem Statement
Import the `Tax-AI-Assistant` repo (FastAPI + MongoDB + React) from GitHub into Emergent, install all dependencies, and make it actually run end-to-end (not just install-then-error). Smoke test web search, AI search, and PDF upload/download.

## Architecture
- **Frontend**: Create React App + CRACO + Tailwind + shadcn, yarn. Single-page `App.js`. Uses `REACT_APP_BACKEND_URL` for all `/api` calls.
- **Backend**: FastAPI (`server.py`), MongoDB via `motor`. PDF/DOCX parsing (pdfplumber/pypdf/python-docx). `storage.py` = Emergent Object Storage. `web_search.py` = Gemini Google Search grounding via `EMERGENT_LLM_KEY`.
- **Database**: Local MongoDB in Emergent, `DB_NAME=taxai`. Seeds sample peraturan + putusan on startup.

## Setup done (2026-06)
- Cloned repo `ivanfdillhk/Tax-AI-Assistant` (branch main) into `/app`.
- Created `backend/.env` (MONGO_URL local, DB_NAME=taxai, CORS_ORIGINS=*, EMERGENT_LLM_KEY) and used existing `frontend/.env`.
- Installed backend deps (resolved litellm/emergentintegrations whl conflict by installing the rest separately; both already present). `yarn install` for frontend.
- Backend healthy: object storage initialized, Mongo seeded.

## Verified flows
- Web search `/api/search` → real grounded results (7).
- AI search `/api/ai-search` (body `{q}`) → ~3.2k char answer + 3 citations.
- PDF upload `/api/putusan/upload` → metadata extracted → stored in object storage + Mongo; download `/api/files/{id}/download` returns valid PDF.
- pytest: 25 passed (with REACT_APP_BACKEND_URL exported).
- Frontend testing agent: all 6 UI flows pass 100%.

## Fixes applied
- `App.js goToDatabase()`: reset shared `query` state (and pass empty query override to `loadDatabase`) so switching Knowledge→Database no longer shows an empty DB from a stale query.

## Backlog (not blocking)
- P2: Native `<select>` on Database page overlaps putusan rows — consider shadcn Select.
- P2: Several API calls (loadDocument, compareDocuments, sendQuestion, loadPeraturan) swallow errors silently — add toasts.
- P2: `App.js` is large; could split into KnowledgeView/DatabaseView/PutusanView.

## Notes
- No authentication in this app.
- Running inside Emergent → EMERGENT_LLM_KEY + Object Storage auto-available.

## Update (2026-10) — 3 feature fixes
1. **Compare Decision (side-by-side)**: 'Bandingkan sekarang' now closes the modal and opens a full-page view (`view==='compare'`) with two columns: metadata (diff-highlighted), Amar Putusan (verdict), and full Pertimbangan Hukum/body. Compare modal has two selects (first + second). Backend `/api/putusan/compare` unchanged. Verified visually by main agent.
2. **Full PDF text extraction**: `_extract_pdf_structured` hardened against false-positive table detection (genuine tables need ≥2 rows & ≥2 cols; table-dominated pages kept as plain text; empty-filter fallback; final completeness safety net vs `_extract_pdf_plain`). Body cap raised 120k→2M chars. URL import now uses lxml (`_extract_html_text`) + follows a PDF link (`_find_pdf_url`) to grab the full document and save the original file. Backend tested 3/3.
3. **PDF viewer (CORS)**: new `GET /api/pdf-proxy?url=&inline=1` streams external PDFs server-side (bypasses source CORS/X-Frame-Options). Frontend PDF tab priority: stored file → proxy(source_url if .pdf) → generated PDF. Backend tested 4/4.
- Backend testing: all 9 tests passed.

