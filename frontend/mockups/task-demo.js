(function (global) {
  "use strict";

  var TASKS_KEY = "document-task-demo.tasks.v1";
  var ACTIVE_KEY = "document-task-demo.active-id.v1";
  var memory = { tasks: {}, activeId: null };
  var allowedStatuses = { ready: true, review: true, processing: true, unsupported: true, failed: true };

  function clone(value) {
    return value == null ? value : JSON.parse(JSON.stringify(value));
  }

  function now() {
    return new Date().toISOString();
  }

  function slug(value) {
    var result = String(value || "file").toLowerCase().replace(/\.[^.]+$/, "").replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-").replace(/^-+|-+$/g, "");
    return result || "file";
  }

  function fileExtension(name, fallback) {
    var match = String(name || "").match(/\.([^.]+)$/);
    return String(fallback || (match ? match[1] : "文件")).replace(/^\./, "").toUpperCase();
  }

  function makeTaskId() {
    var stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 12);
    return "task-" + stamp + "-" + Math.random().toString(36).slice(2, 6);
  }

  function safeStorageGet(key) {
    try { return global.sessionStorage ? global.sessionStorage.getItem(key) : null; } catch (error) { return null; }
  }

  function safeStorageSet(key, value) {
    try { if (global.sessionStorage) { global.sessionStorage.setItem(key, value); return true; } } catch (error) { }
    return false;
  }

  function safeStorageRemove(key) {
    try { if (global.sessionStorage) { global.sessionStorage.removeItem(key); } } catch (error) { }
  }

  function readTasks() {
    var raw = safeStorageGet(TASKS_KEY);
    if (!raw) { return clone(memory.tasks); }
    try {
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch (error) {
      return {};
    }
  }

  function writeTasks(tasks) {
    memory.tasks = clone(tasks);
    safeStorageSet(TASKS_KEY, JSON.stringify(tasks));
  }

  function readActiveId() {
    return safeStorageGet(ACTIVE_KEY) || memory.activeId || null;
  }

  function writeActiveId(id) {
    memory.activeId = id || null;
    if (id) { safeStorageSet(ACTIVE_KEY, id); } else { safeStorageRemove(ACTIVE_KEY); }
  }

  function parserFor(extension) {
    if (["PDF", "PNG", "JPG", "JPEG"].indexOf(extension) >= 0) {
      return { id: "mineru", name: "MinerU", label: "自动选择处理方式" };
    }
    return { id: "docling", name: "Docling", label: "自动选择处理方式" };
  }

  function defaultRevision(name) {
    return {
      version: "Revision 01",
      total: 0,
      items: [],
      summary: name + "已完成基础检查。"
    };
  }

  function defaultDetail(name, status) {
    return {
      title: String(name || "未命名文档").replace(/\.[^.]+$/, ""),
      pageCount: status === "processing" ? null : 1,
      revision: defaultRevision(name),
      artifacts: {
        original: status === "ready" || status === "review",
        optimized: status === "ready"
      }
    };
  }

  function qualityFor(status, source) {
    var input = source && typeof source === "object" ? source : {};
    var labels = {
      ready: "可下载",
      review: "待确认",
      processing: "处理中",
      unsupported: "格式不支持",
      failed: "处理失败"
    };
    return {
      status: allowedStatuses[input.status] ? input.status : status,
      label: input.label || labels[status] || "处理中",
      revisionCount: Number.isFinite(Number(input.revisionCount)) ? Number(input.revisionCount) : 0,
      summary: input.summary || "",
      decision: input.decision || null
    };
  }

  function normalizeFile(input, index, usedIds) {
    var source = input && typeof input === "object" ? input : {};
    var name = String(source.name || "未命名文件");
    var extension = fileExtension(name, source.extension || source.type);
    var supported = source.supported !== false;
    var status = supported ? (allowedStatuses[source.status] ? source.status : "processing") : "unsupported";
    if (!supported && status !== "unsupported") { status = "unsupported"; }
    var idBase = String(source.id || slug(name));
    var id = idBase;
    var serial = 2;
    while (usedIds[id]) { id = idBase + "-" + serial; serial += 1; }
    usedIds[id] = true;
    var detail = clone(source.detail || defaultDetail(name, status));
    detail.title = detail.title || name.replace(/\.[^.]+$/, "");
    detail.revision = detail.revision || source.revision || defaultRevision(name);
    detail.revision.items = Array.isArray(detail.revision.items) ? detail.revision.items : [];
    detail.revision.total = Number.isFinite(Number(detail.revision.total)) ? Number(detail.revision.total) : detail.revision.items.length;
    detail.artifacts = detail.artifacts || {};
    if (typeof detail.artifacts.original !== "boolean") { detail.artifacts.original = status === "ready" || status === "review"; }
    if (typeof detail.artifacts.optimized !== "boolean") { detail.artifacts.optimized = status === "ready"; }
    var progress = Number(source.progress);
    if (!Number.isFinite(progress)) {
      progress = status === "ready" || status === "review" ? 100 : (status === "processing" ? 8 : 0);
    }
    return {
      id: id,
      name: name,
      extension: extension,
      sizeBytes: Math.max(0, Number(source.sizeBytes != null ? source.sizeBytes : source.size) || 0),
      supported: supported,
      parser: clone(source.parser || parserFor(extension)),
      status: status,
      progress: Math.max(0, Math.min(100, Math.round(progress))),
      quality: qualityFor(status, source.quality),
      detail: detail
    };
  }

  function normalizeSettings(settings) {
    var source = settings && typeof settings === "object" ? settings : {};
    return {
      parserMode: source.parserMode || "recommended",
      qualityCheck: source.qualityCheck !== false,
      priority: source.priority || "standard"
    };
  }

  function normalizeTask(input) {
    var source = input && typeof input === "object" ? input : {};
    var usedIds = {};
    var files = Array.isArray(source.files) ? source.files.map(function (file, index) { return normalizeFile(file, index, usedIds); }) : [];
    return {
      version: 1,
      id: String(source.id || makeTaskId()),
      createdAt: source.createdAt || now(),
      updatedAt: now(),
      settings: normalizeSettings(source.settings),
      files: files
    };
  }

  function revision(items, version, summary) {
    return { version: version, total: items.length, items: items, summary: summary };
  }

  function exampleTask() {
    return normalizeTask({
      id: "demo-0826",
      createdAt: "2026-08-26T09:00:00+08:00",
      updatedAt: "2026-08-26T09:20:00+08:00",
      settings: { parserMode: "recommended", qualityCheck: true, priority: "standard" },
      files: [
        {
          id: "supply-chain-report", name: "供应链协同研究报告.pdf", extension: "PDF", sizeBytes: 2936013,
          parser: { id: "mineru", name: "MinerU", label: "自动选择处理方式" }, status: "ready", progress: 100,
          quality: { status: "ready", label: "可下载", revisionCount: 4, summary: "4 处内容已整理。" },
          detail: { title: "供应链协同研究报告", pageCount: 28, artifacts: { original: true, optimized: true }, revision: revision([
            { id: "supply-1", title: "合并被拆分的段落", reason: "段落在页面换行处被拆开。", before: "……协同机制由供需双方共同\n建立。", after: "……协同机制由供需双方共同建立。", page: 5, status: "applied" },
            { id: "supply-2", title: "整理标题层级", reason: "标题编号与正文层级不一致。", before: "1.2 供应策略", after: "## 1.2 供应策略", page: 8, status: "applied" },
            { id: "supply-3", title: "还原表格分隔线", reason: "表格列在转换后缺少分隔。", before: "区域  供给量  周期", after: "| 区域 | 供给量 | 周期 |", page: 14, status: "applied" },
            { id: "supply-4", title: "整理图片说明", reason: "图片说明与正文间距异常。", before: "图 3 供应网络", after: "图 3 供应网络", page: 20, status: "applied" }
          ], "Revision 02", "4 处内容已整理。") }
        },
        {
          id: "policy-tables", name: "政策附件与统计表.pdf", extension: "PDF", sizeBytes: 5662310,
          parser: { id: "docling", name: "Docling", label: "自动选择处理方式" }, status: "review", progress: 100,
          quality: { status: "review", label: "待确认", revisionCount: 3, summary: "1 处表格需要确认。" },
          detail: { title: "政策附件与统计表", pageCount: 16, artifacts: { original: true, optimized: false }, revision: revision([
            { id: "policy-1", title: "保留合并单元格的原始含义", reason: "表头的合并范围无法完全确认。", before: "年度  指标  指标", after: "年度 | 指标（待确认）", page: 6, status: "review" },
            { id: "policy-2", title: "统一表格列宽", reason: "列宽在转换后不一致。", before: "统计口径", after: "统计口径", page: 7, status: "applied" },
            { id: "policy-3", title: "补充表格标题", reason: "表格标题与内容分离。", before: "表 2", after: "表 2 主要统计指标", page: 8, status: "applied" }
          ], "Revision 02", "其中 1 处需确认。") }
        },
        {
          id: "scanned-contract", name: "采购合同（扫描件）.pdf", extension: "PDF", sizeBytes: 19293798,
          parser: { id: "mineru", name: "MinerU", label: "自动选择处理方式" }, status: "processing", progress: 46,
          quality: { status: "processing", label: "处理中", revisionCount: 0, summary: "正在识别文档内容。" },
          detail: { title: "采购合同（扫描件）", pageCount: 50, artifacts: { original: false, optimized: false }, revision: revision([], "Revision 01", "文档处理完成后显示修订内容。") }
        },
        {
          id: "meeting-notes", name: "项目复盘会议纪要.docx", extension: "DOCX", sizeBytes: 862208,
          parser: { id: "docling", name: "Docling", label: "自动选择处理方式" }, status: "ready", progress: 100,
          quality: { status: "ready", label: "可下载", revisionCount: 2, summary: "2 处排版已整理。" },
          detail: { title: "项目复盘会议纪要", pageCount: 6, artifacts: { original: true, optimized: true }, revision: revision([
            { id: "notes-1", title: "整理连续空白段", reason: "文档中存在连续空白段。", before: "议题一\n\n\n结论", after: "议题一\n\n结论", page: 2, status: "applied" },
            { id: "notes-2", title: "统一列表缩进", reason: "列表缩进不一致。", before: "  - 后续计划", after: "- 后续计划", page: 4, status: "applied" }
          ], "Revision 02", "2 处排版已整理。") }
        },
        {
          id: "research-appendix", name: "研究补充材料.pdf", extension: "PDF", sizeBytes: 3250586,
          parser: { id: "mineru", name: "MinerU", label: "自动选择处理方式" }, status: "review", progress: 100,
          quality: { status: "review", label: "待确认", revisionCount: 2, summary: "图注归属需要确认。" },
          detail: { title: "研究补充材料", pageCount: 12, artifacts: { original: true, optimized: false }, revision: revision([
            { id: "appendix-1", title: "确认图注归属", reason: "图注靠近两张图片，归属无法确定。", before: "图 4 样本分布", after: "图 4 样本分布（待确认）", page: 9, status: "review" },
            { id: "appendix-2", title: "整理参考文献编号", reason: "编号与正文引用不一致。", before: "[ 3 ]", after: "[3]", page: 11, status: "applied" }
          ], "Revision 02", "其中 1 处需确认。") }
        }
      ]
    });
  }

  function getTask(taskId) {
    var id = taskId || readActiveId();
    var tasks = readTasks();
    if (id && tasks[id]) { return clone(tasks[id]); }
    if (!id || id === "demo-0826") { return exampleTask(); }
    return null;
  }

  function saveTask(task) {
    var normalized = normalizeTask(task);
    var tasks = readTasks();
    tasks[normalized.id] = normalized;
    writeTasks(tasks);
    writeActiveId(normalized.id);
    return clone(normalized);
  }

  function resetTask() {
    memory = { tasks: {}, activeId: null };
    safeStorageRemove(TASKS_KEY);
    safeStorageRemove(ACTIVE_KEY);
  }

  function createTask(queue, settings) {
    return normalizeTask({ files: Array.isArray(queue) ? queue : [], settings: settings || {} });
  }

  function getExampleQueue() {
    return clone(exampleTask().files);
  }

  function getCounts(task) {
    var source = task || getTask();
    var files = source && Array.isArray(source.files) ? source.files : [];
    var counts = { total: files.length, processable: 0, unsupported: 0, ready: 0, review: 0, processing: 0, failed: 0, completed: 0, downloadable: 0, parsed: 0, revisionCount: 0 };
    files.forEach(function (file) {
      var status = file.status || "processing";
      if (file.supported === false || status === "unsupported") { counts.unsupported += 1; return; }
      counts.processable += 1;
      if (Object.prototype.hasOwnProperty.call(counts, status)) { counts[status] += 1; }
      if (status === "ready" || status === "review") { counts.completed += 1; counts.parsed += 1; }
      if (status === "ready") { counts.downloadable += 1; }
      counts.revisionCount += Number(file.quality && file.quality.revisionCount) || 0;
    });
    return counts;
  }

  function getFile(task, fileId) {
    var source = task || getTask();
    var files = source && Array.isArray(source.files) ? source.files : [];
    var found = files.filter(function (file) { return file.id === fileId; })[0] || null;
    return clone(found);
  }

  function getArtifactScope(task, kind) {
    var source = task || getTask();
    var requestedKind = kind === "optimized" ? "optimized" : "original";
    var files = source && Array.isArray(source.files) ? source.files : [];
    var processable = files.filter(function (file) { return file.supported !== false && file.status !== "unsupported"; });
    var included = processable.filter(function (file) {
      if (requestedKind === "original") { return (file.status === "ready" || file.status === "review") && file.detail && file.detail.artifacts && file.detail.artifacts.original !== false; }
      return file.status === "ready" && file.detail && file.detail.artifacts && file.detail.artifacts.optimized !== false;
    });
    return {
      kind: requestedKind,
      label: requestedKind === "original" ? "原始解析压缩包" : "优化后文档压缩包",
      fileIds: included.map(function (file) { return file.id; }),
      fileNames: included.map(function (file) { return file.name; }),
      count: included.length,
      total: processable.length,
      pendingCount: Math.max(0, processable.length - included.length),
      available: included.length > 0
    };
  }

  function confirmFile(task, fileId, action) {
    var source = clone(task || getTask());
    if (!source) { return null; }
    var file = source.files.filter(function (item) { return item.id === fileId; })[0];
    if (!file) { return source; }
    var selected = String(action || "accept");
    if (selected === "accept" || selected === "keep-original") {
      file.status = "ready";
      file.progress = 100;
      file.quality = qualityFor("ready", {
        revisionCount: file.quality && file.quality.revisionCount,
        summary: selected === "accept" ? "已确认采用修订内容。" : "已保留原始内容。",
        decision: selected
      });
      file.detail = file.detail || defaultDetail(file.name, "ready");
      file.detail.artifacts = file.detail.artifacts || {};
      file.detail.artifacts.original = true;
      file.detail.artifacts.optimized = true;
    } else if (selected === "reprocess") {
      file.status = "processing";
      file.progress = 5;
      file.quality = qualityFor("processing", { revisionCount: 0, summary: "正在重新处理文档。" });
      file.detail = file.detail || defaultDetail(file.name, "processing");
      file.detail.artifacts = file.detail.artifacts || {};
      file.detail.artifacts.original = false;
      file.detail.artifacts.optimized = false;
    } else {
      return source;
    }
    return saveTask(source);
  }

  function retryFile(task, fileId) {
    return confirmFile(task, fileId, "reprocess");
  }

  global.DocumentTaskDemo = {
    getTask: getTask,
    saveTask: saveTask,
    resetTask: resetTask,
    createTask: createTask,
    getExampleQueue: getExampleQueue,
    getCounts: getCounts,
    getFile: getFile,
    getArtifactScope: getArtifactScope,
    confirmFile: confirmFile,
    retryFile: retryFile
  };
}(window));
