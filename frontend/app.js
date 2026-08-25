// @ts-check
/**
 * API 契约类型由 scripts/gen_frontend_types.py 从后端 OpenAPI 自动生成
 * （frontend/api-types.ts）；后端 DTO 变更后重新生成即可让编辑器标出失配。
 * 重新生成：.venv\Scripts\python.exe scripts\gen_frontend_types.py
 * @typedef {import('./api-types.ts').ParseJobResponse} ParseJobResponse
 * @typedef {import('./api-types.ts').ParserListResponse} ParserListResponse
 * @typedef {import('./api-types.ts').QualityPackageResponse} QualityPackageResponse
 * @typedef {import('./api-types.ts').QualityPackage} QualityPackage
 * @typedef {import('./api-types.ts').ParserCapability} ParserCapability
 * @typedef {{ path: string, size_bytes: number, file_type: string, category?: string }} PackageFileEntry
 */
const state = {
  /** @type {ParserCapability[]} */
  parsers: [],
  /** @type {ParseJobResponse | null} */
  lastResponse: null,
  /** @type {QualityPackage | null} */
  lastQuality: null,
};
const $ = (id) => document.getElementById(id);
const PARSER_LABELS = { "microsoft.markitdown": "通用文档解析", docling: "Docling 结构化解析", mineru: "MinerU 版面解析", ocr: "OCR 图片识别", anydoc: "AnyDoc Office 解析" };
const PARSER_HINTS = { "microsoft.markitdown": "适合 Word、Markdown、PDF 和常见办公文档。", docling: "适合需要结构化内容、表格和版面信息的文档。", mineru: "适合 PDF 和图片；当前环境可能需要云端 Token 或本地模型。", ocr: "适合扫描件和图片；需要本机 OCR 能力。", anydoc: "适合 Office 文件；需要单独安装 AnyDoc。" };
const QUALITY_LABELS = { pass: "质量通过", pass_with_warnings: "通过，但有提醒", manual_review_required: "建议人工复核", reparse_required: "建议重新解析", rejected: "未通过" };
const SEVERITY_LABELS = { critical: "严重问题", error: "错误", warning: "提醒", info: "信息" };

function setStatus(text, kind = "") { const status = $("appStatus"); status.className = `status ${kind}`.trim(); status.querySelector("span:last-child").textContent = text; }
function setBusy(buttonId, busy, busyText) { const button = $(buttonId); button.disabled = busy; if (busy) { button.dataset.originalText = button.querySelector("span")?.textContent || button.textContent; if (button.querySelector("span")) button.querySelector("span").textContent = busyText; else button.textContent = busyText; } else if (button.dataset.originalText) { if (button.querySelector("span")) button.querySelector("span").textContent = button.dataset.originalText; else button.textContent = button.dataset.originalText; } }
function parserLabel(id) { return PARSER_LABELS[id] || id || "自动选择"; }
function formatBytes(bytes) { if (!Number.isFinite(bytes) || bytes <= 0) return ""; if (bytes < 1024) return `${bytes} B`; if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`; return `${(bytes / 1024 / 1024).toFixed(1)} MB`; }

function populateParserSelects() {
  for (const select of [$("parserSelect"), $("reparseParser")]) {
    select.innerHTML = "";
    const auto = document.createElement("option"); auto.value = ""; auto.textContent = "自动选择（推荐）"; select.appendChild(auto);
    for (const parser of state.parsers) { const option = document.createElement("option"); option.value = parser.parser_id; option.textContent = `${parserLabel(parser.parser_id)}${parser.available ? "" : " · 环境未就绪"}`; option.title = PARSER_HINTS[parser.parser_id] || parser.unavailable_reason || ""; select.appendChild(option); }
  }
  updateParserHint();
}
function updateParserHint() { const id = $("parserSelect").value; if (!id) { $("parserHint").textContent = "推荐使用自动选择，系统会根据文件类型安排解析方式。"; return; } const parser = state.parsers.find((item) => item.parser_id === id); if (!parser) return; $("parserHint").textContent = parser.available ? (PARSER_HINTS[id] || "") : `${parser.unavailable_reason || "当前环境未报告此能力"} 可能返回降级结果。`; }
function buildOptions() { return { route_profile: $("routeProfile").value, allow_cloud: $("allowCloud").checked, libreoffice_available: $("libreofficeAvailable").checked }; }
function updateSelectedFile() { const file = $("fileInput").files[0]; $("fileName").textContent = file ? file.name : "点击选择文件"; $("fileHint").textContent = file ? `${formatBytes(file.size) || "文件"} · 已准备好解析` : "也可以把文件拖到这里"; }

function friendlyArtifactName(path) { const names = { "native/docling_document.json": "Docling 结构化结果", "native/mineru_result.json": "MinerU 结构化结果", "native/full.md": "解析后的 Markdown", "native/document.html": "HTML 文档预览", "parsed_document.json": "统一文档结果", "quality_package.json": "质量检查结果", "source/original.docx": "原始 DOCX 文件", "source/original.pdf": "原始 PDF 文件", "source/original.md": "原始 Markdown 文件" }; return names[path] || path.split("/").pop() || path; }
async function loadPackageFiles(parseId, fallbackArtifacts = []) {
  try {
    const response = await fetch(`/api/parses/${encodeURIComponent(parseId)}/artifacts`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "文件列表读取失败");
    renderArtifactLinks(parseId, payload.files || []);
  } catch (error) {
    renderArtifactLinks(parseId, fallbackArtifacts);
    $("artifactCount").title = error.message;
  }
}

/** @param {string} parseId @param {PackageFileEntry[]} artifacts */\nfunction renderArtifactLinks(parseId, artifacts) {
  const target = $("artifactsOutput");
  const downloadAll = $("downloadAllButton");
  target.innerHTML = "";
  $("artifactCount").textContent = `${artifacts.length} 个文件`;
  downloadAll.hidden = artifacts.length === 0;
  downloadAll.href = `/api/parses/${encodeURIComponent(parseId)}/download`;
  if (!artifacts.length) { target.innerHTML = '<p class="empty-state">本次没有可下载的文件。</p>'; return; }
  for (const artifact of artifacts) {
    const row = document.createElement("div"); row.className = "artifact-item";
    const name = document.createElement("span"); name.className = "artifact-name"; name.textContent = friendlyArtifactName(artifact.path); name.title = artifact.path;
    const meta = document.createElement("span"); meta.className = "artifact-meta"; meta.textContent = formatBytes(artifact.size_bytes) || artifact.file_type || "文件";
    const link = document.createElement("a"); link.href = `/api/parses/${encodeURIComponent(parseId)}/artifacts/${artifact.path.split("/").map(encodeURIComponent).join("/")}`; link.textContent = "下载"; link.target = "_blank";
    row.append(name, meta, link); target.appendChild(row);
  }
}
function renderWarnings(warnings) { const panel = $("warningsPanel"), target = $("warningList"); target.innerHTML = ""; const visible = [...new Set((warnings || []).filter(Boolean))]; panel.hidden = visible.length === 0; for (const warning of visible) { const item = document.createElement("li"); item.textContent = warning; target.appendChild(item); } }
function qualityStateLabel(state) { return QUALITY_LABELS[state] || state || "未生成"; }

/** @param {QualityPackage} packagePayload */\nfunction renderQualityPackage(packagePayload) {
  state.lastQuality = packagePayload; const report = packagePayload?.quality_report || {}, stateName = report.state || "unknown", stateElement = $("qualityState"); stateElement.textContent = qualityStateLabel(stateName); stateElement.className = `quality-state ${stateName}`;
  const issues = report.issues || []; $("issueCount").textContent = `${issues.length} 项`; $("qualitySummary").textContent = issues.length ? `${issues.length} 条检查结果，${(report.applied_repairs || []).length} 项已自动整理` : "未发现需要关注的问题";
  const target = $("qualityIssues"); target.innerHTML = "";
  if (!issues.length) target.innerHTML = '<p class="empty-state">这份文档没有发现需要关注的问题。</p>'; else { for (const issue of issues.slice(0, 6)) { const item = document.createElement("div"), severity = issue.severity || "info"; item.className = `issue-item ${severity}`; const tag = document.createElement("span"); tag.className = "issue-tag"; tag.textContent = SEVERITY_LABELS[severity] || severity; const message = document.createElement("p"); message.textContent = issue.message || "需要关注的质量问题"; item.append(tag, message); target.appendChild(item); } if (issues.length > 6) { const more = document.createElement("p"); more.className = "empty-state"; more.textContent = `还有 ${issues.length - 6} 条结果，请在技术详情中查看完整数据。`; target.appendChild(more); } }
  const repairs = report.applied_repairs || [], repairTarget = $("repairSummary"); repairTarget.hidden = repairs.length === 0; repairTarget.textContent = repairs.length ? `已自动整理 ${repairs.length} 项格式问题。` : ""; $("qualityOutput").textContent = JSON.stringify(packagePayload, null, 2);
}
async function loadQualityPackage(parseId) { try { const response = await fetch(`/api/parses/${encodeURIComponent(parseId)}/quality-package`), payload = await response.json(); if (!response.ok) throw new Error(payload.detail || `质量包读取失败：${response.status}`); renderQualityPackage(payload.quality_package); $("qualityMeta").textContent = `任务目录：${payload.package_path}`; } catch (error) { $("qualityState").textContent = "未生成"; $("qualityState").className = "quality-state"; $("qualitySummary").textContent = error.message; $("qualityIssues").innerHTML = '<p class="empty-state">暂时无法读取质量检查结果。</p>'; $("qualityMeta").textContent = error.message; } }

/** @param {ParseJobResponse} payload */\nfunction renderResponse(payload) {
  state.lastResponse = payload; const doc = payload.document || {}, provenance = doc.provenance || {}, routing = doc.routing_decision || {}, parseId = payload.parse_id || "", parserId = provenance.parser_id || routing.selected_parser_id || "", blocks = doc.blocks || [], tables = doc.tables || [], assets = doc.assets || [];
  $("resultSection").hidden = false; $("reparseId").value = parseId; $("resultSourceName").textContent = `${doc.filename || "文档"} · 任务编号 ${parseId}`; $("resultParser").textContent = parserLabel(parserId); $("resultRoute").textContent = routing.reason || (provenance.routing_mode === "manual" ? "手动指定" : "自动选择"); $("resultBlocks").textContent = blocks.length; $("resultTables").textContent = tables.length; $("resultAssets").textContent = `${tables.length} 张表格 · ${assets.length} 个附件`; $("markdownOutput").textContent = doc.markdown || "解析器没有返回可预览的正文内容。";
  $("routingOutput").textContent = JSON.stringify(routing, null, 2); $("documentOutput").textContent = JSON.stringify({ filename: doc.filename, file_type: doc.file_type, provenance, confidence: doc.confidence, capabilities: doc.capabilities, warnings: doc.warnings, blocks: blocks.length, tables: tables.length, assets: assets.length }, null, 2); loadPackageFiles(parseId, doc.native_artifacts || []); renderWarnings(doc.warnings || []); loadQualityPackage(parseId); $("resultSection").scrollIntoView({ behavior: "smooth", block: "start" });
}
async function loadParsers() { const response = await fetch("/api/parsers"); if (!response.ok) throw new Error(`解析方式列表加载失败：${response.status}`); state.parsers = (await response.json()).parsers || []; populateParserSelects(); }

async function submitParse(event) { event.preventDefault(); const file = $("fileInput").files[0]; if (!file) { setStatus("请先选择文件", "error"); return; } const formData = new FormData(); formData.set("file", file); if ($("parserSelect").value) formData.set("parser_id", $("parserSelect").value); formData.set("options_json", JSON.stringify(buildOptions())); setStatus("正在解析…", "busy"); setBusy("parseButton", true, "解析中…"); try { const response = await fetch("/api/parses", { method: "POST", body: formData }), payload = await response.json(); if (!response.ok) throw new Error(payload.detail || `解析失败：${response.status}`); renderResponse(payload); setStatus("解析完成"); } catch (error) { setStatus(error.message, "error"); } finally { setBusy("parseButton", false); } }
async function submitReparse(event) { event.preventDefault(); const parseId = $("reparseId").value.trim(); if (!parseId) { setStatus("没有可重新解析的任务", "error"); return; } setStatus("正在重新解析…", "busy"); setBusy("reparseButton", true, "处理中…"); try { const response = await fetch(`/api/parses/${encodeURIComponent(parseId)}/reparse`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parser_id: $("reparseParser").value || null, options: {} }) }), payload = await response.json(); if (!response.ok) throw new Error(payload.detail || `重新解析失败：${response.status}`); renderResponse(payload); setStatus("重新解析完成"); } catch (error) { setStatus(error.message, "error"); } finally { setBusy("reparseButton", false); } }

function bindFilePicker() { const input = $("fileInput"), dropzone = $("fileDropzone"); input.addEventListener("change", updateSelectedFile); for (const eventName of ["dragenter", "dragover"]) dropzone.addEventListener(eventName, (event) => { event.preventDefault(); dropzone.classList.add("dragover"); }); for (const eventName of ["dragleave", "drop"]) dropzone.addEventListener(eventName, (event) => { event.preventDefault(); dropzone.classList.remove("dragover"); }); dropzone.addEventListener("drop", (event) => { if (event.dataTransfer.files.length) { input.files = event.dataTransfer.files; updateSelectedFile(); } }); }
async function copyParseId() { const value = $("reparseId").value; if (!value) return; try { await navigator.clipboard.writeText(value); setStatus("任务编号已复制"); } catch { setStatus("任务编号：" + value); } }

document.addEventListener("DOMContentLoaded", async () => { bindFilePicker(); $("parserSelect").addEventListener("change", updateParserHint); $("parseForm").addEventListener("submit", submitParse); $("reparseForm").addEventListener("submit", submitReparse); $("copyParseId").addEventListener("click", copyParseId); try { await loadParsers(); setStatus("准备就绪"); } catch (error) { setStatus(error.message, "error"); } });
