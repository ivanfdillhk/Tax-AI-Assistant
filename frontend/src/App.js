import { useEffect, useState } from "react";
import "@/App.css";
import { BrowserRouter } from "react-router-dom";
import axios from "axios";
import { ArrowUpRight, BookOpen, BrainCircuit, Cloud, ChevronLeft, Copy, Download, Eye, FileText, FileUp, FolderOpen, Gavel, ImagePlus, Link2, RefreshCw, Scale, Search, Send, Settings, Sparkles, Trash2, X, GitCompareArrows } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const isPdfFile = (name) => (name || "").toLowerCase().endsWith(".pdf");
const fileInlineUrl = (fileId) => `${API}/files/${fileId}/download?inline=1`;
const putusanPdfUrl = (id, inline = true) => `${API}/putusan/${id}/pdf${inline ? "?inline=1" : ""}`;
const peraturanPdfUrl = (id, inline = true) => `${API}/peraturan/${id}/pdf${inline ? "?inline=1" : ""}`;
const looksLikePdfUrl = (u) => /\.pdf(\?|#|$)/i.test(u || "");
const pdfProxyUrl = (u) => `${API}/pdf-proxy?inline=1&url=${encodeURIComponent(u || "")}`;
// Resolve the best source URL for a document's PDF tab:
// 1) stored original file (same-origin), 2) external PDF via backend proxy, 3) server-generated PDF.
const putusanPdfTabUrl = (doc) =>
  doc.file_id && isPdfFile(doc.original_filename) ? fileInlineUrl(doc.file_id)
  : looksLikePdfUrl(doc.source_url) ? pdfProxyUrl(doc.source_url)
  : putusanPdfUrl(doc.id);
const peraturanPdfTabUrl = (doc) =>
  doc.file_id && isPdfFile(doc.original_filename) ? fileInlineUrl(doc.file_id)
  : looksLikePdfUrl(doc.source_url) ? pdfProxyUrl(doc.source_url)
  : peraturanPdfUrl(doc.id);

// Render assistant text: **bold** -> <strong> (no visible asterisks), numbered/bulleted
// lines -> proper <ol>/<ul> lists, other lines -> paragraphs; strips stray markdown markers.
const parseInline = (str, kp) => {
  const segs = str.split(/(\*\*[^*]+\*\*)/g).filter((s) => s !== "");
  return segs.map((seg, i) =>
    seg.startsWith("**") && seg.endsWith("**")
      ? <strong key={`${kp}-b${i}`}>{seg.slice(2, -2)}</strong>
      : <span key={`${kp}-s${i}`}>{seg.replace(/\*/g, "")}</span>
  );
};
const renderRich = (text) => {
  const clean = (text || "").replace(/`+/g, "").replace(/^\s{0,3}#{1,6}\s*/gm, "");
  const lines = clean.split("\n");
  const blocks = [];
  let list = null;
  const flush = () => { if (list) { blocks.push(list); list = null; } };
  lines.forEach((raw) => {
    const line = raw.trimEnd();
    const om = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    const um = line.match(/^\s*[-*•·]\s+(.*)$/);
    if (om) {
      if (!list || list.type !== "ol") { flush(); list = { type: "ol", items: [] }; }
      list.items.push(om[2]);
    } else if (um) {
      if (!list || list.type !== "ul") { flush(); list = { type: "ul", items: [] }; }
      list.items.push(um[1]);
    } else {
      flush();
      if (line.trim()) blocks.push({ type: "p", text: line });
    }
  });
  flush();
  return blocks.map((b, bi) => {
    if (b.type === "ol") return <ol className="msg-list msg-ol" key={bi}>{b.items.map((it, ii) => <li key={ii}>{parseInline(it, `${bi}-${ii}`)}</li>)}</ol>;
    if (b.type === "ul") return <ul className="msg-list msg-ul" key={bi}>{b.items.map((it, ii) => <li key={ii}>{parseInline(it, `${bi}-${ii}`)}</li>)}</ul>;
    return <p className="msg-para" key={bi}>{parseInline(b.text, bi)}</p>;
  });
};
const plainAnswer = (t) => (t || "").replace(/\*\*/g, "").replace(/`+/g, "");

const PdfFrame = ({ url, testId }) => {
  const [blobUrl, setBlobUrl] = useState("");
  const [status, setStatus] = useState("loading");
  useEffect(() => {
    let active = true; let created = "";
    setStatus("loading"); setBlobUrl("");
    axios.get(url, { responseType: "blob" })
      .then((res) => {
        if (!active) return;
        created = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
        setBlobUrl(created); setStatus("ready");
      })
      .catch(() => { if (active) setStatus("error"); });
    return () => { active = false; if (created) URL.revokeObjectURL(created); };
  }, [url]);
  if (status === "loading") return <div className="pdf-loading" data-testid={`${testId}-loading`}>Memuat PDF…</div>;
  if (status === "error") return <div className="pdf-error" data-testid={`${testId}-error`}>Gagal menampilkan PDF di dalam aplikasi. <a href={url} target="_blank" rel="noreferrer">Buka PDF di tab baru</a></div>;
  return <iframe title="PDF" src={blobUrl} data-testid={testId} />;
};

const Home = () => {
  const [document, setDocument] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [peraturanResults, setPeraturanResults] = useState([]);
  const [perFilter, setPerFilter] = useState({ jenis: "", status: "" });
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState({ year: "", tax_type: "", case_type: "" });
  const [putusanFacets, setPutusanFacets] = useState({ years: [], caseTypes: [] });
  const [docTab, setDocTab] = useState("teks");
  const [perDocTab, setPerDocTab] = useState("teks");
  const [previewPdf, setPreviewPdf] = useState(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([{ role: "assistant", text: "Saya siap membantu membaca putusan ini. Tanyakan dasar pertimbangan, isu PPN, atau amar putusannya.", citations: [] }]);
  const [loading, setLoading] = useState(false);
  const [mobileChat, setMobileChat] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareId, setCompareId] = useState("");
  const [compareFirstId, setCompareFirstId] = useState("");
  const [enrichingId, setEnrichingId] = useState("");
  const [comparison, setComparison] = useState(null);
  const [importStatus, setImportStatus] = useState("");
  const [urlOpen, setUrlOpen] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [importingUrl, setImportingUrl] = useState(false);
  const [peraturanOpen, setPeraturanOpen] = useState(false);
  const [peraturanList, setPeraturanList] = useState([]);
  const [peraturanActive, setPeraturanActive] = useState(null);
  const [peraturanFilters, setPeraturanFilters] = useState({ q: "", jenis: "", tahun: "" });
  const [peraturanStatus, setPeraturanStatus] = useState("");
  const [peraturanUrl, setPeraturanUrl] = useState("");
  const [peraturanRelated, setPeraturanRelated] = useState([]);
  const [brandingOpen, setBrandingOpen] = useState(false);
  const [branding, setBranding] = useState({ firm_name: "", firm_address: "", tagline: "", logo_base64: null });
  const [brandingSaving, setBrandingSaving] = useState(false);
  const [savedIds, setSavedIds] = useState(() => { try { return JSON.parse(window.localStorage.getItem("taxlens-saved") || "[]"); } catch { return []; } });
  const [toastMsg, setToastMsg] = useState("");
  const [externalOpen, setExternalOpen] = useState(false);
  const [externalLinks, setExternalLinks] = useState("");
  const [externalKind, setExternalKind] = useState("putusan");
  const [externalPreviews, setExternalPreviews] = useState([]); // {url, provider, filename, size_kb, detected_format, status, error}
  const [externalBusy, setExternalBusy] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const [files, setFiles] = useState([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [view, setView] = useState("knowledge");
  const [searchMode, setSearchMode] = useState("web"); // "web" | "ai"
  const [webType, setWebType] = useState("web"); // "web" | "news" | "pdf"
  const [webData, setWebData] = useState(null);
  const [webLoading, setWebLoading] = useState(false);
  const [aiData, setAiData] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [lastQuery, setLastQuery] = useState("");

  const loadDocument = async (id = "put-004106-2020", switchView = true) => {
    try { const response = await axios.get(`${API}/putusan/${id}`); setDocument(response.data); setCompareId(""); setComparison(null); if (switchView) setView("putusan"); setSearchOpen(false); setMobileChat(false); }
    catch (_) { setMessages([{ role: "assistant", text: "Dokumen belum dapat dimuat. Silakan coba lagi.", citations: [] }]); }
  };
  const runSearch = async (perOverride) => {
    const per = perOverride || perFilter;
    const [putusanRes, peraturanRes] = await Promise.all([
      axios.get(`${API}/putusan`, { params: { q: query || undefined, year: filters.year || undefined } }),
      axios.get(`${API}/peraturan`, { params: { q: query || undefined, tahun: filters.year || undefined, jenis: per.jenis || undefined, status: per.status || undefined } }).catch(() => ({ data: [] })),
    ]);
    setDocuments(putusanRes.data); setPeraturanResults(peraturanRes.data); setSearchOpen(true);
  };
  const searchDocuments = () => runSearch();
  const applyPerFilter = (patch) => { const next = { ...perFilter, ...patch }; setPerFilter(next); runSearch(next); };
  const runWebSearch = async (q, page = 1, type = webType) => {
    const qq = (q !== undefined ? q : query).trim();
    if (!qq) return;
    setLastQuery(qq); setSearchError(""); setAiData(null); setWebLoading(true);
    try {
      const response = await axios.get(`${API}/search`, { params: { q: qq, page, type } });
      setWebData(response.data);
    } catch (e) {
      setWebData(null);
      setSearchError(e?.response?.data?.detail || "Pencarian web gagal. Silakan coba lagi.");
    } finally { setWebLoading(false); }
  };
  const runAiSearch = async (q) => {
    const qq = (q !== undefined ? q : query).trim();
    if (!qq) return;
    setLastQuery(qq); setSearchError(""); setWebData(null); setAiLoading(true);
    try {
      const response = await axios.post(`${API}/ai-search`, { q: qq });
      setAiData(response.data);
    } catch (e) {
      setAiData(null);
      setSearchError(e?.response?.data?.detail || "AI Search gagal. Silakan coba lagi.");
    } finally { setAiLoading(false); }
  };
  const submitSearch = (q) => {
    const qq = q !== undefined ? q : query;
    if (q !== undefined) setQuery(q);
    if (searchMode === "ai") runAiSearch(qq); else runWebSearch(qq, 1, webType);
  };
  const changeWebType = (t) => { setWebType(t); if ((query || lastQuery).trim()) runWebSearch(query || lastQuery, 1, t); };
  const gotoPage = (p) => runWebSearch(lastQuery || query, p, webType);
  const renderAiAnswer = (answer, sources) => {
    const tokens = (answer || "").split(/(\[\d+\]|\*\*[^*]+\*\*)/g);
    return tokens.map((part, i) => {
      const cite = part.match(/^\[(\d+)\]$/);
      if (cite) {
        const num = parseInt(cite[1], 10);
        const src = (sources || []).find((s) => s.number === num);
        if (src) return <a key={i} className="ai-cite" href={src.url} target="_blank" rel="noreferrer" title={src.title}>{num}</a>;
        return <sup key={i} className="ai-cite ai-cite-dead">{num}</sup>;
      }
      const bold = part.match(/^\*\*([^*]+)\*\*$/);
      if (bold) return <strong key={i}>{bold[1]}</strong>;
      return <span key={i}>{part.replace(/\*/g, "").replace(/^[ \t]*#{1,6}[ \t]*/gm, "")}</span>;
    });
  };
  const renderAiSource = (s) => (
    <a className="ai-source" href={s.url} target="_blank" rel="noreferrer" data-testid={`ai-source-${s.number}`} key={s.number}>
      <span className="ai-source-num">{s.number}</span>
      {s.favicon ? <img className="web-favicon" src={s.favicon} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} /> : null}
      <span className="ai-source-text"><strong>{s.title}</strong><span>{s.displayUrl}</span></span>
      <ArrowUpRight size={14} />
    </a>
  );
  const goToKnowledge = () => { setView("knowledge"); setSearchOpen(false); setPeraturanOpen(false); };
  const loadDatabase = async (filterOverride, queryOverride) => {
    const f = filterOverride || filters;
    const q = queryOverride !== undefined ? queryOverride : query;
    try {
      const [putusanRes, peraturanRes] = await Promise.all([
        axios.get(`${API}/putusan`, { params: { q: q || undefined, year: f.year || undefined, case_type: f.case_type || undefined } }),
        axios.get(`${API}/peraturan`, { params: { q: q || undefined, jenis: perFilter.jenis || undefined, status: perFilter.status || undefined } }).catch(() => ({ data: [] })),
      ]);
      setDocuments(putusanRes.data); setPeraturanResults(peraturanRes.data);
    } catch (_) { /* keep previous data on failure */ }
  };
  const loadPutusanFacets = async () => {
    try {
      const res = await axios.get(`${API}/putusan`);
      const years = [...new Set(res.data.map((d) => d.year).filter((y) => y !== null && y !== undefined))].sort((a, b) => b - a);
      const caseTypes = [...new Set(res.data.map((d) => d.case_type).filter(Boolean))].sort();
      setPutusanFacets({ years, caseTypes });
    } catch (_) { /* ignore */ }
  };
  const applyDbPutusanFilter = (patch) => { const next = { ...filters, ...patch }; setFilters(next); loadDatabase(next); };
  const goToDatabase = () => { setView("database"); setSearchOpen(false); setPeraturanOpen(false); setQuery(""); loadPutusanFacets(); loadDatabase(null, ""); };
  useEffect(() => { loadDocument(undefined, false); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    axios.get(`${API}/branding`).then((response) => setBranding((prev) => ({ ...prev, ...response.data }))).catch(() => {});
  }, []);

  const sendQuestion = async (event) => {
    event.preventDefault(); if (!question.trim() || loading) return;
    const current = question.trim(); setQuestion(""); setMessages((items) => [...items, { role: "user", text: current }, { role: "assistant", text: "", citations: [] }]); setLoading(true);
    try {
      const response = await fetch(`${API}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: current, document_id: document.id }) });
      if (!response.ok || !response.body) throw new Error("Chat request failed");
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let answer = ""; let citations = [];
      while (true) {
        const { value, done } = await reader.read(); if (done) break;
        decoder.decode(value).split("\n\n").forEach((line) => { if (line.startsWith("data: ")) { try { const data = JSON.parse(line.slice(6)); if (data.type === "token") answer += data.content; if (data.type === "done") citations = data.citations || []; } catch (_) {} } });
        setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, text: answer, citations } : item));
      }
    } catch (_) { setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, text: "Maaf, asisten sedang tidak tersedia.", citations: [] } : item)); }
    finally { setLoading(false); }
  };

  const importFile = async (event) => {
    const file = event.target.files?.[0]; if (!file) return;
    setImportStatus("Mengekstrak dokumen…"); const form = new FormData(); form.append("file", file);
    try { const response = await fetch(`${API}/putusan/upload`, { method: "POST", body: form }); const imported = await response.json(); if (!response.ok) throw new Error(imported.detail); setImportStatus("Dokumen siap dibaca"); await loadDocument(imported.id); }
    catch (error) { setImportStatus(error.message || "Impor gagal"); }
  };

  const importUrl = async (event) => {
    event.preventDefault();
    const url = urlInput.trim(); if (!url || importingUrl) return;
    setImportingUrl(true); setImportStatus("Mengambil halaman publik…");
    try {
      const response = await axios.post(`${API}/putusan/import-url`, { url });
      setImportStatus("Dokumen siap dibaca");
      setUrlInput(""); setUrlOpen(false);
      await loadDocument(response.data.id);
    } catch (error) {
      setImportStatus(error.response?.data?.detail || "Impor URL gagal");
    } finally { setImportingUrl(false); }
  };

  const compareDocuments = async () => {
    const firstId = compareFirstId || document?.id;
    if (!firstId || !compareId || firstId === compareId) return;
    try {
      const response = await axios.post(`${API}/putusan/compare`, { first_id: firstId, second_id: compareId });
      setComparison(response.data);
      setCompareOpen(false);
      setView("compare");
    } catch (_) {
      showToast("Gagal memuat perbandingan. Coba lagi.");
    }
  };
  const openCompare = () => {
    setCompareFirstId(document?.id || (documents[0]?.id || ""));
    setCompareId("");
    if (!documents.length) searchDocuments();
    setCompareOpen(true);
  };
  const copyAnswer = async (text) => {
    try { await navigator.clipboard.writeText(plainAnswer(text)); showToast("Jawaban disalin"); }
    catch { showToast("Gagal menyalin jawaban"); }
  };
  const enrichPeraturan = async () => {
    if (!peraturanActive?.id) return;
    setEnrichingId(peraturanActive.id);
    setPeraturanStatus("Mengambil teks lengkap dari sumber…");
    try {
      const res = await axios.post(`${API}/peraturan/${peraturanActive.id}/refetch`);
      setPeraturanActive(res.data);
      setPeraturanList((list) => list.map((it) => it.id === res.data.id ? res.data : it));
      setPeraturanStatus("Teks lengkap berhasil diambil dari sumber.");
    } catch (error) {
      setPeraturanStatus(error.response?.data?.detail || "Gagal mengambil teks lengkap dari sumber.");
    } finally { setEnrichingId(""); }
  };
  const deletePeraturan = async (id, event) => {
    if (event) event.stopPropagation();
    if (!window.confirm("Hapus peraturan ini dari database?")) return;
    try {
      await axios.delete(`${API}/peraturan/${id}`);
      setPeraturanList((list) => list.filter((it) => it.id !== id));
      setPeraturanResults((list) => list.filter((it) => it.id !== id));
      if (peraturanActive?.id === id) setPeraturanActive(null);
      showToast("Peraturan dihapus");
    } catch { showToast("Gagal menghapus peraturan"); }
  };
  const deletePutusan = async (id, event) => {
    if (event) event.stopPropagation();
    if (!window.confirm("Hapus putusan ini dari database?")) return;
    try {
      await axios.delete(`${API}/putusan/${id}`);
      setDocuments((list) => list.filter((it) => it.id !== id));
      showToast("Putusan dihapus");
    } catch { showToast("Gagal menghapus putusan"); }
  };

  const loadPeraturan = async () => {
    const response = await axios.get(`${API}/peraturan`, { params: { q: peraturanFilters.q || undefined, jenis: peraturanFilters.jenis || undefined, tahun: peraturanFilters.tahun || undefined } });
    setPeraturanList(response.data);
    if (!peraturanActive && response.data[0]) setPeraturanActive(response.data[0]);
  };
  const openPeraturanById = async (id) => {
    const response = await axios.get(`${API}/peraturan/${id}`);
    setPeraturanActive(response.data); setPeraturanOpen(true);
    if (!peraturanList.length) loadPeraturan();
  };
  const togglePeraturanStatus = async () => {
    if (!peraturanActive) return;
    const next = peraturanActive.status === "Berlaku" ? "Dicabut" : "Berlaku";
    const payload = next === "Dicabut" ? { status: next, dicabut_oleh: window.prompt("Dicabut oleh (opsional, misal UU 7/2021):") || undefined } : { status: next };
    const response = await axios.patch(`${API}/peraturan/${peraturanActive.id}/status`, payload);
    setPeraturanActive(response.data);
    setPeraturanList((list) => list.map((item) => item.id === response.data.id ? response.data : item));
  };
  useEffect(() => {
    if (!peraturanActive) { setPeraturanRelated([]); return; }
    let active = true;
    axios.get(`${API}/peraturan/${peraturanActive.id}/putusan`).then((res) => { if (active) setPeraturanRelated(res.data.putusan || []); }).catch(() => { if (active) setPeraturanRelated([]); });
    return () => { active = false; };
  }, [peraturanActive?.id, peraturanActive?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (document) setDocTab(document.file_id && isPdfFile(document.original_filename) ? "pdf" : "teks");
  }, [document?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (peraturanActive) setPerDocTab(peraturanActive.file_id && isPdfFile(peraturanActive.original_filename) ? "pdf" : "teks");
  }, [peraturanActive?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const uploadPeraturanFile = async (event) => {
    const file = event.target.files?.[0]; if (!file) return;
    setPeraturanStatus("Mengekstrak peraturan…"); const form = new FormData(); form.append("file", file);
    try { const response = await fetch(`${API}/peraturan/upload`, { method: "POST", body: form }); const imported = await response.json(); if (!response.ok) throw new Error(imported.detail); setPeraturanStatus("Peraturan tersimpan"); await loadPeraturan(); setPeraturanActive(imported); }
    catch (error) { setPeraturanStatus(error.message || "Impor gagal"); }
  };
  const importPeraturanUrl = async (event) => {
    event.preventDefault();
    const url = peraturanUrl.trim(); if (!url) return;
    setPeraturanStatus("Mengambil peraturan dari URL…");
    try {
      const response = await axios.post(`${API}/putusan/import-url`, { url, kind: "peraturan" });
      setPeraturanStatus("Peraturan tersimpan"); setPeraturanUrl("");
      await loadPeraturan(); setPeraturanActive(response.data);
    } catch (error) { setPeraturanStatus(error.response?.data?.detail || "Impor URL gagal"); }
  };

  const handleCitationClick = (citation) => {
    if (citation.kind === "peraturan" && citation.peraturan_id) {
      openPeraturanById(citation.peraturan_id);
      return;
    }
    setDocTab("teks");
    window.setTimeout(() => window.document.getElementById(`paragraph-${citation.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
  };

  const showToast = (msg) => { setToastMsg(msg); window.setTimeout(() => setToastMsg(""), 2600); };
  const loadFiles = async () => {
    setFilesLoading(true);
    try { const response = await axios.get(`${API}/files`); setFiles(response.data); }
    catch { showToast("Gagal memuat daftar file"); }
    finally { setFilesLoading(false); }
  };
  const downloadOriginal = async (fileId, filename) => {
    try {
      const response = await axios.get(`${API}/files/${fileId}/download`, { responseType: "blob" });
      const blobUrl = window.URL.createObjectURL(response.data);
      const link = window.document.createElement("a");
      link.href = blobUrl; link.download = filename || "dokumen";
      window.document.body.appendChild(link); link.click();
      window.document.body.removeChild(link);
      window.setTimeout(() => window.URL.revokeObjectURL(blobUrl), 1500);
    } catch { showToast("Gagal mengunduh file asli"); }
  };
  const deleteFile = async (fileId) => {
    try { await axios.delete(`${API}/files/${fileId}`); setFiles((list) => list.filter((f) => f.id !== fileId)); showToast("File dihapus dari daftar"); }
    catch { showToast("Gagal menghapus file"); }
  };
  const toggleSave = () => {
    const next = savedIds.includes(document.id) ? savedIds.filter((id) => id !== document.id) : [...savedIds, document.id];
    setSavedIds(next); window.localStorage.setItem("taxlens-saved", JSON.stringify(next));
    showToast(savedIds.includes(document.id) ? "Putusan dihapus dari daftar simpan" : "Putusan tersimpan di daftar Anda");
  };
  const shareDocument = async () => {
    const shareUrl = document.source_url || window.location.href;
    try { await window.navigator.clipboard.writeText(shareUrl); showToast("Tautan sumber disalin ke clipboard"); }
    catch { showToast(shareUrl); }
  };
  const focusAssistant = () => {
    setMobileChat(true);
    const input = window.document.querySelector('[data-testid="chat-question-input"]');
    if (input) { input.scrollIntoView({ behavior: "smooth", block: "center" }); setTimeout(() => input.focus(), 250); }
  };
  const openSearchQuick = () => { setQuery(""); searchDocuments(); };

  const renderBodyWithTables = (body, { withParagraphIds = false } = {}) => {
    const nodes = []; let counter = 0; let keyIdx = 0;
    const regex = /\[TABLE\]\s*\n([\s\S]*?)\n\s*\[\/TABLE\]/g;
    let lastIndex = 0; let match;
    while ((match = regex.exec(body)) !== null) {
      const textChunk = body.slice(lastIndex, match.index);
      textChunk.split("\n").forEach((line) => {
        keyIdx += 1;
        if (!line.trim()) { nodes.push(<div className="document-gap" key={`g${keyIdx}`} />); return; }
        if (withParagraphIds) { counter += 1; const pid = `P${counter}`; nodes.push(<p id={`paragraph-${pid}`} data-testid={`document-paragraph-${pid}`} key={`p${keyIdx}`}>{line}</p>); }
        else { nodes.push(<p key={`p${keyIdx}`}>{line}</p>); }
      });
      const rows = match[1].split("\n").map((row) => row.split("\t"));
      const [header, ...dataRows] = rows;
      keyIdx += 1;
      nodes.push(<div className="document-table-wrap" key={`t${keyIdx}`} data-testid="document-table"><table className="document-table"><thead><tr>{header.map((cell, idx) => <th key={idx}>{cell}</th>)}</tr></thead><tbody>{dataRows.map((row, rowIdx) => <tr key={rowIdx}>{row.map((cell, cellIdx) => <td key={cellIdx}>{cell}</td>)}</tr>)}</tbody></table></div>);
      lastIndex = regex.lastIndex;
    }
    const tail = body.slice(lastIndex);
    tail.split("\n").forEach((line) => {
      keyIdx += 1;
      if (!line.trim()) { nodes.push(<div className="document-gap" key={`g${keyIdx}`} />); return; }
      if (withParagraphIds) { counter += 1; const pid = `P${counter}`; nodes.push(<p id={`paragraph-${pid}`} data-testid={`document-paragraph-${pid}`} key={`p${keyIdx}`}>{line}</p>); }
      else { nodes.push(<p key={`p${keyIdx}`}>{line}</p>); }
    });
    return nodes;
  };

  const parseExternalUrls = () => externalLinks.split("\n").map((line) => line.trim()).filter((line) => line.startsWith("http"));
  const previewExternalLinks = async () => {
    const urls = parseExternalUrls();
    if (!urls.length) { setExternalPreviews([]); showToast("Tempel minimal satu URL yang diawali http(s)://"); return; }
    setExternalBusy(true); setExternalPreviews(urls.map((url) => ({ url, status: "loading" })));
    const results = await Promise.all(urls.map(async (url) => {
      try {
        const response = await axios.post(`${API}/import/external/preview`, { url, kind: externalKind });
        return { url, ...response.data, status: "preview" };
      } catch (error) {
        return { url, status: "error", error: error.response?.data?.detail || "Tidak dapat diakses" };
      }
    }));
    setExternalPreviews(results); setExternalBusy(false);
  };
  const importExternalLinks = async () => {
    const urls = parseExternalUrls();
    if (!urls.length) { showToast("Tempel minimal satu URL"); return; }
    setExternalBusy(true);
    const previews = urls.map((url) => externalPreviews.find((p) => p.url === url) || { url, status: "loading" });
    setExternalPreviews(previews);
    let firstImportedId = null;
    for (let i = 0; i < urls.length; i += 1) {
      const url = urls[i];
      setExternalPreviews((list) => list.map((p) => p.url === url ? { ...p, status: "importing" } : p));
      try {
        const response = await axios.post(`${API}/import/external`, { url, kind: externalKind });
        if (!firstImportedId && externalKind === "putusan") firstImportedId = response.data.id;
        setExternalPreviews((list) => list.map((p) => p.url === url ? { ...p, status: "done", filename: response.data.external_filename || p.filename, provider: response.data.external_provider || p.provider } : p));
      } catch (error) {
        setExternalPreviews((list) => list.map((p) => p.url === url ? { ...p, status: "error", error: error.response?.data?.detail || "Impor gagal" } : p));
      }
    }
    setExternalBusy(false);
    if (externalKind === "peraturan") { loadPeraturan(); showToast("Peraturan baru masuk katalog"); }
    else if (firstImportedId) { loadDocument(firstImportedId); setExternalOpen(false); showToast("Putusan eksternal berhasil dibuka"); }
  };

  const exportDasarHukum = async (message, userQuestion, kind = "pdf") => {
    const endpoints = { pdf: "/export/dasar-hukum", docx: "/export/dasar-hukum-docx", bundel: "/export/bundel", "bundel-docx": "/export/bundel-docx" };
    const extensions = { pdf: "pdf", docx: "docx", bundel: "pdf", "bundel-docx": "docx" };
    const prefixes = { pdf: "dasar-hukum", docx: "dasar-hukum", bundel: "bundel-penelitian", "bundel-docx": "bundel-penelitian" };
    try {
      const response = await axios.post(`${API}${endpoints[kind]}`, {
        document_id: document.id,
        question: userQuestion || "Pertanyaan tidak tercatat",
        answer: message.text,
        citations: message.citations || [],
      }, { responseType: "blob" });
      const mime = extensions[kind] === "docx" ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document" : "application/pdf";
      const url = window.URL.createObjectURL(new Blob([response.data], { type: mime }));
      const a = window.document.createElement("a");
      a.href = url; a.download = `${prefixes[kind]}-${document.slug || document.id}.${extensions[kind]}`;
      window.document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (_) { window.alert("Gagal mengekspor. Coba lagi."); }
  };

  const handleLogoUpload = (event) => {
    const file = event.target.files?.[0]; if (!file) return;
    if (file.size > 500 * 1024) { window.alert("Logo terlalu besar, maksimal 500 KB."); return; }
    const reader = new FileReader();
    reader.onload = () => setBranding((prev) => ({ ...prev, logo_base64: reader.result }));
    reader.readAsDataURL(file);
  };
  const removeLogo = () => setBranding((prev) => ({ ...prev, logo_base64: null }));
  const saveBranding = async () => {
    setBrandingSaving(true);
    try {
      await axios.post(`${API}/branding`, {
        firm_name: branding.firm_name || null,
        firm_address: branding.firm_address || null,
        tagline: branding.tagline || null,
        logo_base64: branding.logo_base64 || null,
      });
      if (!branding.logo_base64) {
        await axios.delete(`${API}/branding/logo`).catch(() => {});
      }
      setBrandingOpen(false);
    } catch (_) { window.alert("Gagal menyimpan branding."); }
    finally { setBrandingSaving(false); }
  };
  if (!document) return <div className="loading-screen" data-testid="document-loading">Menyiapkan ruang kerja putusan…</div>;

  return <div className="app-shell">
    <header className="topbar"><div className="brand brand-clickable" data-testid="brand-home" onClick={goToKnowledge}><span className="brand-mark"><Gavel size={18} /></span><span>Tax AI Assistant</span></div><nav className="topbar-nav" data-testid="topbar-nav"><button className={`topbar-nav-link ${view === "knowledge" ? "active" : ""}`} data-testid="nav-tax-knowledge" onClick={goToKnowledge}>Tax Knowledge</button><button className={`topbar-nav-link ${view === "database" || view === "putusan" || view === "compare" ? "active" : ""}`} data-testid="nav-tax-database" onClick={goToDatabase}>Tax Database</button></nav>{view === "putusan" && <><button className="icon-button mobile-chat-trigger" data-testid="mobile-chat-button" onClick={() => setMobileChat(true)}><BrainCircuit size={18} /></button><div className="topbar-actions"><button className="outline-button" data-testid="open-branding-button" onClick={() => setBrandingOpen(true)}><Settings size={15} /> Branding</button><button className="outline-button" data-testid="open-external-button" onClick={() => setExternalOpen(true)}><Cloud size={15} /> Hubungkan Drive</button><button className="outline-button" data-testid="open-peraturan-button" onClick={() => { setPeraturanOpen(true); loadPeraturan(); }}><Scale size={15} /> Peraturan</button><button className="outline-button" data-testid="open-files-button" onClick={() => { setFilesOpen(true); loadFiles(); }}><FolderOpen size={15} /> File</button><button className="outline-button" data-testid="url-import-toggle" onClick={() => setUrlOpen((open) => !open)}><Link2 size={15} /> Impor URL</button><label className="import-button" data-testid="document-upload-label"><FileUp size={15} /> Impor PDF/DOCX/TXT<input data-testid="document-upload-input" type="file" accept=".pdf,.docx,.txt" onChange={importFile} /></label><button className="primary-button" data-testid="try-assistant-button" onClick={focusAssistant}><Sparkles size={16} /> Asisten pajak</button></div></>}</header>
    {view === "knowledge" ? <main className="knowledge-landing" data-testid="knowledge-landing">
      <div className="knowledge-hero">
        <span className="knowledge-mark"><Gavel size={30} /></span>
        <h1 className="knowledge-title">Tax Knowledge</h1>
        <p className="knowledge-sub">Mesin pencari web real-time untuk riset pajak &amp; umum. Hasil diambil langsung dari internet beserta sumber aslinya.</p>
        <div className="search-mode-tabs" data-testid="search-mode-tabs">
          <button className={`search-mode-tab ${searchMode === "web" ? "active" : ""}`} data-testid="mode-web" onClick={() => setSearchMode("web")}><Search size={15} /> Web</button>
          <button className={`search-mode-tab ${searchMode === "ai" ? "active" : ""}`} data-testid="mode-ai" onClick={() => setSearchMode("ai")}><Sparkles size={15} /> AI Search</button>
        </div>
        <form className="knowledge-search" data-testid="knowledge-search-form" onSubmit={(event) => { event.preventDefault(); submitSearch(); }}>
          <Search size={20} />
          <input data-testid="knowledge-search-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={searchMode === "ai" ? "Tanyakan apa saja, mis. Apakah STP bisa dibatalkan?" : "Cari apa saja di web, mis. pembatalan STP pajak"} autoFocus />
          <button className="primary-button" type="submit" data-testid="knowledge-search-button" disabled={webLoading || aiLoading}>{(webLoading || aiLoading) ? "Mencari…" : "Cari"}</button>
        </form>
        <div className="knowledge-suggestions" data-testid="knowledge-suggestions">
          {["pembatalan STP pajak", "PPN TBS sawit", "putusan banding PPh badan", "PMK 81 tahun 2024", "pajak natura"].map((s) => <button key={s} data-testid={`knowledge-suggestion-${s}`} onClick={() => submitSearch(s)}><Sparkles size={13} /> {s}</button>)}
        </div>
      </div>

      {(webLoading || aiLoading) && <div className="search-loading" data-testid="search-loading"><span className="search-spinner" />{searchMode === "ai" ? "AI sedang membaca sumber dari web…" : "Mencari di web secara real-time…"}</div>}

      {!webLoading && !aiLoading && searchError && <div className="search-error" data-testid="search-error">{searchError}</div>}

      {!webLoading && searchMode === "web" && webData && !searchError && <div className="web-results" data-testid="web-results">
        <div className="web-results-bar">
          <div className="web-filters">
            {[["web", "Web"], ["news", "Berita"], ["pdf", "PDF"]].map(([t, label]) => (
              <button key={t} className={`web-filter ${webType === t ? "active" : ""}`} data-testid={`web-filter-${t}`} onClick={() => changeWebType(t)}>{label}</button>
            ))}
          </div>
          <span className="web-stats" data-testid="web-stats">Sekitar {webData.total} hasil ({webData.searchTime} detik)</span>
        </div>
        {webData.results.length === 0 ? <div className="result-empty" data-testid="web-no-results">Tidak ada hasil untuk &quot;{webData.query}&quot;.</div> :
          webData.results.map((r) => (
            <div className="web-result" data-testid={`web-result-${r.rank}`} key={`${r.rank}-${r.url}`}>
              <div className="web-result-head">
                {r.favicon ? <img className="web-favicon" src={r.favicon} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} /> : null}
                <span className="web-display-url">{r.displayUrl}</span>
              </div>
              <a className="web-title" href={r.url} target="_blank" rel="noreferrer" data-testid={`web-result-link-${r.rank}`}>{r.title}</a>
              {r.snippet ? <p className="web-snippet">{r.snippet.replace(/\*/g, "")}</p> : null}
              <a className="web-open" href={r.url} target="_blank" rel="noreferrer" data-testid={`web-open-${r.rank}`}><ArrowUpRight size={13} /> Open Source</a>
            </div>
          ))}
        {webData.totalPages > 1 && <div className="web-pagination" data-testid="web-pagination">
          <button className="outline-button" disabled={webData.page <= 1} data-testid="web-prev" onClick={() => gotoPage(webData.page - 1)}><ChevronLeft size={15} /> Sebelumnya</button>
          <span>Halaman {webData.page} dari {webData.totalPages}</span>
          <button className="outline-button" disabled={webData.page >= webData.totalPages} data-testid="web-next" onClick={() => gotoPage(webData.page + 1)}>Berikutnya</button>
        </div>}
      </div>}

      {!aiLoading && searchMode === "ai" && aiData && !searchError && <div className="ai-result" data-testid="ai-result">
        <div className="ai-result-head"><Sparkles size={15} /> Jawaban AI <span className="ai-time">({aiData.searchTime} detik)</span></div>
        <div className="ai-answer" data-testid="ai-answer">{renderAiAnswer(aiData.answer, aiData.sources)}</div>
        {aiData.sources.length > 0 && <div className="ai-sources" data-testid="ai-sources">
          <div className="ai-sources-label">Sumber ({aiData.sources.length})</div>
          {aiData.sources.filter((s) => s.cited !== false).map(renderAiSource)}
          {aiData.sources.some((s) => s.cited === false) && <div className="ai-sources-label ai-sources-sub" data-testid="ai-related-sources-label">Sumber terkait lainnya</div>}
          {aiData.sources.filter((s) => s.cited === false).map(renderAiSource)}
        </div>}
        <div className="ai-disclaimer">Jawaban AI dapat keliru — selalu verifikasi ke sumber asli di atas.</div>
      </div>}
    </main> : view === "database" ? <main className="database-page" data-testid="database-page">
      <div className="database-hero">
        <span className="knowledge-mark"><Scale size={30} /></span>
        <h1 className="knowledge-title">Tax Database</h1>
        <form className="knowledge-search" data-testid="database-search-form" onSubmit={(event) => { event.preventDefault(); loadDatabase(); }}>
          <Search size={20} />
          <input data-testid="database-search-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Cari nomor, isu, atau kata dalam putusan atau peraturan" />
          <button className="primary-button" type="submit" data-testid="database-search-button">Cari</button>
        </form>
        <div className="database-actions" data-testid="database-actions">
          <button data-testid="database-open-compare" onClick={openCompare}><GitCompareArrows size={14} /> Bandingkan Putusan</button>
          <button data-testid="database-open-peraturan-catalog" onClick={() => { setPeraturanOpen(true); loadPeraturan(); }}><BookOpen size={14} /> Katalog Peraturan</button>
        </div>
      </div>
      <div className="database-grid" data-testid="database-grid">
        <section className="database-col" data-testid="database-col-putusan">
          <div className="database-col-head"><Gavel size={16} /><h2>Putusan</h2><span className="database-count">{documents.length}</span></div>
          <div className="database-filter-row" data-testid="database-putusan-filters">
            <select data-testid="db-filter-year" value={filters.year} onChange={(event) => applyDbPutusanFilter({ year: event.target.value })}>
              <option value="">Semua tahun</option>
              {putusanFacets.years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <select data-testid="db-filter-case-type" value={filters.case_type} onChange={(event) => applyDbPutusanFilter({ case_type: event.target.value })}>
              <option value="">Semua jenis sengketa</option>
              {putusanFacets.caseTypes.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            {(filters.year || filters.case_type) && <button className="database-filter-reset" data-testid="db-filter-reset" onClick={() => applyDbPutusanFilter({ year: "", case_type: "" })}><X size={13} /> Reset</button>}
          </div>
          <div className="database-list">
            {documents.length === 0 ? <div className="result-empty">Belum ada putusan yang cocok.</div> :
              documents.map((item) => <div className="database-item-row" key={item.id}>
                <button className="database-item" data-testid={`database-putusan-${item.id}`} onClick={() => loadDocument(item.id)}>
                  <strong>{item.title}</strong>
                  <span className="database-item-meta">{item.tax_type} · {item.year} · {item.case_type}</span>
                </button>
                <button className="preview-pdf-btn" data-testid={`preview-putusan-${item.id}`} title="Pratinjau PDF" onClick={() => setPreviewPdf({ url: putusanPdfUrl(item.id), title: item.title, downloadUrl: putusanPdfUrl(item.id, false) })}><Eye size={16} /></button>
                <button className="preview-pdf-btn db-delete-btn" data-testid={`delete-putusan-${item.id}`} title="Hapus putusan" onClick={(event) => deletePutusan(item.id, event)}><Trash2 size={16} /></button>
              </div>)}
          </div>
        </section>
        <section className="database-col" data-testid="database-col-peraturan">
          <div className="database-col-head"><Scale size={16} /><h2>Peraturan</h2><span className="database-count">{peraturanResults.length}</span></div>
          <div className="database-list">
            {peraturanResults.length === 0 ? <div className="result-empty">Belum ada peraturan yang cocok.</div> :
              peraturanResults.map((reg) => <div className="database-item-row" key={reg.id}>
                <button className="database-item database-item-peraturan" data-testid={`database-peraturan-${reg.id}`} onClick={() => openPeraturanById(reg.id)}>
                  <strong><span className={`tag tag-${reg.jenis.toLowerCase().replace("-", "")}`}>{reg.jenis}</span> {reg.nomor} — {reg.judul}</strong>
                  <span className="database-item-meta">{reg.tahun} · {reg.status}</span>
                </button>
                <button className="preview-pdf-btn" data-testid={`preview-peraturan-${reg.id}`} title="Pratinjau PDF" onClick={() => setPreviewPdf({ url: peraturanPdfUrl(reg.id), title: `${reg.jenis} ${reg.nomor}`, downloadUrl: peraturanPdfUrl(reg.id, false) })}><Eye size={16} /></button>
                <button className="preview-pdf-btn db-delete-btn" data-testid={`delete-peraturan-${reg.id}`} title="Hapus peraturan" onClick={(event) => deletePeraturan(reg.id, event)}><Trash2 size={16} /></button>
              </div>)}
          </div>
        </section>
      </div>
    </main> : view === "compare" ? <main className="compare-page" data-testid="compare-page">
      <div className="compare-page-head">
        <button className="crumbs-button" data-testid="compare-back-button" onClick={goToDatabase}><ChevronLeft size={16} /> Kembali ke Tax Database</button>
        <div className="compare-page-title"><span className="eyebrow">ANALISIS BERDAMPINGAN</span><h1>Perbandingan Putusan</h1></div>
        <button className="outline-button" data-testid="compare-reopen-button" onClick={openCompare}><GitCompareArrows size={15} /> Ganti putusan</button>
      </div>
      {comparison ? <>
        {(() => { const diffCount = Object.values(comparison.differences || {}).filter(Boolean).length; return (
          <div className="compare-diff-banner" data-testid="compare-diff-banner">{diffCount === 0 ? "Metadata kedua putusan identik." : `${diffCount} aspek metadata berbeda — ditandai di bawah.`}</div>
        ); })()}
        <div className="compare-columns" data-testid="compare-columns">
          {[["first", "PUTUSAN PERTAMA"], ["second", "PUTUSAN PEMBANDING"]].map(([key, label]) => { const d = comparison[key]; const diff = comparison.differences || {}; return (
            <section className="compare-col" data-testid={`compare-col-${key}`} key={key}>
              <span className="compare-col-label">{label}</span>
              <h2 className="compare-doc-title" data-testid={`compare-title-${key}`}>{d.title}</h2>
              <div className="compare-meta">
                <div className={diff.case_type ? "compare-meta-row is-diff" : "compare-meta-row"}><span>Jenis Sengketa</span><strong>{d.case_type || "-"}</strong></div>
                <div className={diff.tax_type ? "compare-meta-row is-diff" : "compare-meta-row"}><span>Jenis Pajak</span><strong>{d.tax_type || "-"}</strong></div>
                <div className="compare-meta-row"><span>Badan Peradilan</span><strong>{d.court || "-"}</strong></div>
                <div className="compare-meta-row"><span>Majelis</span><strong>{d.panel || "-"}</strong></div>
                <div className="compare-meta-row"><span>Tahun</span><strong>{d.year || "-"}</strong></div>
              </div>
              <div className="compare-section">
                <h3 className={diff.verdict ? "compare-section-title is-diff" : "compare-section-title"}><Gavel size={14} /> Amar Putusan</h3>
                <p className="compare-verdict" data-testid={`compare-verdict-${key}`}>{d.verdict || "Amar putusan tidak tersedia."}</p>
              </div>
              <div className="compare-section">
                <h3 className="compare-section-title"><BookOpen size={14} /> Pertimbangan Hukum &amp; Isi Lengkap</h3>
                <article className="compare-body" data-testid={`compare-body-${key}`}>{renderBodyWithTables(d.body)}</article>
              </div>
              <div className="compare-col-foot"><a href={d.source_url} target="_blank" rel="noreferrer">Sumber dokumen <ArrowUpRight size={13} /></a></div>
            </section>
          ); })}
        </div>
      </> : <div className="peraturan-empty" data-testid="compare-empty">Belum ada perbandingan. Pilih dua putusan untuk dibandingkan.</div>}
    </main> : <main className="workspace">
      <section className="document-column">
        <button className="crumbs crumbs-button" data-testid="document-breadcrumb" onClick={goToKnowledge}><ChevronLeft size={16} /> Tax Knowledge <span>/</span> Putusan</button>
        <div className="search-strip"><div className="search-input-wrap"><Search size={16} /><input data-testid="putusan-search-input" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && searchDocuments()} placeholder="Cari nomor, isu, atau kata dalam putusan atau peraturan" /></div><button className="outline-button" data-testid="open-search-button" onClick={searchDocuments}>Cari</button><button className="icon-button" data-testid="search-open-peraturan-button" title="Buka katalog peraturan" onClick={() => { setPeraturanOpen(true); loadPeraturan(); }}><Scale size={17} /></button><button className="icon-button" data-testid="compare-open-button" onClick={openCompare} title="Bandingkan putusan"><GitCompareArrows size={17} /></button></div>
        {urlOpen && <form className="url-import-form" data-testid="url-import-form" onSubmit={importUrl}><div className="url-input-wrap"><Link2 size={16} /><input data-testid="url-import-input" type="url" value={urlInput} onChange={(event) => setUrlInput(event.target.value)} placeholder="Tempel URL putusan publik, misal https://..." required /></div><button className="primary-button" data-testid="url-import-submit" type="submit" disabled={importingUrl || !urlInput.trim()}>{importingUrl ? "Mengimpor…" : "Impor & baca"}</button><button className="icon-button" data-testid="url-import-close" type="button" onClick={() => { setUrlOpen(false); setUrlInput(""); }}><X size={16} /></button></form>}
        {searchOpen && <div className="search-results" data-testid="search-results"><div className="filter-row"><select data-testid="filter-year" value={filters.year} onChange={(event) => setFilters({ ...filters, year: event.target.value })}><option value="">Semua tahun</option><option value="2022">2022</option><option value="2021">2021</option></select><span className="filter-divider">Peraturan:</span><select data-testid="filter-per-jenis" value={perFilter.jenis} onChange={(event) => applyPerFilter({ jenis: event.target.value })}><option value="">Semua jenis</option><option value="UU">UU</option><option value="PP">PP</option><option value="PMK">PMK</option><option value="PER-DJP">PER-DJP</option><option value="SE-DJP">SE-DJP</option></select><select data-testid="filter-per-status" value={perFilter.status} onChange={(event) => applyPerFilter({ status: event.target.value })}><option value="">Semua status</option><option value="Berlaku">Berlaku</option><option value="Dicabut">Dicabut</option><option value="Diubah">Diubah</option></select><span>{documents.length} putusan · {peraturanResults.length} peraturan</span></div>{documents.length > 0 && <div className="result-group-label">PUTUSAN</div>}{documents.map((item) => <button className="result-item" data-testid={`search-result-${item.id}`} key={item.id} onClick={() => { loadDocument(item.id); setSearchOpen(false); }}><strong>{item.title}</strong><span>{item.tax_type} · {item.year} · {item.case_type}</span></button>)}{peraturanResults.length > 0 && <div className="result-group-label">PERATURAN</div>}{peraturanResults.map((reg) => <button className="result-item result-item-peraturan" data-testid={`search-peraturan-${reg.id}`} key={reg.id} onClick={() => { openPeraturanById(reg.id); setSearchOpen(false); }}><strong><span className={`tag tag-${reg.jenis.toLowerCase().replace("-", "")}`}>{reg.jenis}</span> {reg.nomor} — {reg.judul}</strong><span>{reg.tahun} · {reg.status}</span></button>)}{documents.length === 0 && peraturanResults.length === 0 && <div className="result-empty" data-testid="search-no-results">Tidak ada hasil untuk pencarian ini.</div>}</div>}
        <div className="import-status" data-testid="import-status">{importStatus}</div>
        <div className="document-head"><div className="tag-row"><span className="tag blue-tag">PUTUSAN</span><span className="tag">{document.tax_type}</span><span className="tag">{document.year}</span></div><h1 data-testid="document-title">{document.title}</h1><p className="document-lede" data-testid="document-summary">{document.summary}</p><div className="head-actions"><button className={`outline-button ${savedIds.includes(document.id) ? "is-saved" : ""}`} data-testid="save-document-button" onClick={toggleSave}><BookOpen size={16} /> {savedIds.includes(document.id) ? "Tersimpan" : "Simpan"}</button><button className="outline-button" data-testid="share-document-button" onClick={shareDocument}>Bagikan <ArrowUpRight size={15} /></button><button className="outline-button" data-testid="download-pdf-button" onClick={() => window.open(putusanPdfUrl(document.id, false), "_blank")}><Download size={16} /> Unduh PDF</button>{document.file_id && <button className="outline-button" data-testid="download-original-button" onClick={() => downloadOriginal(document.file_id, document.original_filename)}><Download size={16} /> Unduh file asli</button>}</div></div>
        <div className="meta-grid" data-testid="document-metadata"><div><span>JENIS SENGKETA</span><strong>{document.case_type}</strong></div><div><span>JENIS PAJAK</span><strong>{document.tax_type}</strong></div><div><span>BADAN PERADILAN</span><strong>{document.court}</strong></div><div><span>MAJELIS</span><strong>{document.panel}</strong></div></div>
        <div className="reader-toolbar"><span className="reader-label"><span className="status-dot" /> Dokumen terverifikasi</span><div className="doc-tabs" data-testid="doc-tabs"><button className={`doc-tab ${docTab === "teks" ? "active" : ""}`} data-testid="doc-tab-teks" onClick={() => setDocTab("teks")}><BookOpen size={14} /> Teks terformat</button><button className={`doc-tab ${docTab === "pdf" ? "active" : ""}`} data-testid="doc-tab-pdf" onClick={() => setDocTab("pdf")}><FileText size={14} /> {document.file_id && isPdfFile(document.original_filename) ? "PDF Asli" : "PDF"}</button></div><button className="icon-button" data-testid="search-document-button" title="Cari putusan lain" onClick={openSearchQuick}><Search size={17} /></button></div>
        {docTab === "pdf"
          ? <div className="pdf-viewer" data-testid="pdf-viewer"><PdfFrame url={putusanPdfTabUrl(document)} testId="pdf-frame" /></div>
          : <article className="document-body" data-testid="document-body">{renderBodyWithTables(document.body, { withParagraphIds: true })}</article>}
        
      </section>
      <aside className={`assistant-panel ${mobileChat ? "panel-open" : ""}`} data-testid="assistant-panel"><div className="assistant-head"><div><div className="assistant-kicker"><span className="live-dot" /> AI CONTEXTUAL ASSISTANT</div><h2>Tanya putusan ini</h2><p>Jawaban berbasis dokumen aktif</p></div><button className="icon-button close-chat" data-testid="close-chat-button" onClick={() => setMobileChat(false)}><X size={18} /></button></div><div className="model-chip" data-testid="model-indicator"><Sparkles size={14} /> GPT 5.6 Terra <span>•</span> grounded</div><div className="chat-messages" data-testid="chat-messages">{messages.map((message, index) => <div className={`message ${message.role}`} key={index}><div className="message-top"><span className="message-label">{message.role === "assistant" ? "TaxLens AI" : "Anda"}</span>{message.role === "assistant" && message.text && <button className="copy-answer-btn" data-testid={`copy-answer-${index}`} title="Salin jawaban" onClick={() => copyAnswer(message.text)}><Copy size={13} /> Salin</button>}</div><div className="msg-body">{message.text ? renderRich(message.text) : (loading ? "Membaca pertimbangan majelis…" : "")}</div>{message.citations?.length > 0 && <><div className="citation-list" data-testid="citation-list">{message.citations.map((citation) => <button className={`citation-chip citation-${citation.kind || "paragraf"}`} data-testid={`citation-${citation.id}`} key={citation.id} onClick={() => handleCitationClick(citation)}><span>{citation.label}</span> {citation.text}</button>)}</div><div className="export-row"><span className="export-label">UNDUH LAMPIRAN</span><button className="export-btn" data-testid={`export-pdf-${index}`} onClick={() => exportDasarHukum(message, messages[index - 1]?.text, "pdf")}><Download size={12} /> PDF</button><button className="export-btn" data-testid={`export-docx-${index}`} onClick={() => exportDasarHukum(message, messages[index - 1]?.text, "docx")}><Download size={12} /> DOCX</button><button className="export-btn export-btn-primary" data-testid={`export-bundel-${index}`} onClick={() => exportDasarHukum(message, messages[index - 1]?.text, "bundel")}><Download size={12} /> Bundel PDF</button><button className="export-btn export-btn-primary" data-testid={`export-bundel-docx-${index}`} onClick={() => exportDasarHukum(message, messages[index - 1]?.text, "bundel-docx")}><Download size={12} /> Bundel DOCX</button></div></>}</div>)}</div><div className="suggestions"><button data-testid="suggestion-summary" onClick={() => setQuestion("Apa inti pertimbangan majelis dalam putusan ini?")}>Ringkas pertimbangan</button><button data-testid="suggestion-issue" onClick={() => setQuestion("Apa isu PPN yang diputus?")}>Identifikasi isu PPN</button></div><form className="chat-form" onSubmit={sendQuestion}><textarea value={question} onChange={(event) => setQuestion(event.target.value)} data-testid="chat-question-input" placeholder="Tanyakan sesuatu tentang putusan…" rows="2" /><button className="send-button" data-testid="chat-send-button" disabled={loading || !question.trim()}><Send size={17} /></button></form><div className="assistant-note"><span>⌘</span> Jawaban AI perlu diverifikasi terhadap dokumen asli</div></aside>
    </main>}
    {compareOpen && <div className="modal-backdrop" data-testid="compare-modal"><div className="compare-modal"><div className="modal-head"><div><span className="eyebrow">ANALISIS BERDAMPINGAN</span><h2>Bandingkan putusan</h2></div><button className="icon-button" data-testid="compare-close-button" onClick={() => setCompareOpen(false)}><X size={17} /></button></div><p className="modal-copy">Pilih dua putusan untuk melihat perbandingan metadata, amar, dan pertimbangan hukum secara berdampingan.</p><button className="outline-button compare-load" data-testid="compare-search-button" onClick={searchDocuments}><Search size={15} /> Muat hasil pencarian</button><label className="compare-field-label">Putusan pertama</label><select data-testid="compare-first-select" value={compareFirstId} onChange={(event) => setCompareFirstId(event.target.value)}><option value="">Pilih putusan pertama</option>{documents.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><label className="compare-field-label">Putusan kedua (pembanding)</label><select data-testid="compare-document-select" value={compareId} onChange={(event) => setCompareId(event.target.value)}><option value="">Pilih putusan kedua</option>{documents.filter((item) => item.id !== compareFirstId).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select>{compareFirstId && compareId && compareFirstId === compareId && <div className="difference-note">Pilih dua putusan yang berbeda.</div>}<button className="primary-button compare-submit" data-testid="compare-submit-button" disabled={!compareFirstId || !compareId || compareFirstId === compareId} onClick={compareDocuments}><GitCompareArrows size={15} /> Bandingkan sekarang</button></div></div>}
    {brandingOpen && <div className="modal-backdrop" data-testid="branding-modal"><div className="branding-modal"><div className="modal-head"><div><span className="eyebrow">BRANDING FIRMA</span><h2>Logo & Letterhead</h2></div><button className="icon-button" data-testid="branding-close-button" onClick={() => setBrandingOpen(false)}><X size={17} /></button></div><p className="modal-copy">Logo dan nama firma ini akan tercetak otomatis di setiap ekspor PDF, DOCX, dan Bundel Penelitian — langsung siap diserahkan ke klien.</p>      <div className="branding-split">
        <div className="branding-form">
          <label className="branding-field"><span>Nama Firma</span><input data-testid="branding-firm-name" type="text" value={branding.firm_name || ""} onChange={(event) => setBranding({ ...branding, firm_name: event.target.value })} placeholder="Konsultan Pajak Nusantara" /></label>
          <label className="branding-field"><span>Alamat</span><textarea data-testid="branding-firm-address" rows="2" value={branding.firm_address || ""} onChange={(event) => setBranding({ ...branding, firm_address: event.target.value })} placeholder="Jl. Sudirman No. 12, Jakarta Pusat" /></label>
          <label className="branding-field"><span>Tagline (opsional)</span><input data-testid="branding-tagline" type="text" value={branding.tagline || ""} onChange={(event) => setBranding({ ...branding, tagline: event.target.value })} placeholder="Precision in Taxation" /></label>
          <div className="branding-field"><span>Logo (PNG/JPG, maks 500 KB)</span>
            <div className="branding-logo-row">
              <label className="import-button" data-testid="branding-logo-label"><ImagePlus size={14} /> {branding.logo_base64 ? "Ganti logo" : "Unggah logo"}<input data-testid="branding-logo-input" type="file" accept="image/png,image/jpeg" onChange={handleLogoUpload} /></label>
              {branding.logo_base64 && <button className="outline-button" data-testid="branding-logo-remove" onClick={removeLogo}>Hapus logo</button>}
            </div>
          </div>
        </div>
        <div className="branding-preview" data-testid="branding-preview">
          <span className="preview-label">PREVIEW LETTERHEAD</span>
          <div className="preview-card">
            <div className="preview-head">
              {branding.logo_base64 && <img src={branding.logo_base64} alt="logo" data-testid="branding-logo-preview" />}
              <div className="preview-text">
                <strong>{branding.firm_name || "Nama Firma Anda"}</strong>
                {branding.firm_address && <span>{branding.firm_address}</span>}
                {branding.tagline && <em>{branding.tagline}</em>}
                <small>TAXLENS · DASAR HUKUM JAWABAN AI</small>
              </div>
            </div>
            <hr />
            <strong className="preview-doc-title">PUT-004106.16/2020/PP/M.IB Tahun 2022</strong>
            <p>1. Pertanyaan</p>
            <p className="preview-dim">Apa dasar hukum koreksi faktur sebelum NSFP?</p>
          </div>
        </div>
      </div>
      <div className="branding-actions"><button className="outline-button" data-testid="branding-cancel-button" onClick={() => setBrandingOpen(false)}>Batal</button><button className="primary-button" data-testid="branding-save-button" disabled={brandingSaving} onClick={saveBranding}>{brandingSaving ? "Menyimpan…" : "Simpan branding"}</button></div>
    </div></div>}
    {peraturanOpen && <div className="modal-backdrop" data-testid="peraturan-modal"><div className="peraturan-modal"><div className="modal-head"><div><span className="eyebrow">DASAR HUKUM</span><h2>Katalog Peraturan Pajak</h2></div><button className="icon-button" data-testid="peraturan-close-button" onClick={() => setPeraturanOpen(false)}><X size={17} /></button></div><p className="modal-copy">UU, PP, PMK, dan PER-DJP yang menjadi dasar jawaban AI. Impor peraturan baru dari URL atau file.</p>
      <div className="peraturan-import-row">
        <form className="url-import-form" data-testid="peraturan-url-form" onSubmit={importPeraturanUrl}>
          <div className="url-input-wrap"><Link2 size={15} /><input data-testid="peraturan-url-input" type="url" value={peraturanUrl} onChange={(event) => setPeraturanUrl(event.target.value)} placeholder="URL peraturan.go.id / jdih.kemenkeu.go.id" /></div>
          <button className="primary-button" data-testid="peraturan-url-submit" type="submit" disabled={!peraturanUrl.trim()}>Impor URL</button>
        </form>
        <label className="import-button" data-testid="peraturan-upload-label"><FileUp size={14} /> File<input data-testid="peraturan-upload-input" type="file" accept=".pdf,.docx,.txt" onChange={uploadPeraturanFile} /></label>
      </div>
      {peraturanStatus && <div className="import-status" data-testid="peraturan-import-status">{peraturanStatus}</div>}
      <div className="peraturan-filter-row">
        <div className="search-input-wrap"><Search size={14} /><input data-testid="peraturan-search-input" placeholder="Cari judul, nomor, atau isi pasal" value={peraturanFilters.q} onChange={(event) => setPeraturanFilters({ ...peraturanFilters, q: event.target.value })} onKeyDown={(event) => event.key === "Enter" && loadPeraturan()} /></div>
        <select data-testid="peraturan-filter-jenis" value={peraturanFilters.jenis} onChange={(event) => setPeraturanFilters({ ...peraturanFilters, jenis: event.target.value })}><option value="">Semua jenis</option><option value="UU">UU</option><option value="PP">PP</option><option value="PMK">PMK</option><option value="PER-DJP">PER-DJP</option><option value="SE-DJP">SE-DJP</option></select>
        <select data-testid="peraturan-filter-tahun" value={peraturanFilters.tahun} onChange={(event) => setPeraturanFilters({ ...peraturanFilters, tahun: event.target.value })}><option value="">Semua tahun</option>{[...new Set(peraturanList.map((item) => item.tahun))].sort((a, b) => b - a).map((year) => <option key={year} value={year}>{year}</option>)}</select>
        <button className="outline-button" data-testid="peraturan-apply-filter" onClick={loadPeraturan}>Terapkan</button>
      </div>
      <div className="peraturan-split">
        <div className="peraturan-list" data-testid="peraturan-list">{peraturanList.length === 0 && <div className="peraturan-empty">Belum ada peraturan. Tekan Terapkan atau impor sumber baru.</div>}{peraturanList.map((reg) => <div className={`peraturan-item-row ${peraturanActive?.id === reg.id ? "active" : ""} ${reg.status !== "Berlaku" ? "revoked" : ""}`} key={reg.id}><button className={`peraturan-item ${peraturanActive?.id === reg.id ? "active" : ""} ${reg.status !== "Berlaku" ? "revoked" : ""}`} data-testid={`peraturan-item-${reg.id}`} onClick={() => setPeraturanActive(reg)}><div className="peraturan-item-top"><span className={`tag tag-${reg.jenis.toLowerCase().replace("-", "")}`}>{reg.jenis}</span><span className={`status-dot-badge status-${reg.status.toLowerCase()}`} title={reg.status}>{reg.status === "Berlaku" ? "✓" : "✕"}</span></div><strong>{reg.nomor}</strong><p>{reg.judul}</p><small>{reg.tahun} · {reg.status}</small></button><button className="peraturan-item-delete" data-testid={`peraturan-delete-${reg.id}`} title="Hapus peraturan" onClick={(event) => deletePeraturan(reg.id, event)}><Trash2 size={14} /></button></div>)}</div>
        <div className="peraturan-detail" data-testid="peraturan-detail">{peraturanActive ? <>
          <div className="peraturan-head"><div className="peraturan-head-top"><span className={`tag tag-${peraturanActive.jenis.toLowerCase().replace("-", "")}`}>{peraturanActive.jenis}</span><span className={`status-badge status-${peraturanActive.status.toLowerCase()}`} data-testid="peraturan-status-badge">{peraturanActive.status === "Berlaku" ? "✓ Berlaku" : peraturanActive.status === "Dicabut" ? "✕ Dicabut" : peraturanActive.status}</span><button className="outline-button status-toggle" data-testid="peraturan-status-toggle" onClick={togglePeraturanStatus}>{peraturanActive.status === "Berlaku" ? "Tandai dicabut" : "Tandai berlaku"}</button><button className="outline-button" data-testid="peraturan-download-pdf" onClick={() => window.open(peraturanPdfUrl(peraturanActive.id, false), "_blank")}><Download size={15} /> Unduh PDF</button>{peraturanActive.source_url && <button className="outline-button" data-testid="peraturan-refetch" disabled={enrichingId === peraturanActive.id} onClick={enrichPeraturan}><RefreshCw size={15} /> {enrichingId === peraturanActive.id ? "Mengambil…" : "Ambil teks lengkap dari sumber"}</button>}<button className="icon-button peraturan-delete-detail" data-testid="peraturan-delete-detail" title="Hapus peraturan" onClick={(event) => deletePeraturan(peraturanActive.id, event)}><Trash2 size={15} /></button></div><h3 data-testid="peraturan-title">{peraturanActive.judul}</h3><div className="peraturan-meta"><span>Nomor</span><strong>{peraturanActive.nomor}</strong><span>Tahun</span><strong>{peraturanActive.tahun}</strong><span>Status</span><strong>{peraturanActive.status}</strong>{peraturanActive.tanggal_berlaku && <><span>Berlaku</span><strong>{peraturanActive.tanggal_berlaku}</strong></>}{peraturanActive.dicabut_oleh && <><span>Dicabut oleh</span><strong>{peraturanActive.dicabut_oleh}</strong></>}</div>{peraturanActive.status !== "Berlaku" && <div className="status-warning" data-testid="peraturan-status-warning">Peraturan ini sudah tidak berlaku dan dikecualikan dari dasar jawaban AI.</div>}</div>
          <div className="doc-tabs doc-tabs-modal" data-testid="per-doc-tabs"><button className={`doc-tab ${perDocTab === "teks" ? "active" : ""}`} data-testid="per-doc-tab-teks" onClick={() => setPerDocTab("teks")}><BookOpen size={14} /> Teks</button><button className={`doc-tab ${perDocTab === "pdf" ? "active" : ""}`} data-testid="per-doc-tab-pdf" onClick={() => setPerDocTab("pdf")}><FileText size={14} /> {peraturanActive.file_id && isPdfFile(peraturanActive.original_filename) ? "PDF Asli" : "PDF"}</button></div>
          {perDocTab === "pdf"
            ? <div className="pdf-viewer pdf-viewer-modal" data-testid="per-pdf-viewer"><PdfFrame url={peraturanPdfTabUrl(peraturanActive)} testId="per-pdf-frame" /></div>
            : <article className="peraturan-body" data-testid="peraturan-body">{renderBodyWithTables(peraturanActive.body)}</article>}
          <div className="peraturan-related" data-testid="peraturan-related">
            <h4><Gavel size={14} /> Yurisprudensi — Putusan yang merujuk {peraturanActive.jenis} {peraturanActive.nomor}</h4>
            {peraturanRelated.length === 0 ? <div className="peraturan-related-empty">Belum ada putusan dalam katalog yang merujuk peraturan ini.</div> :
              <div className="peraturan-related-list">{peraturanRelated.map((item) => <button key={item.id} className="related-item" data-testid={`related-putusan-${item.id}`} onClick={() => { loadDocument(item.id); setPeraturanOpen(false); }}><strong>{item.title}</strong><span>{item.tax_type} · {item.year} · {item.case_type} · {item.match_count}× dirujuk</span></button>)}</div>}
          </div>
        </> : <div className="peraturan-empty">Pilih peraturan di sebelah kiri untuk melihat detail pasal.</div>}</div>
      </div>
    </div></div>}
    {externalOpen && <div className="modal-backdrop" data-testid="external-modal"><div className="external-modal"><div className="modal-head"><div><span className="eyebrow">INTEGRASI INBOUND</span><h2>Impor dari Google Drive · Dropbox · OneDrive</h2></div><button className="icon-button" data-testid="external-close-button" onClick={() => setExternalOpen(false)}><X size={17} /></button></div><p className="modal-copy">Tempel share-link publik dari Drive/Dropbox/OneDrive (satu per baris). Pastikan file di-set <strong>"Anyone with the link"</strong>. TaxLens akan mengambil file, mengekstrak teks, dan menyimpannya sebagai Putusan atau Peraturan.</p>
      <div className="external-kind-row">
        <label className={`kind-pill ${externalKind === "putusan" ? "active" : ""}`}><input type="radio" name="external-kind" value="putusan" checked={externalKind === "putusan"} onChange={() => setExternalKind("putusan")} data-testid="external-kind-putusan" /> Sebagai Putusan</label>
        <label className={`kind-pill ${externalKind === "peraturan" ? "active" : ""}`}><input type="radio" name="external-kind" value="peraturan" checked={externalKind === "peraturan"} onChange={() => setExternalKind("peraturan")} data-testid="external-kind-peraturan" /> Sebagai Peraturan</label>
      </div>
      <textarea className="external-textarea" data-testid="external-links-input" rows="4" value={externalLinks} onChange={(event) => setExternalLinks(event.target.value)} placeholder={"https://drive.google.com/file/d/... /view\nhttps://www.dropbox.com/s/.../putusan.pdf?dl=0\nhttps://1drv.ms/b/s!..."} />
      <div className="external-actions">
        <button className="outline-button" data-testid="external-preview-button" disabled={externalBusy} onClick={previewExternalLinks}>Pratinjau tautan</button>
        <button className="primary-button" data-testid="external-import-button" disabled={externalBusy || !parseExternalUrls().length} onClick={importExternalLinks}>{externalBusy ? "Memproses…" : "Impor semua"}</button>
      </div>
      {externalPreviews.length > 0 && <div className="external-previews" data-testid="external-previews">{externalPreviews.map((p) => <div key={p.url} className={`preview-row preview-${p.status}`} data-testid={`external-preview-${p.status}`}><div className="preview-row-head"><span className={`provider-badge provider-${(p.provider || "").toLowerCase().replace(/\s/g, "-")}`}>{p.provider || "URL"}</span><strong>{p.filename || p.url.split("/").pop() || "—"}</strong>{p.detected_format && <span className="format-badge">{p.detected_format}</span>}{p.size_kb != null && <span className="size-badge">{p.size_kb} KB</span>}</div><div className="preview-row-sub">{p.status === "loading" && "Memuat pratinjau…"}{p.status === "importing" && "Mengambil & memproses…"}{p.status === "preview" && "Siap diimpor"}{p.status === "done" && "✓ Berhasil diimpor"}{p.status === "error" && `✕ ${p.error}`}</div><small className="preview-url">{p.url}</small></div>)}</div>}
    </div></div>}
    {filesOpen && <div className="modal-backdrop" data-testid="files-modal"><div className="peraturan-modal"><div className="modal-head"><div><span className="eyebrow">PENYIMPANAN FILE</span><h2>File Tersimpan</h2></div><button className="icon-button" data-testid="files-close-button" onClick={() => setFilesOpen(false)}><X size={17} /></button></div><p className="modal-copy">Semua file asli (PDF/DOCX/TXT) yang Anda unggah atau impor dari URL tersimpan aman di object storage. Unduh kembali kapan saja.</p>
      <div className="files-toolbar"><button className="outline-button" data-testid="files-refresh-button" onClick={loadFiles}><FolderOpen size={15} /> Muat ulang</button><span className="files-count">{files.length} file</span></div>
      <div className="files-list" data-testid="files-list">
        {filesLoading ? <div className="peraturan-empty">Memuat…</div> : files.length === 0 ? <div className="peraturan-empty" data-testid="files-empty">Belum ada file tersimpan. Unggah putusan atau peraturan untuk mengisi penyimpanan.</div> :
          files.map((f) => <div key={f.id} className="file-row" data-testid={`file-row-${f.id}`}>
            <div className="file-row-main"><span className={`tag ${f.linked_type === "peraturan" ? "" : "blue-tag"}`}>{f.linked_type === "peraturan" ? "PERATURAN" : "PUTUSAN"}</span><strong className="file-name">{f.original_filename}</strong><small>{(f.size / 1024).toFixed(1)} KB · {new Date(f.created_at).toLocaleString("id-ID")}</small></div>
            <div className="file-row-actions"><button className="outline-button" data-testid={`file-download-${f.id}`} onClick={() => downloadOriginal(f.id, f.original_filename)}><Download size={14} /> Unduh</button><button className="icon-button" data-testid={`file-delete-${f.id}`} title="Hapus dari daftar" onClick={() => deleteFile(f.id)}><Trash2 size={15} /></button></div>
          </div>)}
      </div>
    </div></div>}
    {previewPdf && <div className="modal-backdrop" data-testid="pdf-preview-modal" onClick={() => setPreviewPdf(null)}><div className="pdf-preview-dialog" onClick={(e) => e.stopPropagation()}>
      <div className="modal-head"><div><span className="eyebrow">PRATINJAU CEPAT</span><h2 data-testid="pdf-preview-title">{previewPdf.title}</h2></div><div className="pdf-preview-actions"><button className="outline-button" data-testid="pdf-preview-download" onClick={() => window.open(previewPdf.downloadUrl, "_blank")}><Download size={15} /> Unduh PDF</button><button className="icon-button" data-testid="pdf-preview-close" onClick={() => setPreviewPdf(null)}><X size={17} /></button></div></div>
      <div className="pdf-viewer pdf-viewer-modal" data-testid="pdf-preview-viewer"><PdfFrame url={previewPdf.url} testId="pdf-preview-frame" /></div>
    </div></div>}

    {toastMsg && <div className="toast" data-testid="toast-message">{toastMsg}</div>}
  </div>;
};

function App() { return <BrowserRouter><Home /></BrowserRouter>; }
export default App;