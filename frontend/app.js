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
  /** @type {Map<string, string>} */
  artifactPreviewCache: new Map(),
};
const $ = (id) => document.getElementById(id);
const PARSER_LABELS = { "microsoft.markitdown": "通用文档解析", docling: "Docling 结构化解析", mineru: "MinerU 版面解析", ocr: "OCR 图片识别", anydoc: "AnyDoc Office 解析" };
const PARSER_HINTS = { "microsoft.markitdown": "适合 Word、Markdown、PDF 和常见办公文档。", docling: "适合需要结构化内容、表格和版面信息的文档。", mineru: "适合 PDF 和图片；当前环境可能需要云端 Token 或本地模型。", ocr: "适合扫描件和图片；需要本机 OCR 能力。", anydoc: "适合 Office 文件；需要单独安装 AnyDoc。" };
const QUALITY_LABELS = { pass: "质量通过", pass_with_warnings: "通过，但有提醒", reparse_required: "建议自动重新解析", rejected: "未通过" };
const SEVERITY_LABELS = { critical: "严重问题", error: "错误", warning: "提醒", info: "信息" };
const CAPABILITY_LABELS = { verified: "已验证", inferred: "根据结构推断", manual_review_required: "需要人工复核", reparse_required: "需要重新解析", rejected: "拒绝交付", unavailable: "信息不可用" };
const CAPABILITY_PRIORITY = { unavailable: 0, verified: 1, inferred: 2, manual_review_required: 3, reparse_required: 4, rejected: 5 };
const VIEW_SCOPE_LABELS = { all_rows: "全量行", visible_rows: "筛选后的可见行", unknown: "视图范围未知" };

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

function friendlyArtifactName(path) {
  const names = { "native/docling_document.json": "Docling 结构化结果", "native/mineru_result.json": "MinerU 结构化结果", "native/full.md": "解析后的 Markdown", "native/document.html": "HTML 文档预览", "parsed_document.json": "统一文档结果", "structure.json": "文档结构", "quality_issues.json": "质量问题和复核状态", "source/original.docx": "原始 DOCX 文件", "source/original.pdf": "原始 PDF 文件", "source/original.md": "原始 Markdown 文件" };
  const baseName = path.split("/").pop() || path;
  const baseNames = { "optimized.md": "质量修复后的 Markdown", "table_index.sqlite3": "大表查询索引" };
  return names[path] || baseNames[baseName] || baseName;
}

const DELIVERY_ARTIFACTS = {
  quality_markdown: { order: 1, code: "MD", role: "正文", description: "质量修复后的正文，供 Wiki 阅读、切分和检索。", tone: "markdown", previewable: true },
  document_structure: { order: 2, code: "JSON", role: "结构", description: "保留章节、表格、单元格关系与来源位置。", tone: "structure", previewable: true },
  quality_issues: { order: 3, code: "JSON", role: "状态", description: "说明哪些内容已修复、仍不确定或需要人工复核。", tone: "quality", previewable: true },
  table_index: { order: 4, code: "DB", role: "大表索引", description: "表格规模较大时生成，供下游按需查询。", tone: "database" },
};
const ARTIFACT_CATEGORY_LABELS = {
  parsed_document: "统一结果",
  parser_output: "解析器输出",
  source: "原始文件",
  asset: "附件",
  other: "其他文件",
};

function artifactDownloadUrl(parseId, path) {
  return `/api/parses/${encodeURIComponent(parseId)}/artifacts/${path.split("/").map(encodeURIComponent).join("/")}`;
}

function createDeliveryArtifact(parseId, artifact) {
  const config = DELIVERY_ARTIFACTS[artifact.category];
  const card = document.createElement("article");
  card.className = `delivery-artifact-card ${config.tone}`;
  const format = document.createElement("span");
  format.className = "artifact-format";
  format.textContent = config.code;
  const content = document.createElement("div");
  content.className = "delivery-artifact-content";
  const role = document.createElement("span");
  role.className = "artifact-role";
  role.textContent = config.role;
  const name = document.createElement("h4");
  name.textContent = friendlyArtifactName(artifact.path);
  const description = document.createElement("p");
  description.textContent = config.description;
  const meta = document.createElement("small");
  meta.textContent = `${artifact.path} · ${formatBytes(artifact.size_bytes) || artifact.file_type || "文件"}`;
  content.append(role, name, description, meta);
  const actions = document.createElement("div");
  actions.className = "delivery-artifact-actions";
  if (config.previewable) {
    const preview = document.createElement("button");
    preview.className = "artifact-preview-button";
    preview.type = "button";
    preview.dataset.artifactPath = artifact.path;
    preview.textContent = "预览";
    preview.addEventListener("click", () => showArtifactPreview(parseId, artifact));
    actions.appendChild(preview);
  }
  const link = document.createElement("a");
  link.className = "artifact-download-button";
  link.href = artifactDownloadUrl(parseId, artifact.path);
  link.textContent = "下载";
  link.target = "_blank";
  actions.appendChild(link);
  card.append(format, content, actions);
  return card;
}

function createSupportingArtifact(parseId, artifact) {
  const row = document.createElement("div");
  row.className = "supporting-artifact-item";
  const category = document.createElement("span");
  category.className = "artifact-category";
  category.textContent = ARTIFACT_CATEGORY_LABELS[artifact.category] || "过程文件";
  const content = document.createElement("div");
  content.className = "supporting-artifact-content";
  const name = document.createElement("strong");
  name.textContent = friendlyArtifactName(artifact.path);
  name.title = artifact.path;
  const path = document.createElement("small");
  path.textContent = artifact.path;
  content.append(name, path);
  const meta = document.createElement("span");
  meta.className = "artifact-meta";
  meta.textContent = formatBytes(artifact.size_bytes) || artifact.file_type || "文件";
  const link = document.createElement("a");
  link.href = artifactDownloadUrl(parseId, artifact.path);
  link.textContent = "下载";
  link.target = "_blank";
  row.append(category, content, meta, link);
  return row;
}

async function showArtifactPreview(parseId, artifact) {
  const panel = $("artifactPreviewPanel");
  const output = $("artifactPreviewOutput");
  if (!panel || !output) return;
  const cacheKey = `${parseId}/${artifact.path}`;
  panel.dataset.previewKey = cacheKey;
  output.dataset.kind = artifact.category === "quality_markdown" ? "markdown" : "json";
  $("artifactPreviewName").textContent = friendlyArtifactName(artifact.path);
  $("artifactPreviewMeta").textContent = `${artifact.path} · ${formatBytes(artifact.size_bytes) || artifact.file_type || "文件"}`;
  const download = $("artifactPreviewDownload");
  download.href = artifactDownloadUrl(parseId, artifact.path);
  document.querySelectorAll(".artifact-preview-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.artifactPath === artifact.path);
  });
  output.textContent = "正在读取文件内容…";
  $("artifactPreviewNote").textContent = "";

  try {
    let content = state.artifactPreviewCache.get(cacheKey);
    if (content === undefined) {
      const response = await fetch(artifactDownloadUrl(parseId, artifact.path));
      if (!response.ok) throw new Error(`文件读取失败：${response.status}`);
      content = await response.text();
      state.artifactPreviewCache.set(cacheKey, content);
    }
    if (panel.dataset.previewKey !== cacheKey) return;
    if (artifact.category !== "quality_markdown") {
      try { content = JSON.stringify(JSON.parse(content), null, 2); } catch { /* 保留原始文本，便于排查非标准 JSON。 */ }
    }
    const previewLimit = 60000;
    const truncated = content.length > previewLimit;
    output.textContent = truncated ? content.slice(0, previewLimit) : content;
    $("artifactPreviewNote").textContent = truncated
      ? `文件内容较长，当前展示前 ${previewLimit.toLocaleString("zh-CN")} 个字符；完整内容请下载查看。`
      : "当前展示的是实际交付文件内容。";
  } catch (error) {
    if (panel.dataset.previewKey !== cacheKey) return;
    output.textContent = error.message || "文件预览加载失败。";
    $("artifactPreviewNote").textContent = "可以尝试直接下载该文件。";
  }
}
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

/** @param {string} parseId @param {PackageFileEntry[]} artifacts */
function renderArtifactLinks(parseId, artifacts) {
  const target = $("artifactsOutput");
  const downloadAll = $("downloadAllButton");
  target.innerHTML = "";
  const delivery = artifacts
    .filter((artifact) => DELIVERY_ARTIFACTS[artifact.category])
    .sort((left, right) => DELIVERY_ARTIFACTS[left.category].order - DELIVERY_ARTIFACTS[right.category].order);
  const supporting = artifacts.filter((artifact) => !DELIVERY_ARTIFACTS[artifact.category]);
  $("artifactCount").textContent = delivery.length
    ? `${delivery.length} 个交付文件${supporting.length ? ` · ${supporting.length} 个其他文件` : ""}`
    : `${artifacts.length} 个文件`;
  downloadAll.hidden = artifacts.length === 0;
  downloadAll.href = `/api/parses/${encodeURIComponent(parseId)}/download`;
  if (!artifacts.length) { target.innerHTML = '<p class="empty-state">本次没有可下载的文件。</p>'; return; }

  if (delivery.length) {
    const heading = document.createElement("div");
    heading.className = "artifact-group-heading";
    heading.innerHTML = "<div><strong>Wiki 交付文件</strong><span>下游消费的正式结果</span></div>";
    const recommended = document.createElement("span");
    recommended.className = "artifact-recommended";
    recommended.textContent = "优先下载";
    heading.appendChild(recommended);
    const grid = document.createElement("div");
    grid.className = "delivery-artifact-grid";
    if (delivery.length === 4) grid.classList.add("four-artifacts");
    for (const artifact of delivery) grid.appendChild(createDeliveryArtifact(parseId, artifact));
    target.append(heading, grid);

    const previewable = delivery.filter((artifact) => DELIVERY_ARTIFACTS[artifact.category].previewable);
    if (previewable.length) {
      const preview = document.createElement("section");
      preview.id = "artifactPreviewPanel";
      preview.className = "artifact-preview-panel";
      preview.innerHTML = `
        <div class="artifact-preview-heading">
          <div>
            <span class="panel-kicker">文件内容预览</span>
            <h4 id="artifactPreviewName">请选择文件</h4>
            <small id="artifactPreviewMeta"></small>
          </div>
          <a id="artifactPreviewDownload" class="artifact-preview-download" href="#" target="_blank">下载当前文件</a>
        </div>
        <pre id="artifactPreviewOutput" class="artifact-preview-output">请选择上方文件进行预览。</pre>
        <p id="artifactPreviewNote" class="artifact-preview-note"></p>`;
      target.appendChild(preview);
      void showArtifactPreview(parseId, previewable[0]);
    }
  }

  if (supporting.length) {
    const details = document.createElement("details");
    details.className = "supporting-artifacts";
    const summary = document.createElement("summary");
    summary.innerHTML = `<span><strong>其他过程文件</strong><small>原始文件、解析器输出和内部统一结果</small></span><b>${supporting.length} 个</b>`;
    const list = document.createElement("div");
    list.className = "supporting-artifact-list";
    for (const artifact of supporting) list.appendChild(createSupportingArtifact(parseId, artifact));
    details.append(summary, list);
    target.appendChild(details);
  }
}
function renderWarnings(warnings) { const panel = $("warningsPanel"), target = $("warningList"); target.innerHTML = ""; const visible = [...new Set((warnings || []).filter(Boolean))]; panel.hidden = visible.length === 0; for (const warning of visible) { const item = document.createElement("li"); item.textContent = warning; target.appendChild(item); } }
function qualityStateLabel(state) { return QUALITY_LABELS[state] || state || "未生成"; }
function capabilityStateLabel(stateName) { return CAPABILITY_LABELS[stateName] || stateName || "信息不可用"; }

function worstCapabilityState(states) {
  return states.filter(Boolean).sort((left, right) => (CAPABILITY_PRIORITY[right] ?? -1) - (CAPABILITY_PRIORITY[left] ?? -1))[0] || "unavailable";
}

function canonicalCellText(cell) {
  const value = cell.display_value ?? cell.normalized_value ?? cell.text ?? cell.raw_value ?? "";
  return String(value);
}

function tableSourceLabel(table) {
  const locator = table.source_locator || {};
  const parts = [];
  if (locator.container_name) parts.push(locator.container_name);
  if (locator.range_ref) parts.push(locator.range_ref);
  if (locator.page_number) parts.push("第 " + locator.page_number + " 页");
  return parts.join(" · ") || table.table_id;
}

function clearCellJsonInspector() {
  $("selectedCellLabel").textContent = "尚未选择单元格";
  $("selectedCellJson").textContent = "点击上方表格中的任意单元格后，仅显示该单元格及其关联绑定。";
}

function bindingRolesForCell(binding, cellId) {
  const roles = [];
  if ((binding.row_cell_ids || []).includes(cellId)) roles.push("行路径");
  if ((binding.column_cell_ids || []).includes(cellId)) roles.push("列路径");
  if (binding.value_cell_id === cellId) roles.push("数值");
  return roles;
}

function showCellJson(table, cell, bindings, cellElement) {
  const cellId = cell.cell_id || (table.table_id + ":r" + cell.start_row + "c" + cell.start_col);
  const matchingBindings = bindings.filter((binding) => bindingRolesForCell(binding, cellId).length > 0);
  const bindingReferences = matchingBindings.slice(0, 20).map((binding) => ({
    binding_id: binding.binding_id,
    roles: bindingRolesForCell(binding, cellId),
    row_path: binding.row_path || [binding.row_key],
    column_path: binding.column_path,
    value: binding.value,
    value_cell_id: binding.value_cell_id,
    status: binding.status,
    source_locator: binding.source_locator,
  }));
  const payload = {
    table_id: table.table_id,
    cell,
    matching_binding_count: matchingBindings.length,
    binding_references: bindingReferences,
    binding_references_truncated: matchingBindings.length > bindingReferences.length,
  };

  document.querySelectorAll("#canonicalTablePreview .cell-json-selected").forEach((item) => item.classList.remove("cell-json-selected"));
  cellElement.classList.add("cell-json-selected");
  const sourceRef = cell.source_anchor?.cell_ref;
  $("selectedCellLabel").textContent = sourceRef || ("第 " + (cell.start_row + 1) + " 行，第 " + (cell.start_col + 1) + " 列");
  $("selectedCellJson").textContent = JSON.stringify(payload, null, 2);
}

function renderTableQuality(packagePayload) {
  const canonical = packagePayload?.canonical_document || {};
  const tables = canonical.tables || [];
  const panel = $("tableQualityPanel");
  panel.hidden = tables.length === 0;
  if (!tables.length) return;

  $("canonicalTableCount").textContent = tables.length + " 张表格";
  const select = $("canonicalTableSelect");
  const previous = select.value;
  select.innerHTML = "";
  tables.forEach((table, index) => {
    const option = document.createElement("option");
    option.value = table.table_id;
    const source = table.source_locator?.container_name;
    option.textContent = "表格 " + (index + 1) + " · " + table.num_rows + " 行 × " + table.num_cols + " 列" + (source ? " · " + source : "");
    select.appendChild(option);
  });
  if (tables.some((table) => table.table_id === previous)) select.value = previous;
  renderSelectedCanonicalTable();
}

function renderSelectedCanonicalTable() {
  const canonical = state.lastQuality?.canonical_document || {};
  const tables = canonical.tables || [];
  const table = tables.find((item) => item.table_id === $("canonicalTableSelect").value) || tables[0];
  if (!table) return;

  const bindings = (canonical.table_bindings || []).filter((binding) => binding.table_id === table.table_id);
  const cells = table.cells || [];
  const mergedCells = cells.filter((cell) => (cell.row_span || 1) > 1 || (cell.col_span || 1) > 1);
  const tableState = worstCapabilityState([table.header_state, ...bindings.map((binding) => binding.status)]);

  $("tableGridSize").textContent = table.num_rows + " × " + table.num_cols;
  $("mergedCellCount").textContent = String(mergedCells.length);
  $("tableBindingCount").textContent = String(bindings.length);
  $("tableQualityState").textContent = capabilityStateLabel(tableState);
  $("tableQualityState").dataset.state = tableState;
  $("tableSourceLocation").textContent = tableSourceLabel(table);

  clearCellJsonInspector();
  renderCanonicalTablePreview(table, bindings);
  renderTableBindings(table, bindings);
}

function renderCanonicalTablePreview(table, bindings) {
  const target = $("canonicalTablePreview");
  const note = $("tablePreviewNote");
  target.innerHTML = "";
  const cells = table.cells || [];
  if (!cells.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "该表格的完整单元格已外置到 table_index.sqlite3，页面不一次加载整张大表。";
    target.appendChild(empty);
    note.textContent = "仍可按表格、行路径、列路径或源单元格位置查询。";
    return;
  }

  const inferredRows = Math.max(0, ...cells.map((cell) => cell.start_row + (cell.row_span || 1)));
  const inferredCols = Math.max(0, ...cells.map((cell) => cell.start_col + (cell.col_span || 1)));
  const totalRows = table.num_rows || inferredRows;
  const totalCols = table.num_cols || inferredCols;
  const visibleRows = Math.min(totalRows, 12);
  const visibleCols = Math.min(totalCols, 8);
  const cellsByStart = new Map();
  cells.forEach((cell) => cellsByStart.set(cell.start_row + ":" + cell.start_col, cell));

  const occupied = new Set();
  const headerRows = new Set(table.header_row_indices || []);
  if (!headerRows.size && Number.isInteger(table.header_rows)) {
    for (let row = 0; row < table.header_rows; row += 1) headerRows.add(row);
  }

  const scroll = document.createElement("div");
  scroll.className = "canonical-table-scroll";
  const tableElement = document.createElement("table");
  tableElement.className = "canonical-table";
  const body = document.createElement("tbody");

  for (let row = 0; row < visibleRows; row += 1) {
    const rowElement = document.createElement("tr");
    for (let col = 0; col < visibleCols; col += 1) {
      const key = row + ":" + col;
      if (occupied.has(key)) continue;
      const cell = cellsByStart.get(key);
      const cellElement = document.createElement(cell && (cell.column_header || headerRows.has(row)) ? "th" : "td");
      if (!cell) {
        cellElement.className = "table-empty-cell";
        cellElement.textContent = " ";
        rowElement.appendChild(cellElement);
        continue;
      }

      const rowSpan = Math.min(cell.row_span || 1, visibleRows - row);
      const colSpan = Math.min(cell.col_span || 1, visibleCols - col);
      cellElement.rowSpan = rowSpan;
      cellElement.colSpan = colSpan;
      cellElement.textContent = canonicalCellText(cell) || " ";
      if (cell.cell_id) cellElement.dataset.cellId = cell.cell_id;
      if (cell.row_header) cellElement.classList.add("table-row-header");
      if (rowSpan > 1 || colSpan > 1) cellElement.classList.add("table-merged-cell");
      const sourceRef = cell.source_anchor?.cell_ref;
      if (sourceRef) cellElement.title = "源单元格：" + sourceRef;
      cellElement.tabIndex = 0;
      cellElement.setAttribute("role", "button");
      cellElement.setAttribute("aria-label", "查看单元格 " + (sourceRef || canonicalCellText(cell) || key) + " 的 JSON");
      cellElement.addEventListener("click", () => showCellJson(table, cell, bindings, cellElement));
      cellElement.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          showCellJson(table, cell, bindings, cellElement);
        }
      });

      for (let coveredRow = row; coveredRow < row + rowSpan; coveredRow += 1) {
        for (let coveredCol = col; coveredCol < col + colSpan; coveredCol += 1) {
          if (coveredRow !== row || coveredCol !== col) occupied.add(coveredRow + ":" + coveredCol);
        }
      }
      rowElement.appendChild(cellElement);
    }
    body.appendChild(rowElement);
  }

  tableElement.appendChild(body);
  scroll.appendChild(tableElement);
  target.appendChild(scroll);

  const previewParts = [];
  if (totalRows > visibleRows || totalCols > visibleCols) previewParts.push("页面展示前 " + visibleRows + " 行、" + visibleCols + " 列");
  previewParts.push(VIEW_SCOPE_LABELS[table.view_scope] || "视图范围未知");
  if (table.hidden_row_count) previewParts.push(table.hidden_row_count + " 行未显示");
  note.textContent = previewParts.join(" · ");
}

function addBindingPath(parent, label, value) {
  const line = document.createElement("div");
  line.className = "binding-path-line";
  const name = document.createElement("span");
  name.textContent = label;
  const content = document.createElement("strong");
  content.textContent = value || "未确定";
  line.append(name, content);
  parent.appendChild(line);
}

function highlightTableBinding(binding, activeButton) {
  const rowCells = new Set(binding.row_cell_ids || []);
  const columnCells = new Set(binding.column_cell_ids || []);
  const valueCell = binding.value_cell_id;
  document.querySelectorAll("#canonicalTablePreview [data-cell-id]").forEach((cell) => {
    cell.classList.remove("binding-row-cell", "binding-column-cell", "binding-value-cell");
    const cellId = cell.dataset.cellId;
    if (rowCells.has(cellId)) cell.classList.add("binding-row-cell");
    if (columnCells.has(cellId)) cell.classList.add("binding-column-cell");
    if (cellId === valueCell) cell.classList.add("binding-value-cell");
  });
  document.querySelectorAll(".table-binding-item").forEach((item) => item.classList.remove("active"));
  if (activeButton) activeButton.classList.add("active");
}

function renderTableBindings(table, bindings) {
  const target = $("tableBindings");
  target.innerHTML = "";
  if (!bindings.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "该表格保留了结构，但当前没有生成可安全查询的字段绑定。请结合质量状态决定是否复核。";
    target.appendChild(empty);
    return;
  }

  let firstButton = null;
  bindings.slice(0, 10).forEach((binding) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "table-binding-item";
    addBindingPath(button, "行", (binding.row_path || []).join(" / ") || binding.row_key);
    addBindingPath(button, "列", (binding.column_path || []).join(" → "));

    const result = document.createElement("div");
    result.className = "binding-result";
    const value = document.createElement("strong");
    value.textContent = binding.value || "空值";
    const meta = document.createElement("span");
    const locator = binding.source_locator || {};
    const source = locator.cell_ref || locator.table_cell || tableSourceLabel(table);
    meta.textContent = capabilityStateLabel(binding.status) + " · " + source;
    meta.dataset.state = binding.status;
    result.append(value, meta);
    button.appendChild(result);
    button.addEventListener("click", () => highlightTableBinding(binding, button));
    target.appendChild(button);
    if (!firstButton) firstButton = button;
  });

  if (bindings.length > 10) {
    const more = document.createElement("p");
    more.className = "table-preview-note";
    more.textContent = "当前展示 10 条，共 " + bindings.length + " 条；完整记录可在 structure.json 或大表索引中查询。";
    target.appendChild(more);
  }
  highlightTableBinding(bindings[0], firstButton);
}

/** @param {QualityPackage} packagePayload */
function renderQualityPackage(packagePayload) {
  state.lastQuality = packagePayload; const report = packagePayload?.quality_report || {}, stateName = report.state || "unknown", stateElement = $("qualityState"); stateElement.textContent = qualityStateLabel(stateName); stateElement.className = `quality-state ${stateName}`;
  const issues = report.issues || []; $("issueCount").textContent = `${issues.length} 项`; $("qualitySummary").textContent = issues.length ? `${issues.length} 条检查结果，${(report.applied_repairs || []).length} 项已自动整理` : "未发现需要关注的问题";
  const target = $("qualityIssues"); target.innerHTML = "";
  if (!issues.length) target.innerHTML = '<p class="empty-state">这份文档没有发现需要关注的问题。</p>'; else { for (const issue of issues.slice(0, 6)) { const item = document.createElement("div"), severity = issue.severity || "info"; item.className = `issue-item ${severity}`; const tag = document.createElement("span"); tag.className = "issue-tag"; tag.textContent = `${SEVERITY_LABELS[severity] || severity}${issue.rule_id ? ` · ${issue.rule_id}` : ""}`; tag.title = issue.category || ""; const message = document.createElement("p"); message.textContent = issue.message || "需要关注的质量问题"; item.append(tag, message); target.appendChild(item); } if (issues.length > 6) { const more = document.createElement("p"); more.className = "empty-state"; more.textContent = `还有 ${issues.length - 6} 条结果，请在技术详情中查看完整数据。`; target.appendChild(more); } }
  const repairs = report.applied_repairs || [], repairTarget = $("repairSummary"); repairTarget.hidden = repairs.length === 0; repairTarget.textContent = repairs.length ? `已自动整理 ${repairs.length} 项格式问题。` : ""; $("qualityOutput").textContent = JSON.stringify(packagePayload, null, 2);
  renderTableQuality(packagePayload);
}
async function loadQualityPackage(parseId) { try { const response = await fetch(`/api/parses/${encodeURIComponent(parseId)}/quality-package`), payload = await response.json(); if (!response.ok) throw new Error(payload.detail || `质量包读取失败：${response.status}`); renderQualityPackage(payload.quality_package); $("qualityMeta").textContent = `任务目录：${payload.package_path}`; } catch (error) { $("qualityState").textContent = "未生成"; $("qualityState").className = "quality-state"; $("qualitySummary").textContent = error.message; $("qualityIssues").innerHTML = '<p class="empty-state">暂时无法读取质量检查结果。</p>'; $("qualityMeta").textContent = error.message; } }

/** @param {ParseJobResponse} payload */
function renderResponse(payload) {
  $("tableQualityPanel").hidden = true;
  state.lastResponse = payload; const doc = payload.document || {}, provenance = doc.provenance || {}, routing = doc.routing_decision || {}, parseId = payload.parse_id || "", parserId = provenance.parser_id || routing.selected_parser_id || "", blocks = doc.blocks || [], tables = doc.tables || [], assets = doc.assets || [];
  $("resultSection").hidden = false; $("reparseId").value = parseId; $("resultSourceName").textContent = `${doc.filename || "文档"} · 任务编号 ${parseId}`; $("resultParser").textContent = parserLabel(parserId); $("resultRoute").textContent = routing.reason || (provenance.routing_mode === "manual" ? "手动指定" : "自动选择"); $("resultBlocks").textContent = blocks.length; $("resultTables").textContent = tables.length; $("resultAssets").textContent = `${tables.length} 张表格 · ${assets.length} 个附件`; $("markdownOutput").textContent = doc.markdown || "解析器没有返回可预览的正文内容。";
  $("routingOutput").textContent = JSON.stringify(routing, null, 2); $("documentOutput").textContent = JSON.stringify({ filename: doc.filename, file_type: doc.file_type, provenance, confidence: doc.confidence, capabilities: doc.capabilities, warnings: doc.warnings, blocks: blocks.length, tables: tables.length, assets: assets.length }, null, 2); loadPackageFiles(parseId, doc.native_artifacts || []); renderWarnings(doc.warnings || []); loadQualityPackage(parseId); $("resultSection").scrollIntoView({ behavior: "smooth", block: "start" });
}
async function loadParsers() { const response = await fetch("/api/parsers"); if (!response.ok) throw new Error(`解析方式列表加载失败：${response.status}`); state.parsers = (await response.json()).parsers || []; populateParserSelects(); }

async function submitParse(event) { event.preventDefault(); const file = $("fileInput").files[0]; if (!file) { setStatus("请先选择文件", "error"); return; } const formData = new FormData(); formData.set("file", file); if ($("parserSelect").value) formData.set("parser_id", $("parserSelect").value); formData.set("options_json", JSON.stringify(buildOptions())); setStatus("正在解析…", "busy"); setBusy("parseButton", true, "解析中…"); try { const response = await fetch("/api/parses", { method: "POST", body: formData }), payload = await response.json(); if (!response.ok) throw new Error(payload.detail || `解析失败：${response.status}`); renderResponse(payload); setStatus("解析完成"); } catch (error) { setStatus(error.message, "error"); } finally { setBusy("parseButton", false); } }
async function submitReparse(event) { event.preventDefault(); const parseId = $("reparseId").value.trim(); if (!parseId) { setStatus("没有可重新解析的任务", "error"); return; } setStatus("正在重新解析…", "busy"); setBusy("reparseButton", true, "处理中…"); try { const response = await fetch(`/api/parses/${encodeURIComponent(parseId)}/reparse`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parser_id: $("reparseParser").value || null, options: {} }) }), payload = await response.json(); if (!response.ok) throw new Error(payload.detail || `重新解析失败：${response.status}`); renderResponse(payload); setStatus("重新解析完成"); } catch (error) { setStatus(error.message, "error"); } finally { setBusy("reparseButton", false); } }

function bindFilePicker() { const input = $("fileInput"), dropzone = $("fileDropzone"); input.addEventListener("change", updateSelectedFile); for (const eventName of ["dragenter", "dragover"]) dropzone.addEventListener(eventName, (event) => { event.preventDefault(); dropzone.classList.add("dragover"); }); for (const eventName of ["dragleave", "drop"]) dropzone.addEventListener(eventName, (event) => { event.preventDefault(); dropzone.classList.remove("dragover"); }); dropzone.addEventListener("drop", (event) => { if (event.dataTransfer.files.length) { input.files = event.dataTransfer.files; updateSelectedFile(); } }); }
async function copyParseId() { const value = $("reparseId").value; if (!value) return; try { await navigator.clipboard.writeText(value); setStatus("任务编号已复制"); } catch { setStatus("任务编号：" + value); } }

const LIFECYCLE_LABELS = { added: "新增", modified: "修改", moved: "移动", deleted: "删除", unchanged: "未变化", retry: "重试" };
function updateLifecycleFileName() {
  const file = $("lifecycleFileInput").files[0];
  $("lifecycleFileName").textContent = file ? file.name : "选择演示文件";
}

function lifecycleFileType(path) {
  const extension = String(path || "").split(".").pop();
  return extension && extension !== path ? extension.slice(0, 5).toUpperCase() : "FILE";
}

function formatLifecycleTime(value) {
  if (!value) return "未记录更新时间";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}

function appendEmptyState(target, text) {
  const empty = document.createElement("p");
  empty.className = "empty-state";
  empty.textContent = text;
  target.appendChild(empty);
}

function renderLifecycle(payload, events = []) {
  const manifest = payload.manifest || {}, sources = Object.values(manifest.sources || {});
  if (payload.raw_root) $("lifecycleRawRoot").textContent = payload.raw_root;
  $("lifecycleTechnical").textContent = JSON.stringify({ state_root: payload.state_root, manifest }, null, 2);

  const currentSources = sources.filter((source) => source.state !== "deleted").sort((left, right) => left.path.localeCompare(right.path, "zh-CN"));
  const activeSources = currentSources.filter((source) => source.state === "active");
  const attentionSources = currentSources.filter((source) => source.state === "parse_failed");
  const counts = events.reduce((result, event) => {
    result[event.kind] = (result[event.kind] || 0) + 1;
    return result;
  }, {});

  $("lifecycleActiveCount").textContent = String(activeSources.length);
  $("lifecycleAddedCount").textContent = String(counts.added || 0);
  $("lifecycleChangedCount").textContent = String((counts.modified || 0) + (counts.moved || 0));
  $("lifecycleAttentionCount").textContent = String(attentionSources.length);
  $("lifecycleEventCount").textContent = events.length + " 项";
  $("lifecycleSourceCount").textContent = currentSources.length + " 份";

  const eventTarget = $("lifecycleEvents");
  eventTarget.innerHTML = "";
  if (!events.length) appendEmptyState(eventTarget, "本次没有文件变化。");
  events.slice(0, 20).forEach((event) => {
    const row = document.createElement("div");
    row.className = "lifecycle-event-item " + event.kind + (event.error ? " failed" : "");

    const kind = document.createElement("span");
    kind.className = "lifecycle-event-kind";
    kind.textContent = LIFECYCLE_LABELS[event.kind] || event.kind;

    const content = document.createElement("div");
    content.className = "lifecycle-event-content";
    const path = document.createElement("code");
    path.textContent = event.path;
    const meta = document.createElement("small");
    const details = [];
    if (event.previous_path) details.push("原位置：" + event.previous_path);
    if (event.parser_id) details.push(parserLabel(event.parser_id));
    if (event.error) details.push(event.error);
    meta.textContent = details.join(" · ") || "变化已记录";
    if (event.error) meta.title = event.error;
    content.append(path, meta);

    const status = document.createElement("span");
    status.className = "lifecycle-event-state";
    status.dataset.state = event.error ? "rejected" : (event.quality_state || "verified");
    status.textContent = event.error ? "处理失败" : (event.quality_state ? qualityStateLabel(event.quality_state) : "已记录");
    row.append(kind, content, status);
    eventTarget.appendChild(row);
  });
  if (events.length > 20) appendEmptyState(eventTarget, "另有 " + (events.length - 20) + " 条变化记录，可在落盘记录中查看。");

  const sourceTarget = $("lifecycleSources");
  sourceTarget.innerHTML = "";
  if (!currentSources.length) appendEmptyState(sourceTarget, "监控目录中暂无文档。");
  currentSources.forEach((source) => {
    const row = document.createElement("div");
    row.className = "lifecycle-source-item" + (source.state === "parse_failed" ? " failed" : "");

    const fileType = document.createElement("span");
    fileType.className = "lifecycle-file-type";
    fileType.textContent = lifecycleFileType(source.path);

    const content = document.createElement("div");
    content.className = "lifecycle-source-content";
    const path = document.createElement("code");
    path.textContent = source.path;
    const meta = document.createElement("small");
    const details = [source.parser_id ? parserLabel(source.parser_id) : "等待解析", formatLifecycleTime(source.updated_at)];
    meta.textContent = details.join(" · ");
    content.append(path, meta);

    const states = document.createElement("div");
    states.className = "lifecycle-source-states";
    const sourceState = document.createElement("span");
    sourceState.className = "source-state";
    sourceState.dataset.state = source.state;
    sourceState.textContent = source.state === "active" ? "生效" : "解析失败";
    const quality = document.createElement("span");
    quality.className = "source-quality";
    quality.dataset.state = source.quality_state || "unavailable";
    quality.textContent = source.quality_state ? qualityStateLabel(source.quality_state) : "等待质量结论";
    states.append(sourceState, quality);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "lifecycle-delete";
    remove.textContent = "移出";
    remove.title = "从监控目录删除并重新扫描";
    remove.addEventListener("click", () => deleteLifecycleSource(source.path));
    row.append(fileType, content, states, remove);
    sourceTarget.appendChild(row);
  });

  const countText = Object.entries(counts).map(([kind, count]) => (LIFECYCLE_LABELS[kind] || kind) + " " + count).join(" · ");
  $("lifecycleSummary").textContent = events.length
    ? "扫描完成：" + countText + "；当前 " + activeSources.length + " 份文档生效"
    : "当前 " + activeSources.length + " 份文档生效，等待下一次扫描";
  $("lifecycleSummary").classList.toggle("has-attention", attentionSources.length > 0);
  renderDownstream(payload.delivery || {}, payload.multimodal_delivery || {});
}
function renderDownstream(delivery, multimodal = {}) {
  const sources = delivery.sources || [], active = sources.filter((item) => item.state === "active");
  $("downstreamState").textContent = delivery.configured ? "适配器已连接" : "未配置";
  $("downstreamSummary").textContent = delivery.configured ? `已向 Wiki 发布 ${delivery.active_count || 0} 份，已撤回 ${delivery.deleted_count || 0} 份；只有质量通过结果可进入此目录` : "下游适配器尚未配置";
  $("downstreamRoot").textContent = delivery.watched_sources_root || "未配置";
  $("multimodalSummary").textContent = multimodal.configured ? `已生成 ${multimodal.ready_count || 0} 个待增强包，已撤回 ${multimodal.withdrawn_count || 0} 个 Source` : "多模态适配器尚未配置";
  $("multimodalRoot").textContent = multimodal.root || "未配置";
  $("downstreamTechnical").textContent = JSON.stringify({ contracts: { multimodal: "ParsedDocument → mmwiki-0.1 package", markdown: "raw/sources/{原文件名}.md", assets: "raw/assets/{source_id}/", quality: "raw/metadata/{source_id}/quality_package.json", accepted_quality_states: ["pass", "pass_with_warnings"] }, multimodal, delivery }, null, 2);
  const target = $("downstreamSources"); target.innerHTML = "";
  if (!active.length) target.innerHTML = '<p class="empty-state">暂无已发布文档；质量未通过的结果不会覆盖下游。</p>';
  for (const item of active) { const row = document.createElement("div"); row.className = "lifecycle-item"; const badge = document.createElement("span"); badge.className = "lifecycle-kind"; badge.textContent = "已发布"; const path = document.createElement("code"); path.textContent = item.source_path || item.parser_source_id; const quality = document.createElement("span"); quality.textContent = qualityStateLabel(item.quality_state); row.append(badge, path, quality); target.appendChild(row); }
}
async function loadLifecycle() { const response = await fetch("/api/lifecycle"), payload = await response.json(); if (!response.ok) throw new Error(payload.detail || "生命周期状态加载失败"); renderLifecycle(payload); }
async function scanLifecycle() { setBusy("scanLifecycleButton", true, "扫描中…"); setStatus("正在扫描监控目录…", "busy"); try { const response = await fetch("/api/lifecycle/scan", { method: "POST" }), payload = await response.json(); if (!response.ok) throw new Error(payload.detail || "扫描失败"); renderLifecycle(payload, payload.events || []); setStatus("生命周期扫描完成"); } catch (error) { setStatus(error.message, "error"); } finally { setBusy("scanLifecycleButton", false); } }
async function uploadLifecycleSource(event) { event.preventDefault(); const file = $("lifecycleFileInput").files[0]; if (!file) return; setBusy("lifecycleUploadButton", true, "放入中…"); try { const body = new FormData(); body.set("file", file); const response = await fetch("/api/lifecycle/sources", { method: "POST", body }), payload = await response.json(); if (!response.ok) throw new Error(payload.detail || "文件写入失败"); await scanLifecycle(); $("lifecycleUploadForm").reset(); updateLifecycleFileName(); } catch (error) { setStatus(error.message, "error"); } finally { setBusy("lifecycleUploadButton", false); } }
async function deleteLifecycleSource(path) { try { const response = await fetch(`/api/lifecycle/sources/${encodeURIComponent(path)}`, { method: "DELETE" }), payload = await response.json(); if (!response.ok) throw new Error(payload.detail || "删除失败"); await scanLifecycle(); } catch (error) { setStatus(error.message, "error"); } }

document.addEventListener("DOMContentLoaded", async () => { bindFilePicker(); $("parserSelect").addEventListener("change", updateParserHint); $("canonicalTableSelect").addEventListener("change", renderSelectedCanonicalTable); $("parseForm").addEventListener("submit", submitParse); $("reparseForm").addEventListener("submit", submitReparse); $("copyParseId").addEventListener("click", copyParseId); $("scanLifecycleButton").addEventListener("click", scanLifecycle); $("lifecycleFileInput").addEventListener("change", updateLifecycleFileName); $("lifecycleUploadForm").addEventListener("submit", uploadLifecycleSource); try { await Promise.all([loadParsers(), loadLifecycle()]); setStatus("准备就绪"); } catch (error) { setStatus(error.message, "error"); } });
