(function () {
  "use strict";

  var state = {
    taskId: "",
    fileId: "",
    detail: null,
    view: "optimized",
    changes: [],
    filter: "all",
    selectedId: "",
    previewAbort: null,
    anchors: new Map(),
    toastTimer: 0,
    pendingLocation: ""
  };

  var ui = {
    back: document.getElementById("backToTask"),
    crumb: document.getElementById("breadcrumbName"),
    title: document.getElementById("documentName"),
    version: document.getElementById("versionLabel"),
    actions: document.getElementById("headerActions"),
    loading: document.getElementById("loadingState"),
    empty: document.getElementById("emptyState"),
    detail: document.getElementById("detailView"),
    summary: document.getElementById("detailSummary"),
    statusIcon: document.getElementById("statusIcon"),
    statusTitle: document.getElementById("statusTitle"),
    statusDescription: document.getElementById("statusDescription"),
    metrics: document.getElementById("detailMetrics"),
    panel: document.getElementById("statusPanel"),
    workbench: document.getElementById("workbench"),
    previewTitle: document.getElementById("previewTitle"),
    optimized: document.getElementById("optimizedViewButton"),
    original: document.getElementById("originalViewButton"),
    previewStatus: document.getElementById("previewStatus"),
    previewScroll: document.getElementById("previewScroll"),
    preview: document.getElementById("previewContent"),
    revisionSummary: document.getElementById("revisionSummary"),
    filters: document.getElementById("revisionFilters"),
    revisions: document.getElementById("revisionList"),
    toast: document.getElementById("toast")
  };

  function apiUrl(path) {
    if (window.DocumentParserConfig && typeof window.DocumentParserConfig.url === "function") {
      return window.DocumentParserConfig.url(path);
    }
    return path;
  }

  function isObject(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function arrayOf(value) {
    return Array.isArray(value) ? value : [];
  }

  function stringOf(value) {
    if (typeof value === "string") return value.trim();
    if (typeof value === "number") return String(value);
    return "";
  }

  function first(source, names) {
    for (var index = 0; index < names.length; index += 1) {
      var item = source && source[names[index]];
      if (item !== undefined && item !== null && stringOf(item)) return item;
    }
    return "";
  }

  function text(source, names) {
    return stringOf(first(source, names));
  }

  function limit(value, size) {
    var item = stringOf(value);
    return item.length > size ? item.slice(0, Math.max(0, size - 1)) + "…" : item;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function create(tagName, className, content) {
    var node = document.createElement(tagName);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = content;
    return node;
  }

  function icon(name) {
    var slot = create("span", "icon-slot");
    if (window.MockIcons && typeof window.MockIcons.svg === "function") {
      slot.innerHTML = window.MockIcons.svg(name);
    }
    return slot;
  }

  function mountIcons(scope) {
    if (window.MockIcons && typeof window.MockIcons.mount === "function") {
      window.MockIcons.mount(scope || document);
    }
  }

  function taskUrl(taskId) {
    return "./task-center.html?task_id=" + encodeURIComponent(taskId);
  }

  function api(suffix) {
    return apiUrl("/api/tasks/" + encodeURIComponent(state.taskId) + "/files/" + encodeURIComponent(state.fileId) + suffix);
  }

  function parseRoute() {
    var path = window.location.pathname.split("/").filter(Boolean);
    var index = path.lastIndexOf("tasks");
    if (index >= 0 && path[index + 1] && path[index + 2] === "files" && path[index + 3]) {
      return { taskId: decodeURIComponent(path[index + 1]), fileId: decodeURIComponent(path[index + 3]) };
    }
    var query = new URLSearchParams(window.location.search);
    var taskId = query.get("task_id") || query.get("task");
    var fileId = query.get("task_file_id") || query.get("file_id") || query.get("file");
    return taskId && fileId ? { taskId: taskId, fileId: fileId } : null;
  }

  function actionsOf(source) {
    var actions = new Set();
    var raw = source.allowed_actions || source.actions || [];
    if (Array.isArray(raw)) {
      raw.forEach(function (item) {
        var name = typeof item === "string" ? item : text(item, ["id", "action", "name", "type"]);
        if (name && (!isObject(item) || item.enabled !== false)) actions.add(name.toLowerCase());
      });
    } else if (isObject(raw)) {
      Object.keys(raw).forEach(function (key) {
        if (raw[key] === true || (isObject(raw[key]) && raw[key].enabled !== false)) actions.add(key.toLowerCase());
      });
    }
    if (source.retryable === true) actions.add("retry");
    if (source.reparse_allowed === true) actions.add("reparse");
    return {
      retry: actions.has("retry") || actions.has("safe_retry"),
      reparse: actions.has("reparse") || actions.has("reprocess")
    };
  }

  function changeType(source) {
    var raw = text(source, ["status", "type", "state"]).toLowerCase();
    if (/review|confirm|pending|待确认/.test(raw)) return "review";
    if (/manual|skip|hold|not_applied|未采用|人工/.test(raw)) return "manual";
    return "fixed";
  }

  function changeAnchor(source) {
    var nested = isObject(source.anchor) ? source.anchor : {};
    return text(source, ["anchor_id", "target_anchor", "target_id", "block_id"]) ||
      text(nested, ["anchor_id", "id", "target_id", "block_id"]);
  }

  function changeAnchors(source) {
    var values = arrayOf(source.anchor_ids || source.anchors || source.target_anchors).map(stringOf).filter(Boolean);
    var primary = changeAnchor(source);
    if (primary && values.indexOf(primary) < 0) values.unshift(primary);
    return values;
  }

  function changeTitle(source, index) {
    var titles = {
      "QL-RPR-001": "清理非语义行尾空白",
      "QL-RPR-002": "对齐 Markdown 表格分隔线",
      "QL-RPR-003": "规范化 HTML 表格"
    };
    var ruleId = text(source, ["rule_id", "rule", "type"]).toUpperCase();
    return titles[ruleId] || text(source, ["title", "label", "name"]) || "自动整理文档格式";
  }

  function changeDescription(source) {
    var ruleId = text(source, ["rule_id", "rule", "type"]).toUpperCase();
    var raw = text(source, ["description", "reason", "summary", "message"]);
    if (ruleId === "QL-RPR-001") return "清理非语义行尾空白，保留 Markdown 硬换行和围栏代码内容。";
    if (ruleId === "QL-RPR-002") return "修复 Markdown 表格分隔行，使列数与表头一致。";
    if (ruleId === "QL-RPR-003") return "将安全的 HTML 表格转换为 Markdown 表格，并保留原文证据。";
    if (raw && !(/[A-Za-z]{3,}/.test(raw) && !/[\u4e00-\u9fff]/.test(raw))) return raw;
    return "按质量层白名单规则完成确定性格式整理。";
  }

  function changeOf(item, index) {
    var source = isObject(item) ? item : {};
    var page = text(source, ["page", "page_number"]);
    var pages = arrayOf(source.page_numbers || source.pages).map(stringOf).filter(Boolean);
    if (!pages.length && page) pages = [page];
    var location = text(source, ["location", "position_label", "anchor_label"]) || (pages.length ? pages.map(function (value) { return "第 " + value + " 页"; }).join("、") : "未提供位置");
    var anchors = changeAnchors(source);
    return {
      id: text(source, ["id", "change_id", "repair_id", "issue_id"]) || "change-" + (index + 1),
      title: changeTitle(source, index),
      type: changeType(source),
      statusLabel: text(source, ["status_label", "state_label"]),
      location: location,
      anchor: anchors[0] || "",
      anchors: anchors,
      description: changeDescription(source),
      before: limit(text(source, ["before", "original", "before_text", "original_text"]), 560),
      after: limit(text(source, ["after", "optimized", "after_text", "optimized_text", "current"]), 560),
      evidence: limit(text(source, ["evidence", "evidence_summary", "verification"]), 260)
    };
  }

  function availability(source, view) {
    var map = source.preview_availability || source.preview_urls || source.previews || {};
    var value = map[view];
    if (value === undefined) value = source[view + "_preview_available"];
    if (value === undefined) return null;
    if (isObject(value)) return value.available !== undefined ? Boolean(value.available) : value.enabled !== false;
    return Boolean(value);
  }

  function countOf(value) {
    var number = Number(value);
    return Number.isFinite(number) && number >= 0 ? Math.floor(number) : 0;
  }

  function qualitySummaryOf(source) {
    var raw = isObject(source.quality_summary) ? source.quality_summary : {};
    return {
      state: text(raw, ["state", "status"]).toLowerCase(),
      issueCount: countOf(first(raw, ["issue_count", "issues_count"])),
      appliedRepairCount: countOf(first(raw, ["applied_repair_count", "repair_count", "applied_count"]))
    };
  }

  function issueTitle(category) {
    var titles = {
      heading_level_granularity_suspect: "标题层级已自动恢复",
      table_field_binding: "表格字段需要核对",
      table_structure: "表格结构需要核对",
      table_continuation: "跨页表格已自动识别",
      reference_integrity: "参考文献需要核对"
    };
    return titles[category] || "文档内容需要核对";
  }

  function issueSeverityLabel(severity, category) {
    if (category === "heading_level_granularity_suspect" || category === "table_continuation") {
      return "已自动处理";
    }
    var labels = {
      critical: "需优先处理",
      error: "需优先处理",
      warning: "请核对",
      info: "建议核对"
    };
    return labels[severity] || "请核对";
  }

  function issueOf(item, index) {
    var source = isObject(item) ? item : {};
    var pages = arrayOf(source.pages).map(function (value) { return stringOf(value); }).filter(function (value) { return Boolean(value); });
    var page = text(source, ["page", "page_number"]);
    if (!pages.length && page) pages = [page];
    var category = text(source, ["category", "rule_id", "type"]).toLowerCase();
    var severity = text(source, ["severity", "level"]).toLowerCase();
    return {
      id: text(source, ["id", "issue_id"]) || "issue-" + (index + 1),
      title: issueTitle(category),
      severity: severity,
      severityLabel: issueSeverityLabel(severity, category),
      location: pages.length ? pages.map(function (value) { return "第 " + value + " 页"; }).join("、") : "相关内容",
      message: text(source, ["message", "description", "reason", "summary"]) || "未提供可展示的具体说明。"
    };
  }

  function detailOf(payload) {
    var outer = isObject(payload) ? payload : {};
    var inner = isObject(outer.detail) ? outer.detail : (isObject(outer.file) ? outer.file : outer);
    var source = Object.assign({}, outer, inner);
    var revision = isObject(source.revision) ? source.revision : {};
    var qualitySummary = qualitySummaryOf(source);
    var changes = arrayOf(source.changes);
    if (!changes.length) changes = arrayOf(source.revisions);
    if (!changes.length) changes = arrayOf(revision.changes);
    if (!changes.length) changes = arrayOf(revision.items);
    var issues = arrayOf(source.issues);
    if (!issues.length && isObject(source.quality)) issues = arrayOf(source.quality.issues);
    return {
      name: text(source, ["display_name", "filename", "file_name", "name", "title"]) || "未命名文档",
      state: text(source, ["state", "status", "file_state"]).toLowerCase(),
      stage: text(source, ["stage", "processing_stage"]).toLowerCase(),
      quality: text(source, ["quality_state", "qualityStatus"]).toLowerCase() || qualitySummary.state || text(isObject(source.quality) ? source.quality : {}, ["state", "status"]).toLowerCase(),
      version: text(source, ["current_version_label", "version_label", "revision_label"]) || text(revision, ["label", "version"]),
      parser: text(source, ["parser_summary", "parser_label", "parser_name", "method"]) || text(isObject(source.parser) ? source.parser : {}, ["summary", "label", "name", "id"]),
      summary: text(source, ["summary", "status_summary", "message"]),
      failure: limit(text(source, ["failure_message", "safe_message", "error_message"]), 260),
      pages: text(source, ["page_count", "pages_count", "pages"]),
      changes: changes.map(changeOf),
      issues: issues.map(issueOf),
      qualitySummary: qualitySummary,
      actions: actionsOf(source),
      previews: { optimized: availability(source, "optimized"), original: availability(source, "original") }
    };
  }

  function statusKind(current) {
    var state = (current.state + " " + current.stage).trim();
    if (/failed|error|cancelled|canceled/.test(state)) return "failed";
    if (/queued|pending|preflight|parsing|normalizing|quality_checking|processing|running/.test(state)) return "processing";
    // Quality state describes the delivered document; it is never a blocking
    // task state once the verified package is available.
    return "ready";
  }

  function stageLabel(stage) {
    var labels = {
      queued: "等待处理",
      pending: "等待处理",
      preflight: "任务准备",
      parsing: "文档解析",
      normalizing: "结构整理",
      quality_checking: "质量检查",
      processing: "文档处理",
      running: "文档处理"
    };
    return labels[stage] || "文档处理";
  }

  function issueCount(current) {
    return current.issues.length || current.qualitySummary.issueCount;
  }

  function repairCount(current) {
    return Math.max(current.changes.length, current.qualitySummary.appliedRepairCount);
  }

  function qualityGuidanceKind(current) {
    if (/rejected/.test(current.quality)) return "risk";
    if (/reparse_required/.test(current.quality)) return "reparse";
    if (/manual_review_required/.test(current.quality)) return "review";
    return "";
  }

  function qualityLabel(current) {
    return {
      pass: "质量通过",
      pass_with_warnings: "质量通过 · 有提醒",
      manual_review_required: "建议人工复核",
      reparse_required: "建议重新解析",
      rejected: "质量未通过"
    }[current.quality] || "";
  }

  function hasQualityGuidance(current) {
    return Boolean(qualityGuidanceKind(current));
  }

  function guidanceTitle(current) {
    var kind = qualityGuidanceKind(current);
    if (kind === "risk") return "质量风险提示";
    if (kind === "reparse") return "待确认项与处理建议";
    return "待确认项";
  }

  function guidanceDescription(current) {
    var pendingCount = issueCount(current);
    var completedRepairs = repairCount(current);
    var kind = qualityGuidanceKind(current);
    var result = kind === "risk"
      ? "该版本已生成并可交付，质量风险说明已随交付结果保留。"
      : (kind === "reparse"
        ? "该版本已生成并可交付，建议重新处理的信息已随交付结果保留。"
        : (pendingCount ? "该版本已生成并可交付，发现 " + pendingCount + " 项待确认内容。" : "该版本已生成并可交付，待确认说明已随交付结果保留。"));
    return result + (completedRepairs ? "已完成 " + completedRepairs + " 项自动修改。" : "本次未执行自动修改，原始内容已保留。");
  }

  function statusMeta(current, kind) {
    var all = {
      ready: { icon: "circle-check-big", tone: "", title: "处理完成", description: "当前版本已准备好，可查看文档内容和修改记录。", metric: "done" },
      guidance: { icon: "circle-alert", tone: "review", title: "质量提示", description: "", metric: "review" },
      processing: { icon: "loader-circle", tone: "processing", title: "文档正在处理中", description: "", metric: "processing" },
      failed: { icon: "circle-x", tone: "failed", title: "文档处理未完成", description: "请使用可用操作继续处理，或返回处理中心查看状态。", metric: "review" }
    };
    var result = Object.assign({}, all[kind] || all.ready);
    if (kind === "guidance") result.description = guidanceDescription(current);
    else if (kind === "processing") result.description = "当前阶段：" + stageLabel(current.stage || current.state) + "。完成后即可查看文档内容和修改记录。";
    else if (kind === "failed" && current.failure) result.description = current.failure;
    else if (kind === "ready" && hasQualityGuidance(current)) result.description = guidanceDescription(current);
    else if (kind === "ready" && current.summary) result.description = current.summary;
    return result;
  }

  function addMetric(content, tone) {
    ui.metrics.appendChild(create("span", "metric " + (tone || ""), content));
  }

  function actionButton(label, tone, action) {
    var button = create("button", "action-button " + (tone || ""), label);
    button.type = "button";
    button.addEventListener("click", function () { void submitAction(action, button); });
    return button;
  }

  function appendActionButtons(target, current, className) {
    if (!current.actions.retry && !current.actions.reparse) return;
    var actions = create("div", className || "status-panel__actions");
    if (current.actions.retry) actions.appendChild(actionButton("安全重试", "", "retry"));
    if (current.actions.reparse) actions.appendChild(actionButton("重新处理", current.actions.retry ? "warning" : "primary", "reparse"));
    target.appendChild(actions);
  }

  function renderActions(current, kind) {
    clear(ui.actions);
    if (kind !== "ready") return;
    if (current.actions.retry) ui.actions.appendChild(actionButton("安全重试", "", "retry"));
    if (current.actions.reparse) ui.actions.appendChild(actionButton("重新处理", current.actions.retry ? "warning" : "primary", "reparse"));
  }

  function renderSummary(current, kind) {
    var meta = statusMeta(current, kind);
    var pendingCount = issueCount(current);
    var completedRepairs = repairCount(current);
    ui.statusIcon.className = "status-icon " + meta.tone;
    clear(ui.statusIcon);
    ui.statusIcon.appendChild(icon(meta.icon));
    ui.statusTitle.textContent = meta.title;
    ui.statusDescription.textContent = limit(meta.description, 260);
    clear(ui.metrics);
    if (current.version) addMetric(current.version);
    if (current.parser) addMetric(current.parser);
    if (hasQualityGuidance(current)) {
      if (pendingCount) addMetric(pendingCount + " 项待确认", "review");
      else addMetric("含质量提示", "review");
      addMetric(completedRepairs ? completedRepairs + " 项自动修改" : "未自动修改", "review");
    } else if (qualityLabel(current)) {
      addMetric(qualityLabel(current), current.quality === "pass" ? "done" : "review");
    } else if (current.changes.length) addMetric(current.changes.length + " 项修改记录", meta.metric);
    if (current.pages) addMetric("共 " + current.pages + " 页");
  }

  function appendStatusHeader(target, current, kind, title) {
    var meta = statusMeta(current, kind);
    var header = create("div", "status-panel__header");
    var panelIcon = create("span", "status-icon " + meta.tone);
    panelIcon.appendChild(icon(meta.icon));
    var heading = create("div", "status-panel__heading");
    heading.appendChild(create("h2", "", title || meta.title));
    heading.appendChild(create("p", "", meta.description));
    if (kind === "processing") heading.appendChild(create("span", "status-panel__stage", "当前阶段：" + stageLabel(current.stage || current.state)));
    header.append(panelIcon, heading);
    target.appendChild(header);
  }

  function renderPanel(current, kind) {
    ui.workbench.hidden = true;
    ui.panel.hidden = false;
    ui.panel.className = "status-panel status-panel--" + kind;
    clear(ui.panel);
    appendStatusHeader(ui.panel, current, kind);
    appendActionButtons(ui.panel, current);
  }

  function renderIssue(item) {
    var card = create("li", "status-panel__issue");
    var head = create("div", "status-panel__issue-head");
    head.appendChild(create("strong", "", item.title));
    head.appendChild(create("span", "status-panel__issue-severity " + item.severity, item.severityLabel));
    card.appendChild(head);
    card.appendChild(create("span", "status-panel__issue-location", item.location));
    card.appendChild(create("p", "", item.message));
    return card;
  }

  function renderGuidancePanel(current) {
    var completedRepairs = repairCount(current);
    ui.panel.hidden = false;
    ui.panel.className = "status-panel status-panel--review status-panel--guidance";
    clear(ui.panel);
    appendStatusHeader(ui.panel, current, "guidance", guidanceTitle(current));
    var body = create("div", "status-panel__body");
    var repairSummary = create("div", "status-panel__summary");
    repairSummary.appendChild(create("strong", "", completedRepairs ? "已完成 " + completedRepairs + " 项自动修改。" : "本次未执行自动修改，原始内容已保留。"));
    repairSummary.appendChild(create("span", "", "相关说明已随优化后文档一并交付；重新处理仅用于获得新的解析版本。"));
    body.appendChild(repairSummary);
    if (current.issues.length) {
      var list = create("ol", "status-panel__issue-list");
      current.issues.forEach(function (item) { list.appendChild(renderIssue(item)); });
      body.appendChild(list);
    } else {
      body.appendChild(create("p", "status-panel__empty", "该版本包含质量提示，但暂无可展示的具体位置。请以交付包中的 quality_report.json 为准。"));
    }
    ui.panel.appendChild(body);
    appendActionButtons(ui.panel, current);
  }

  function renderFilters() {
    var labels = { all: "全部", fixed: "已处理", review: "待确认", manual: "需处理" };
    var count = { all: state.changes.length, fixed: 0, review: 0, manual: 0 };
    state.changes.forEach(function (item) { count[item.type] += 1; });
    clear(ui.filters);
    ["all", "fixed", "review", "manual"].filter(function (item) {
      return item === "all" || count[item] > 0;
    }).forEach(function (item) {
      var button = create("button", "filter-button" + (state.filter === item ? " is-active" : ""), labels[item] + " " + count[item]);
      button.type = "button";
      button.setAttribute("aria-pressed", String(state.filter === item));
      button.addEventListener("click", function () {
        state.filter = item;
        renderFilters();
        renderRevisions();
      });
      ui.filters.appendChild(button);
    });
  }

  function typeLabel(item) {
    return item.statusLabel || { fixed: "已自动修复", review: "待确认", manual: "需处理" }[item.type] || "已处理";
  }

  function addDiff(target, current) {
    if (!current.before && !current.after) return;
    var diff = create("span", "revision-diff");
    var before = create("span", "revision-snippet before");
    before.appendChild(create("b", "", "原始内容"));
    before.appendChild(document.createTextNode(current.before || "未提供"));
    var after = create("span", "revision-snippet after");
    after.appendChild(create("b", "", "当前版本"));
    after.appendChild(document.createTextNode(current.after || "未提供"));
    diff.append(before, after);
    target.appendChild(diff);
  }

  function renderRevisions() {
    var visible = state.changes.filter(function (item) { return state.filter === "all" || item.type === state.filter; });
    ui.revisionSummary.textContent = state.changes.length ? "正在显示 " + visible.length + " / " + state.changes.length + " 项记录。" : "当前版本没有修改记录。";
    clear(ui.revisions);
    if (!visible.length) {
      ui.revisions.appendChild(create("p", "revision-empty", state.changes.length ? "当前筛选下没有修改记录。" : "当前版本没有修改记录。"));
      return;
    }
    if (!visible.some(function (item) { return item.id === state.selectedId; })) state.selectedId = visible[0].id;
    visible.forEach(function (current) {
      var card = create("button", "revision-item" + (current.id === state.selectedId ? " is-selected" : ""));
      card.type = "button";
      card.setAttribute("aria-pressed", String(current.id === state.selectedId));
      card.setAttribute("aria-label", "定位：" + current.title);
      var head = create("span", "revision-item__head");
      head.appendChild(create("h3", "", current.title));
      head.appendChild(create("span", "revision-type " + current.type, typeLabel(current.type)));
      card.appendChild(head);
      card.appendChild(create("span", "revision-location", current.location));
      card.appendChild(create("span", "revision-description", "处理原因：" + limit(current.description, 380)));
      addDiff(card, current);
      if (current.evidence) card.appendChild(create("span", "revision-evidence", "处理依据：" + current.evidence));
      card.appendChild(create("span", "revision-locate", current.anchor ? "定位到正文 →" : "暂无正文定位"));
      card.addEventListener("click", function () { locate(current.id); });
      ui.revisions.appendChild(card);
    });
  }

  function domId(raw) {
    var source = String(raw);
    var value = 5381;
    for (var index = 0; index < source.length; index += 1) value = ((value << 5) + value) ^ source.charCodeAt(index);
    return "preview-anchor-" + (value >>> 0).toString(36);
  }

  function registerAnchor(raw, node) {
    if (!raw || state.anchors.has(raw)) return;
    node.id = domId(raw);
    node.dataset.anchorId = raw;
    state.anchors.set(raw, node);
  }

  function rawAnchor(item) {
    return typeof item === "string" ? item.trim() : text(item, ["anchor_id", "id", "target_id", "block_id"]);
  }

  function anchorContext(items) {
    var byLine = new Map(), byBlock = new Map();
    items.forEach(function (item) {
      var id = rawAnchor(item);
      if (!id) return;
      var line = Number(first(item, ["line", "line_number", "start_line"]));
      var block = text(item, ["block_id", "block", "section_id"]);
      if (Number.isFinite(line) && line > 0) {
        if (!byLine.has(line)) byLine.set(line, []);
        byLine.get(line).push(id);
      }
      if (block) {
        if (!byBlock.has(block)) byBlock.set(block, []);
        byBlock.get(block).push(id);
      }
    });
    return { byLine: byLine, byBlock: byBlock };
  }

  function anchorsAt(target, context, line) {
    (context.byLine.get(line) || []).forEach(function (id) {
      var marker = create("span", "preview-anchor");
      marker.setAttribute("aria-hidden", "true");
      registerAnchor(id, marker);
      target.appendChild(marker);
    });
  }

  function tableCells(line) {
    return String(line || "").trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(function (item) { return item.trim(); });
  }

  function isDivider(line) {
    return /^\s*\|?[\s:|-]+\|[\s:|-]+/.test(line || "");
  }

  function renderMarkdown(source, target, context) {
    var lines = String(source || "").replace(/\r\n?/g, "\n").split("\n");
    var index = 0;
    while (index < lines.length) {
      var line = lines[index];
      anchorsAt(target, context, index + 1);
      if (!line.trim()) {
        index += 1;
        continue;
      }
      var heading = line.match(/^(#{1,4})\s+(.+)$/);
      if (heading) {
        target.appendChild(create("h" + heading[1].length, "", heading[2]));
        index += 1;
        continue;
      }
      if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) {
        target.appendChild(create("hr"));
        index += 1;
        continue;
      }
      if (/^\s*>/.test(line)) {
        target.appendChild(create("blockquote", "", line.replace(/^\s*>\s?/, "")));
        index += 1;
        continue;
      }
      if (index + 1 < lines.length && line.indexOf("|") !== -1 && isDivider(lines[index + 1])) {
        var rows = [tableCells(line)];
        index += 2;
        while (index < lines.length && lines[index].indexOf("|") !== -1 && lines[index].trim()) {
          anchorsAt(target, context, index + 1);
          rows.push(tableCells(lines[index]));
          index += 1;
        }
        var wrap = create("div", "markdown-table-wrap");
        var table = create("table", "markdown-table");
        var thead = create("thead"), headerRow = create("tr");
        rows[0].forEach(function (item) { headerRow.appendChild(create("th", "", item)); });
        thead.appendChild(headerRow);
        table.appendChild(thead);
        var tbody = create("tbody");
        rows.slice(1).forEach(function (row) {
          var tr = create("tr");
          row.forEach(function (item) { tr.appendChild(create("td", "", item)); });
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        wrap.appendChild(table);
        target.appendChild(wrap);
        continue;
      }
      var unordered = line.match(/^\s*[-*+]\s+(.+)$/);
      var ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      if (unordered || ordered) {
        var listNode = create(ordered ? "ol" : "ul");
        while (index < lines.length) {
          var item = ordered ? lines[index].match(/^\s*\d+[.)]\s+(.+)$/) : lines[index].match(/^\s*[-*+]\s+(.+)$/);
          if (!item) break;
          listNode.appendChild(create("li", "", item[1]));
          index += 1;
          if (index < lines.length) anchorsAt(listNode, context, index + 1);
        }
        target.appendChild(listNode);
        continue;
      }
      target.appendChild(create("p", "", line));
      index += 1;
    }
  }

  function previewOf(payload) {
    if (typeof payload === "string") return { markdown: payload, blocks: [], anchors: [] };
    var outer = isObject(payload) ? payload : {};
    var nested = isObject(outer.preview) ? outer.preview : (isObject(outer.data) ? outer.data : outer);
    var source = Object.assign({}, outer, nested);
    var blocks = arrayOf(source.blocks);
    if (!blocks.length) blocks = arrayOf(source.sections);
    var anchors = arrayOf(source.anchors);
    if (!anchors.length) anchors = arrayOf(outer.anchors);
    return {
      markdown: text(source, ["markdown", "content", "text", "body", "document_markdown"]),
      blocks: blocks,
      anchors: anchors
    };
  }

  function renderPreview(payload, view) {
    var preview = previewOf(payload);
    var context = anchorContext(preview.anchors);
    state.anchors.clear();
    clear(ui.preview);
    if (preview.blocks.length) {
      preview.blocks.forEach(function (item) {
        var block = isObject(item) ? item : {};
        var id = rawAnchor(block);
        var section = create("section", "preview-block");
        if (id) registerAnchor(id, section);
        (context.byBlock.get(id) || []).forEach(function (anchorId) { registerAnchor(anchorId, section); });
        var content = text(block, ["markdown", "content", "text", "body"]);
        if (content) renderMarkdown(content, section, context);
        else section.appendChild(create("p", "", "此内容块未提供可预览文本。"));
        ui.preview.appendChild(section);
      });
    } else if (preview.markdown) {
      renderMarkdown(preview.markdown, ui.preview, context);
    } else {
      ui.preview.appendChild(create("p", "revision-empty", "当前版本没有可展示的内容。"));
    }
    ui.previewTitle.textContent = view === "optimized" ? "优化后内容" : "原始解析";
    ui.previewStatus.classList.remove("error");
    ui.previewStatus.textContent = view === "optimized" ? "正在查看优化后内容。" : "正在查看原始解析内容。";
    if (state.pendingLocation) {
      var pending = state.pendingLocation;
      state.pendingLocation = "";
      locate(pending);
    }
  }

  function syncViews() {
    var previews = state.detail ? state.detail.previews : { optimized: false, original: false };
    [[ui.optimized, "optimized"], [ui.original, "original"]].forEach(function (item) {
      item[0].classList.toggle("is-active", state.view === item[1]);
      item[0].setAttribute("aria-selected", String(state.view === item[1]));
      item[0].disabled = previews[item[1]] === false;
    });
  }

  async function responseData(response) {
    var raw = await response.text();
    if (!raw) return {};
    try { return JSON.parse(raw); } catch (error) { return raw; }
  }

  function HttpError(status, detail) {
    this.name = "HttpError";
    this.status = status;
    this.detail = detail;
    this.message = detail || "请求未完成";
  }
  HttpError.prototype = Object.create(Error.prototype);

  function safeError(payload) {
    if (typeof payload === "string") return limit(payload, 160);
    if (!isObject(payload)) return "";
    if (isObject(payload.detail)) return limit(text(payload.detail, ["message", "title", "code"]), 160);
    return limit(text(payload, ["detail", "message", "error"]), 160);
  }

  async function loadPreview(view) {
    if (!state.detail || state.detail.previews[view] === false) {
      ui.previewStatus.classList.add("error");
      ui.previewStatus.textContent = "当前版本暂不可查看。";
      return;
    }
    state.view = view;
    syncViews();
    if (state.previewAbort) state.previewAbort.abort();
    var controller = new AbortController();
    state.previewAbort = controller;
    clear(ui.preview);
    ui.previewStatus.classList.remove("error");
    ui.previewStatus.textContent = "正在读取" + (view === "optimized" ? "优化后内容" : "原始解析内容") + "。";
    try {
      var response = await fetch(api("/preview?view=" + encodeURIComponent(view)), {
        headers: { "Accept": "application/json, text/markdown, text/plain" },
        signal: controller.signal
      });
      var payload = await responseData(response);
      if (!response.ok) throw new HttpError(response.status, safeError(payload));
      if (state.previewAbort !== controller) return;
      renderPreview(payload, view);
    } catch (error) {
      if (error.name === "AbortError") return;
      clear(ui.preview);
      ui.previewStatus.classList.add("error");
      ui.previewStatus.textContent = error.status === 403 ? "您暂时无法查看此版本。" : "内容暂时无法读取，请稍后再试。";
      ui.preview.appendChild(create("p", "revision-empty", "暂时无法显示此版本内容。"));
    } finally {
      if (state.previewAbort === controller) state.previewAbort = null;
    }
  }

  function locate(changeId) {
    var current = state.changes.find(function (item) { return item.id === changeId; });
    if (!current) return;
    state.selectedId = current.id;
    renderRevisions();
    var anchors = current.anchors && current.anchors.length ? current.anchors : (current.anchor ? [current.anchor] : []);
    var target = null;
    for (var index = 0; index < anchors.length; index += 1) {
      target = state.anchors.get(anchors[index]);
      if (target) break;
    }
    if (!target) {
      if (anchors.length && !state.anchors.size) {
        state.pendingLocation = current.id;
        toast("正文正在加载，加载完成后将自动定位。");
      } else {
        toast(anchors.length ? "当前版本未找到该记录对应的正文位置。" : "该记录未提供可定位位置。");
      }
      return;
    }
    Array.from(ui.preview.querySelectorAll(".is-focused")).forEach(function (node) { node.classList.remove("is-focused"); });
    var focusTarget = target.nextElementSibling || target.parentElement || target;
    focusTarget.classList.add("is-focused");
    var top = focusTarget.getBoundingClientRect().top - ui.previewScroll.getBoundingClientRect().top + ui.previewScroll.scrollTop - 24;
    ui.previewScroll.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    ui.previewStatus.classList.remove("error");
    ui.previewStatus.textContent = "已定位至：" + current.location;
  }

  function toast(message) {
    ui.toast.textContent = message;
    ui.toast.classList.add("is-visible");
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(function () { ui.toast.classList.remove("is-visible"); }, 2800);
  }

  async function submitAction(action, button) {
    var label = action === "retry" ? "安全重试" : "重新处理";
    if (!window.confirm("确认" + label + "当前文件吗？")) return;
    button.disabled = true;
    button.textContent = "正在提交…";
    try {
      var options = { method: "POST", headers: { "Accept": "application/json" } };
      if (action === "reparse") {
        options.headers["Content-Type"] = "application/json";
        options.body = "{}";
      }
      var response = await fetch(api("/" + action), options);
      var payload = await responseData(response);
      if (!response.ok) throw new HttpError(response.status, safeError(payload));
      toast(label + "已提交。");
      window.setTimeout(function () { window.location.reload(); }, 420);
    } catch (error) {
      button.disabled = false;
      button.textContent = label;
      toast(error.status === 403 ? "当前操作不可用。" : "操作未完成，请稍后再试。");
    }
  }

  function showEmpty(title, description, showBack) {
    ui.loading.hidden = true;
    ui.detail.hidden = true;
    ui.empty.hidden = false;
    clear(ui.empty);
    var emptyIcon = create("span", "page-state__icon");
    emptyIcon.appendChild(icon("circle-x"));
    ui.empty.appendChild(emptyIcon);
    var content = create("div");
    content.appendChild(create("h2", "", title));
    content.appendChild(create("p", "", description));
    if (showBack) {
      var actions = create("div", "page-state__actions");
      var link = create("a", "action-button primary", "返回处理中心");
      link.href = state.taskId ? taskUrl(state.taskId) : "/";
      actions.appendChild(link);
      content.appendChild(actions);
    }
    ui.empty.appendChild(content);
    document.title = title + "｜文档处理中心";
  }

  function showDetail(current) {
    var currentKind = statusKind(current);
    var terminalPanel = currentKind === "processing" || currentKind === "failed";
    ui.loading.hidden = true;
    ui.empty.hidden = true;
    ui.detail.hidden = false;
    ui.back.href = taskUrl(state.taskId);
    ui.crumb.textContent = current.name;
    ui.title.textContent = current.name;
    ui.version.hidden = !current.version;
    ui.version.textContent = current.version;
    document.title = current.name + "｜文档详情";
    state.changes = current.changes;
    state.filter = "all";
    state.selectedId = "";
    renderActions(current, currentKind);
    ui.summary.hidden = terminalPanel;
    if (!terminalPanel) renderSummary(current, currentKind);
    if (terminalPanel) {
      renderPanel(current, currentKind);
      return;
    }
    ui.workbench.hidden = false;
    if (hasQualityGuidance(current)) renderGuidancePanel(current);
    else ui.panel.hidden = true;
    state.view = "optimized";
    renderFilters();
    renderRevisions();
    syncViews();
    void loadPreview("optimized");
  }

  async function loadDetail() {
    try {
      var response = await fetch(api(""), { headers: { "Accept": "application/json" } });
      var payload = await responseData(response);
      if (!response.ok) throw new HttpError(response.status, safeError(payload));
      state.detail = detailOf(payload);
      showDetail(state.detail);
    } catch (error) {
      if (error.status === 404) showEmpty("未找到文档", "该文档可能已被移除，或链接已失效。", true);
      else if (error.status === 403) showEmpty("无法访问文档", "您暂时无权查看该文档。", true);
      else showEmpty("暂时无法读取文档", "请稍后重试，或返回处理中心查看任务状态。", true);
    }
  }

  function init() {
    mountIcons(document);
    var currentRoute = parseRoute();
    if (!currentRoute) {
      showEmpty("未找到文档", "链接中缺少处理任务或文件标识。", true);
      return;
    }
    state.taskId = currentRoute.taskId;
    state.fileId = currentRoute.fileId;
    ui.back.href = taskUrl(state.taskId);
    ui.optimized.addEventListener("click", function () { void loadPreview("optimized"); });
    ui.original.addEventListener("click", function () { void loadPreview("original"); });
    void loadDetail();
  }

  init();
}());
