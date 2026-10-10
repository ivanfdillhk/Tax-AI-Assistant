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

## Update (2026-10) — chat formatting
- AI assistant answers previously showed raw markdown `**bold**` as literal asterisks. Added `renderRich()` in `App.js` that renders `**bold**` as <strong>, strips stray `*` / backticks / leading `#`, and preserves line breaks. Verified visually: no visible asterisks, citations ([P4] etc.) intact.

## Update (2026-10) — 4 enhancements
1. **Teks lengkap dari sumber**: new `POST /api/peraturan/{id}/refetch` re-fetches full text from the peraturan's `source_url` (shared `_fetch_document_from_url`: lxml HTML + follow PDF link) and updates body + original file. Frontend button "Ambil teks lengkap dari sumber" in peraturan detail. NOTE: peraturan.go.id blocks server-side fetch (502, Cloudflare/JS) — works for direct PDF / JDIH-download URLs and uploads; peraturan.go.id itself is not server-fetchable.
2. **List rapi**: `renderRich()` now renders numbered/bulleted lines as real `<ol>/<ul>`, paragraphs otherwise; message wrapper changed `<p>`→`<div class=msg-body>`.
3. **Salin jawaban**: copy button per assistant message (`copyAnswer` → clipboard, strips `**`).
4. **Bersihkan data contoh**: `DELETE /api/peraturan/{id}` & `DELETE /api/putusan/{id}` with `db.seed_deletions` tombstones so deleted samples don't re-seed; trash buttons on catalog list items, peraturan detail, and both Database-page columns.
- `import_public_url` refactored to use shared `_fetch_document_from_url` (behavior unchanged). Backend tested: 10/10 passed.



## Re-import (2026-10)
- Re-imported repo (main) — /app code identical to repo. Backend deps installed (rest of requirements separately; litellm 1.80.0 + emergentintegrations 0.2.2 present). Frontend `yarn install` OK (cleared corrupt es-abstract yarn cache).
- Backend/frontend running; DB seeded; PDF upload OK.
- Web search & AI Search return 502: EMERGENT_LLM_KEY budget exceeded (not a code bug) — user must top up Universal Key balance.
