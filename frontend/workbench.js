(function () {
  "use strict";

  function apiUrl(path) {
    if (window.DocumentParserConfig && typeof window.DocumentParserConfig.url === "function") {
      return window.DocumentParserConfig.url(path);
    }
    return path;
  }

  var UPLOAD_ENDPOINT = apiUrl("/api/tasks");
  var PARSER_LIST_ENDPOINT = apiUrl("/api/parsers");
  var POLL_INTERVAL_MS = 3500;
  var toastTimer = 0;

  function byId(id) {
    return document.getElementById(id);
  }

  function stringOf(value) {
    if (typeof value === "string") return value.trim();
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
    return "";
  }

  function numberOf(value) {
    var number = Number(value);
    return Number.isFinite(number) && number >= 0 ? number : 0;
  }

  function arrayOf(value) {
    return Array.isArray(value) ? value : [];
  }

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function create(tagName, className, content) {
    var node = document.createElement(tagName);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = content;
    return node;
  }

  function icon(name, className, title) {
    var slot = create("span", "icon-slot" + (className ? " " + className : ""));
    if (window.MockIcons && typeof window.MockIcons.svg === "function") {
      slot.innerHTML = window.MockIcons.svg(name, "", title || "");
    }
    return slot;
  }

  function mountIcons(scope) {
    if (window.MockIcons && typeof window.MockIcons.mount === "function") window.MockIcons.mount(scope || document);
  }

  function formatBytes(value) {
    var bytes = numberOf(value);
    if (!bytes) return "大小未知";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
    return (bytes / 1024 / 1024).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1) + " MB";
  }

  function extensionOf(name, sourceType) {
    var value = stringOf(sourceType);
    if (value) {
      var mapped = value.split("/").pop();
      if (mapped && mapped !== value) return mapped.toUpperCase();
      if (/^[a-z0-9+.-]{1,16}$/i.test(value)) return value.toUpperCase();
    }
    var rawName = stringOf(name);
    var index = rawName.lastIndexOf(".");
    return index >= 0 ? rawName.slice(index + 1).toUpperCase() : "文件";
  }

  function fileIconName(type) {
    if (["XLS", "XLSX", "CSV", "ODS"].indexOf(type) >= 0) return "file-spreadsheet";
    if (["PNG", "JPG", "JPEG", "WEBP", "BMP", "TIFF"].indexOf(type) >= 0) return "file-image";
    return "file-text";
  }

  function fileIconClass(type) {
    if (type === "PDF") return "is-pdf";
    if (["XLS", "XLSX", "CSV", "ODS"].indexOf(type) >= 0) return "is-sheet";
    if (["PNG", "JPG", "JPEG", "WEBP", "BMP", "TIFF"].indexOf(type) >= 0) return "is-image";
    return "";
  }

  function showToast(message) {
    var node = byId("toast");
    if (!node) return;
    node.textContent = message;
    node.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      node.classList.remove("is-visible");
    }, 3200);
  }

  async function responseData(response) {
    var raw = await response.text();
    if (!raw) return {};
    try { return JSON.parse(raw); } catch (error) { return {}; }
  }

  function HttpError(status) {
    this.name = "HttpError";
    this.status = status || 0;
    this.message = "Request failed";
  }
  HttpError.prototype = Object.create(Error.prototype);

  function errorMessage(error, context) {
    if (error && error.status === 404) return context === "task" ? "未找到该处理任务。" : "未找到所需资源。";
    if (error && error.status === 403) return "您暂时无权进行此操作。";
    if (error && error.status === 409) return "当前状态已发生变化，请刷新后重试。";
    if (error && error.status === 413) return "文件大小超过允许范围，请调整后重试。";
    if (error && (error.status === 415 || error.status === 422)) return "部分文件暂不支持或未通过校验，请调整后重试。";
    return "操作未完成，请稍后重试。";
  }

  function taskCenterUrl(taskId, rejectedCount) {
    var rejected = Math.floor(numberOf(rejectedCount));
    return "./task-center.html?task_id=" + encodeURIComponent(taskId) + (rejected > 0 ? "&rejected=" + encodeURIComponent(rejected) : "");
  }

  function documentDetailUrl(taskId, fileId) {
    return "./document-detail.html?task_id=" + encodeURIComponent(taskId) + "&file_id=" + encodeURIComponent(fileId);
  }

  function newSubmissionKey() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
    return "task-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }


  function initializeUpload() {
    var form = byId("taskUploadForm");
    var input = byId("fileInput");
    var dropzone = byId("fileDropzone");
    var chooseButton = byId("chooseFiles");
    var clearButton = byId("clearFiles");
    var queueNode = byId("fileQueue");
    var queueEmpty = byId("fileQueueEmpty");
    var queueSummary = byId("fileQueueSummary");
    var badge = byId("selectedFileBadge");
    var count = byId("selectedFileCount");
    var size = byId("selectedFileSize");
    var start = byId("startTask");
    var startLabel = byId("startTaskLabel");
    var status = byId("uploadStatus");
    var parserSelect = byId("parserSelect");
    var parserHint = byId("parserHint");
    var allowCloud = byId("allowCloud");
    var cloudHint = byId("cloudHint");
    if (!form || !input || !queueNode || !start) return;

    var queue = [];
    var submitting = false;
    var submissionKey = "";
    var parserState = {
      parsers: [],
      loaded: false,
      loadFailed: false,
      cloudParsersEnabled: false
    };

    function fileKey(file) {
      return [stringOf(file.name), numberOf(file.size), numberOf(file.lastModified)].join("|");
    }

    function queueTotal() {
      return queue.reduce(function (sum, item) { return sum + numberOf(item.file.size); }, 0);
    }


    function fileExtension(file) {
      var name = stringOf(file && file.name).toLowerCase();
      var index = name.lastIndexOf(".");
      return index > 0 && index < name.length - 1 ? name.slice(index) : "";
    }

    function selectedExtensions() {
      var extensions = [];
      queue.forEach(function (item) {
        var extension = fileExtension(item && item.file);
        if (extension && extensions.indexOf(extension) < 0) extensions.push(extension);
      });
      return extensions;
    }

    function parserName(parser) {
      return stringOf(parser && parser.display_name) || stringOf(parser && parser.parser_id) || "未命名模型";
    }

    function parserFormats(parser) {
      if (!Array.isArray(parser && parser.formats)) return null;
      return parser.formats
        .filter(function (format) { return typeof format === "string"; })
        .map(function (format) { return format.trim().toLowerCase(); })
        .filter(Boolean)
        .map(function (format) { return format.charAt(0) === "." ? format : "." + format; });
    }

    function parserById(parserId) {
      return parserState.parsers.find(function (parser) {
        return stringOf(parser && parser.parser_id) === parserId;
      }) || null;
    }

    function updateCloudOption() {
      if (!allowCloud) return;
      var serverAllowsCloud = parserState.loaded && !parserState.loadFailed && parserState.cloudParsersEnabled;
      allowCloud.disabled = submitting || !serverAllowsCloud;
      if (!serverAllowsCloud) allowCloud.checked = false;
      if (!cloudHint) return;
      if (!parserState.loaded) {
        cloudHint.textContent = "正在读取服务端云端解析权限。";
      } else if (parserState.loadFailed) {
        cloudHint.textContent = "暂时无法读取云端解析权限，云端解析已关闭。";
      } else if (serverAllowsCloud) {
        cloudHint.textContent = allowCloud.checked
          ? "已开启云端解析；提交时会把此偏好交给服务端路由。"
          : "服务端已允许云端解析；勾选后才会使用需要联网的模型。";
      } else {
        cloudHint.textContent = "当前服务未启用云端解析；请设置 DOCUMENT_PARSER_ALLOW_CLOUD=true 后重启服务。";
      }
    }

    function parserSelectionState(parser, extensions) {
      if (!parser || typeof parser !== "object") {
        return { selectable: false, label: "未列出", reason: "该解析模型未在当前服务中提供。" };
      }
      if (parser.available === false) {
        return { selectable: false, label: "暂不可用", reason: "当前服务暂不能使用此解析模型。" };
      }
      if (parser.requires_network === true && !parserState.cloudParsersEnabled) {
        return { selectable: false, label: "云端未启用", reason: "当前服务未启用云端解析。" };
      }
      var formats = parserFormats(parser);
      var unsupported = (extensions || []).filter(function (extension) {
        return formats !== null && formats.indexOf(extension) < 0;
      });
      if (unsupported.length) {
        var listed = unsupported.map(function (extension) { return extension.toUpperCase(); }).join("、");
        return {
          selectable: false,
          label: "不支持 " + listed,
          reason: parserName(parser) + " 不支持本批文件中的 " + listed + " 格式。"
        };
      }
      return { selectable: true, label: "", reason: "" };
    }

    function updateParserHint() {
      if (!parserHint) return;
      var parserId = stringOf(parserSelect && parserSelect.value);
      var extensions = selectedExtensions();
      if (!parserState.loaded) {
        parserHint.textContent = "正在加载可用解析模型；也可以直接使用自动选择。";
        return;
      }
      if (parserState.loadFailed) {
        parserHint.textContent = "暂时无法读取可用解析模型，仍可使用自动选择。";
        return;
      }
      if (!parserId) {
        parserHint.textContent = extensions.length
          ? "系统会根据每份文件的类型选择合适的解析模型。"
          : "选择文件后可指定一个解析模型，或交给系统自动选择。";
        return;
      }
      var parser = parserById(parserId);
      var selection = parserSelectionState(parser, extensions);
      if (!selection.selectable) {
        parserHint.textContent = selection.reason;
        return;
      }
      if (parser.requires_network === true && allowCloud && !allowCloud.checked) {
        parserHint.textContent = "当前模型需要云端解析，请先勾选“启用云端解析”。";
        return;
      }
      parserHint.textContent = queue.length
        ? "本批 " + queue.length + " 份文件将统一使用 " + parserName(parser) + " 解析；如需更换模型，可在处理完成后逐份重新处理。"
        : "已选择 " + parserName(parser) + "。选择文件后会检查该模型是否适用于本批文件。";
    }

    function renderParserOptions(notifyOnReset) {
      if (!parserSelect) return;
      var previousValue = stringOf(parserSelect.value);
      var extensions = selectedExtensions();
      clear(parserSelect);
      var automatic = create("option", "", "自动选择（推荐）");
      automatic.value = "";
      parserSelect.appendChild(automatic);
      if (!parserState.loaded) {
        var loading = create("option", "", "正在加载解析模型…");
        loading.disabled = true;
        parserSelect.appendChild(loading);
      } else if (parserState.loadFailed) {
        var failed = create("option", "", "暂时无法加载模型列表");
        failed.disabled = true;
        parserSelect.appendChild(failed);
      } else if (!parserState.parsers.length) {
        var empty = create("option", "", "当前没有可用模型");
        empty.disabled = true;
        parserSelect.appendChild(empty);
      } else {
        parserState.parsers.forEach(function (parser) {
          var selection = parserSelectionState(parser, extensions);
          var option = create(
            "option",
            "",
            parserName(parser) + (selection.selectable ? "" : "（" + selection.label + "）")
          );
          option.value = stringOf(parser && parser.parser_id);
          option.disabled = !selection.selectable;
          if (selection.reason) option.title = selection.reason;
          parserSelect.appendChild(option);
        });
      }
      var previousSelection = parserSelectionState(parserById(previousValue), extensions);
      var keepPrevious = Boolean(previousValue && previousSelection.selectable);
      parserSelect.value = keepPrevious ? previousValue : "";
      parserSelect.disabled = submitting;
      updateCloudOption();
      updateParserHint();
      if (notifyOnReset && previousValue && !keepPrevious) {
        var resetMessage = "已改为自动选择：" + previousSelection.reason;
        if (parserHint) parserHint.textContent = resetMessage;
        showToast(resetMessage);
      }
    }

    async function loadParserChoices() {
      try {
        var response = await fetch(PARSER_LIST_ENDPOINT, { headers: { "Accept": "application/json" } });
        var payload = await responseData(response);
        if (!response.ok) throw new HttpError(response.status);
        parserState.parsers = arrayOf(payload && payload.parsers);
        var selectionPolicy = payload && typeof payload.selection_policy === "object"
          ? payload.selection_policy
          : {};
        parserState.cloudParsersEnabled = selectionPolicy.cloud_parsers_enabled === true;
      parserState.loaded = true;
      parserState.loadFailed = false;
      } catch (error) {
        parserState.parsers = [];
        parserState.loaded = true;
        parserState.loadFailed = true;
      }
      updateCloudOption();
      renderParserOptions(false);
    }

    function renderQueue() {
      var total = queueTotal();
      clear(queueNode);
      if (queue.length) {
        queue.forEach(function (item) {
          var file = item.file;
          var type = extensionOf(file.name, "");
          var row = create("article", "upload-file-row");
          var fileIcon = create("span", "file-icon " + fileIconClass(type));
          fileIcon.appendChild(icon(fileIconName(type)));
          row.appendChild(fileIcon);
          var main = create("div", "file-main");
          main.appendChild(create("strong", "file-name", file.name || "未命名文件"));
          main.appendChild(create("span", "file-meta", type + " · " + formatBytes(file.size)));
          row.appendChild(main);
          row.appendChild(create("span", "file-pending", "待提交"));
          var remove = create("button", "button button-quiet button-small button-danger", "");
          remove.type = "button";
          remove.setAttribute("aria-label", "移除“" + (file.name || "该文件") + "”");
          remove.appendChild(icon("trash-2"));
          remove.appendChild(create("span", "", "移除"));
          remove.addEventListener("click", function () {
            if (submitting) return;
            queue = queue.filter(function (candidate) { return candidate.id !== item.id; });
            renderQueue();
            showToast("已移除“" + (file.name || "该文件") + "”。");
          });
          row.appendChild(remove);
          queueNode.appendChild(row);
        });
      }
      queueEmpty.hidden = queue.length > 0;
      clearButton.hidden = !queue.length || submitting;
      badge.textContent = queue.length + " 份文件";
      count.textContent = queue.length + " 份";
      size.textContent = queue.length ? formatBytes(total) : "—";
      queueSummary.textContent = queue.length ? "已选择 " + queue.length + " 份文件，共 " + formatBytes(total) + "。" : "尚未选择文件";
      start.disabled = !queue.length || submitting;
      startLabel.textContent = submitting ? "正在提交…" : (queue.length ? "开始处理" : "请选择文件");
      if (!submitting) status.textContent = queue.length ? "确认后开始提交。" : "选择文件后即可开始处理。";
      renderParserOptions(true);
    }

    function appendFiles(incoming) {
      var added = 0;
      var skipped = 0;
      Array.prototype.forEach.call(incoming || [], function (file) {
        if (!file || typeof file.name !== "string") return;
        var identity = fileKey(file);
        var duplicate = queue.some(function (item) { return item.identity === identity; });
        if (duplicate) {
          skipped += 1;
          return;
        }
        queue.push({ id: "file-" + Date.now().toString(36) + "-" + (queue.length + 1), identity: identity, file: file });
        added += 1;
      });
      renderQueue();
      if (added && skipped) showToast("已加入 " + added + " 份文件，已跳过重复选择的文件。");
      else if (added) showToast("已加入 " + added + " 份文件。");
      else if (skipped) showToast("重复选择的文件未重复加入。");
    }
    async function submitTask() {
      if (submitting || !queue.length) return;
      var selectedParserId = stringOf(parserSelect && parserSelect.value);
      if (selectedParserId) {
        var selection = parserSelectionState(parserById(selectedParserId), selectedExtensions());
        if (!selection.selectable) {
          status.textContent = selection.reason;
          showToast(selection.reason);
          return;
        }
        var selectedParser = parserById(selectedParserId);
        if (selectedParser && selectedParser.requires_network === true && (!allowCloud || !allowCloud.checked)) {
          var cloudReason = "当前模型需要云端解析，请先勾选“启用云端解析”。";
          status.textContent = cloudReason;
          showToast(cloudReason);
          return;
        }
      }
      submitting = true;
      submissionKey = submissionKey || newSubmissionKey();
      renderQueue();
      status.textContent = "正在提交文件。";
      var formData = new FormData();
      queue.forEach(function (item) { formData.append("files", item.file, item.file.name); });
      if (selectedParserId) formData.set("parser_id", selectedParserId);
      formData.set("options_json", JSON.stringify({ allow_cloud: Boolean(allowCloud && allowCloud.checked) }));
      try {
        var response = await fetch(UPLOAD_ENDPOINT, {
          method: "POST",
          headers: { "Accept": "application/json", "Idempotency-Key": submissionKey },
          body: formData
        });
        var payload = await responseData(response);
        if (!response.ok) throw new HttpError(response.status);
        var task = payload && typeof payload.task === "object" ? payload.task : payload;
        var taskId = stringOf(payload && payload.task_id) || stringOf(task && task.task_id);
        if (!taskId) throw new HttpError(0);

        window.location.assign(taskCenterUrl(taskId, arrayOf(payload && payload.rejected_files).length));
      } catch (error) {
        submitting = false;
        renderQueue();
        status.textContent = errorMessage(error, "upload");
        showToast(errorMessage(error, "upload"));
      }
    }

    chooseButton.addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () {
      appendFiles(input.files);
      input.value = "";
    });
    clearButton.addEventListener("click", function () {
      if (submitting || !queue.length) return;
      queue = [];
      renderQueue();
      showToast("已清空文件列表。");
    });
    ["dragenter", "dragover"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        if (!submitting) dropzone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.remove("is-dragover");
      });
    });
    dropzone.addEventListener("drop", function (event) {
      if (!submitting && event.dataTransfer) appendFiles(event.dataTransfer.files);
    });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      void submitTask();
    });
    if (parserSelect) parserSelect.addEventListener("change", function () {
      var parser = parserById(stringOf(parserSelect.value));
      if (parser && parser.requires_network === true && parserState.cloudParsersEnabled && allowCloud) {
        allowCloud.checked = true;
      }
      updateCloudOption();
      updateParserHint();
    });
    if (allowCloud) allowCloud.addEventListener("change", function () {
      updateCloudOption();
      updateParserHint();
    });
    updateCloudOption();
    renderQueue();
    void loadParserChoices();
  }

  function taskIdFromLocation() {
    var parts = window.location.pathname.split("/").filter(Boolean);
    var index = parts.lastIndexOf("tasks");
    if (index >= 0 && parts[index + 1]) {
      try { return decodeURIComponent(parts[index + 1]); } catch (error) { return ""; }
    }
    var query = new URLSearchParams(window.location.search);
    return query.get("task_id") || query.get("task") || "";
  }

  function rejectedCountFromLocation() {
    var query = new URLSearchParams(window.location.search);
    var rejected = Math.floor(numberOf(query.get("rejected")));
    if (rejected <= 0) return 0;
    query.delete("rejected");
    if (window.history && typeof window.history.replaceState === "function") {
      var remaining = query.toString();
      var cleanUrl = window.location.pathname + (remaining ? "?" + remaining : "") + window.location.hash;
      window.history.replaceState({}, document.title, cleanUrl);
    }
    return rejected;
  }
  function taskOf(payload) {
    if (payload && typeof payload.task === "object" && payload.task) return payload.task;
    return payload && typeof payload === "object" ? payload : null;
  }

  function visualState(raw) {
    var value = stringOf(raw).toLowerCase().replace(/-/g, "_");
    if (value === "needs_review" || value === "review") return "review";
    if (value === "available" || value === "ready") return "available";
    if (value === "processing" || value === "queued" || value === "running" || value === "pending" || value === "waiting") return "processing";
    return "failed";
  }

  function fileBuckets(task) {
    var buckets = { processing: [], review: [], available: [], failed: [] };
    arrayOf(task && task.files).forEach(function (file) {
      buckets[visualState(file && file.state)].push(file);
    });
    return buckets;
  }

  function statusLabel(kind) {
    return { processing: "处理中", review: "待确认", available: "可下载", failed: "处理失败" }[kind] || "处理失败";
  }

  function statusIcon(kind) {
    return { processing: "loader-circle", review: "circle-alert", available: "circle-check-big", failed: "circle-x" }[kind] || "circle-x";
  }

  function stageDescription(stage) {
    var value = stringOf(stage).toLowerCase().replace(/-/g, "_");
    var labels = {
      queued: "已进入处理队列。",
      preflight: "正在准备文件。",
      parsing: "正在解析文档内容。",
      normalizing: "正在整理文档内容。",
      quality_checking: "正在检查文档质量。",
      succeeded: "正在整理处理结果。"
    };
    return labels[value] || "正在处理文档。";
  }

  function qualityGuidanceDescription(file) {
    var quality = stringOf(file.quality_state).toLowerCase();
    if (quality === "manual_review_required") return "文档已生成，可下载；含待确认项，说明已随交付结果保留。";
    if (quality === "reparse_required") return "文档已生成，可下载；建议重新处理的信息已随交付结果保留。";
    if (quality === "rejected") return "文档已生成，可下载；含质量风险提示，请按交付报告处理。";
    return "";
  }

  function qualityMeta(file) {
    var value = stringOf(file && file.quality_state).toLowerCase();
    var labels = {
      pass: { label: "质量通过", className: "pass" },
      pass_with_warnings: { label: "质量通过 · 有提醒", className: "review" },
      manual_review_required: { label: "建议人工复核", className: "review" },
      reparse_required: { label: "建议重新解析", className: "review" },
      rejected: { label: "质量未通过", className: "risk" }
    };
    return labels[value] || null;
  }

  function fileDescription(file, kind) {
    if (kind === "processing") return stageDescription(file.stage);
    if (kind === "review") return "处理信息不完整，请打开详情查看。";
    if (kind === "available") return qualityGuidanceDescription(file) || "当前版本已准备好，可查看文档内容和处理记录。";
    return file.retryable ? "处理未完成，可在详情中重新处理。" : "处理未完成，请查看详情了解下一步操作。";
  }

  function aggregateOf(task) {
    var files = arrayOf(task && task.files);
    var buckets = fileBuckets(task);
    return {
      total: files.length,
      processing: buckets.processing.length,
      review: buckets.review.length,
      available: buckets.available.length,
      failed: buckets.failed.length,
      downloadable: buckets.available.length
    };
  }

  function archiveCount(task, kind, fallback) {
    var downloads = task && typeof task.downloads === "object" ? task.downloads : {};
    var archive = downloads && downloads[kind];
    if (!archive || typeof archive !== "object") return fallback;
    if (archive.available === false) return 0;
    return archive.count !== undefined ? numberOf(archive.count) : fallback;
  }
  function initializeTaskCenter() {
    var taskId = taskIdFromLocation();
    var rejectedCount = rejectedCountFromLocation();
    var loading = byId("taskLoading");
    var error = byId("taskError");
    var errorTitle = byId("taskErrorTitle");
    var errorCopy = byId("taskErrorCopy");
    var rejectedNotice = byId("rejectedNotice");
    var rejectedNoticeText = byId("rejectedNoticeText");
    var retry = byId("retryLoadTask");
    var content = byId("taskContent");
    var intro = byId("taskIntro");
    var summaryCopy = byId("summaryCopy");
    var summary = byId("statusSummary");
    var showAll = byId("showAllFiles");
    var fileCount = byId("taskFileCount");
    var filesCopy = byId("taskFilesCopy");
    var fileList = byId("taskFileList");
    var filesEmpty = byId("taskFilesEmpty");
    var refresh = byId("refreshTask");
    var downloadWrap = byId("downloadWrap");
    var downloadButton = byId("downloadButton");
    var downloadMenu = byId("downloadMenu");
    var originalScope = byId("originalDownloadScope");
    var optimizedScope = byId("optimizedDownloadScope");
    if (!loading || !error || !content || !summary || !fileList) return;

    var state = { task: null, filter: "all", loading: false, timer: 0 };

    if (rejectedNotice && rejectedNoticeText && rejectedCount > 0) {
      rejectedNoticeText.textContent = "其中 " + rejectedCount + " 份文件未能受理，请返回上传页调整后重新提交。";
      rejectedNotice.hidden = false;
    }

    function setDownloadOpen(open) {
      if (!downloadMenu) return;
      downloadMenu.hidden = !open;
      if (downloadWrap) downloadWrap.classList.toggle("is-open", open);
      if (downloadButton) downloadButton.setAttribute("aria-expanded", String(open));
    }

    function renderSummary(counts) {
      clear(summary);
      [
        ["processing", counts.processing],
        ["available", counts.available],
        ["failed", counts.failed]
      ].forEach(function (item) {
        var kind = item[0];
        var count = item[1];
        var button = create("button", "status-total is-" + kind);
        button.type = "button";
        button.disabled = count <= 0;
        button.dataset.filter = kind;
        button.setAttribute("aria-disabled", String(count <= 0));
        button.setAttribute("aria-pressed", String(state.filter === kind));
        button.appendChild(create("strong", "", String(count)));
        var label = create("span", "status-label");
        label.appendChild(icon(statusIcon(kind)));
        label.appendChild(document.createTextNode(statusLabel(kind)));
        button.appendChild(label);
        button.addEventListener("click", function () {
          if (count <= 0) return;
          state.filter = kind;
          renderSummary(counts);
          renderFiles();
        });
        summary.appendChild(button);
      });
      showAll.hidden = state.filter === "all";
      summaryCopy.textContent = state.filter === "all" ? "点击状态可查看对应文件。" : "正在显示“" + statusLabel(state.filter) + "”的文件。";
    }

    function renderFiles() {
      var files = arrayOf(state.task && state.task.files);
      var buckets = fileBuckets(state.task);
      var visible = state.filter === "all" ? files : (buckets[state.filter] || []);
      clear(fileList);
      fileCount.textContent = state.filter === "all" ? "共 " + files.length + " 份文件" : "显示 " + visible.length + " / " + files.length + " 份";
      filesCopy.textContent = files.length ? "每份文件都可以单独查看和继续处理。" : "当前没有可显示的文件。";
      filesEmpty.hidden = visible.length > 0;
      if (!visible.length) return;
      visible.forEach(function (file) {
        var item = file && typeof file === "object" ? file : {};
        var name = stringOf(item.display_name) || "未命名文件";
        var type = extensionOf(name, item.source_file_type);
        var kind = visualState(item.state);
        var id = stringOf(item.task_file_id);
        var row = create("article", "task-file-row");
        var fileIcon = create("span", "file-icon " + fileIconClass(type));
        fileIcon.appendChild(icon(fileIconName(type)));
        row.appendChild(fileIcon);
        var nameColumn = create("div", "file-column");
        nameColumn.appendChild(create("strong", "file-name", name));
        nameColumn.appendChild(create("span", "file-meta", type + " · " + formatBytes(item.source_size_bytes)));
        var quality = qualityMeta(item);
        if (quality) nameColumn.appendChild(create("span", "quality-badge " + quality.className, quality.label));
        row.appendChild(nameColumn);
        var statusColumn = create("div", "file-column status-column");
        statusColumn.appendChild(create("span", "row-label", "处理状态"));
        var pill = create("span", "status-pill " + kind);
        pill.appendChild(icon(statusIcon(kind)));
        pill.appendChild(document.createTextNode(statusLabel(kind)));
        statusColumn.appendChild(pill);
        row.appendChild(statusColumn);
        var detailColumn = create("div", "file-column file-detail-column");
        detailColumn.appendChild(create("span", "row-label", "当前情况"));
        detailColumn.appendChild(create("p", "file-detail", fileDescription(item, kind)));
        row.appendChild(detailColumn);
        if (id) {
          var actionLabel = kind === "available" ? "查看文档" : "查看详情";
          var action = create("a", "button button-quiet button-small row-action");
          action.href = documentDetailUrl(taskId, id);
          action.appendChild(icon(kind === "review" ? "list-checks" : "eye"));
          action.appendChild(create("span", "", actionLabel));
          row.appendChild(action);
        } else {
          row.appendChild(create("span", "row-action", ""));
        }
        fileList.appendChild(row);
      });
    }

    function setPackage(button, scope, kind, count) {
      if (!button || !scope) return;
      button.disabled = count <= 0;
      var label = kind === "original" ? "原始解析压缩包" : "优化后文档压缩包";
      scope.textContent = count > 0 ? "包含当前可下载的 " + count + " 份文件。" : "当前没有可下载的文件。";
      button.setAttribute("aria-label", label + "，" + scope.textContent);
    }

    function renderDownloads(task, counts) {
      var original = downloadMenu && downloadMenu.querySelector('[data-download="original"]');
      var optimized = downloadMenu && downloadMenu.querySelector('[data-download="optimized"]');
      setPackage(original, originalScope, "original", archiveCount(task, "original", counts.downloadable));
      setPackage(optimized, optimizedScope, "optimized", archiveCount(task, "optimized", counts.downloadable));
    }

    function renderTask(task) {
      state.task = task;
      var counts = aggregateOf(task);
      if (state.filter !== "all" && counts[state.filter] <= 0) state.filter = "all";
      loading.hidden = true;
      error.hidden = true;
      content.hidden = false;
      intro.textContent = counts.total ? "查看每份文件的处理情况，并继续下一步操作。" : "当前处理任务中没有文件。";
      renderSummary(counts);
      renderFiles();
      renderDownloads(task, counts);
      scheduleRefresh(counts.processing > 0);
    }

    function scheduleRefresh(shouldPoll) {
      window.clearTimeout(state.timer);
      state.timer = 0;
      if (!shouldPoll) return;
      state.timer = window.setTimeout(function () { void loadTask(false); }, POLL_INTERVAL_MS);
    }

    function showTaskError(errorValue) {
      window.clearTimeout(state.timer);
      loading.hidden = true;
      content.hidden = true;
      error.hidden = false;
      if (!taskId) {
        errorTitle.textContent = "未选择处理任务";
        errorCopy.textContent = "请先上传文件，再进入处理中心。";
      } else if (errorValue && errorValue.status === 404) {
        errorTitle.textContent = "未找到处理任务";
        errorCopy.textContent = "该任务可能已被移除，或链接已失效。";
      } else if (errorValue && errorValue.status === 403) {
        errorTitle.textContent = "无法访问处理任务";
        errorCopy.textContent = "您暂时无权查看该处理任务。";
      } else {
        errorTitle.textContent = "暂时无法读取处理状态";
        errorCopy.textContent = "请稍后重试。";
      }
    }
    async function loadTask(showFeedback) {
      if (state.loading) return;
      if (!taskId) {
        showTaskError(null);
        return;
      }
      state.loading = true;
      if (!state.task) {
        loading.hidden = false;
        error.hidden = true;
      }
      if (refresh) refresh.disabled = true;
      try {
        var response = await fetch(apiUrl("/api/tasks/" + encodeURIComponent(taskId)), { headers: { "Accept": "application/json" } });
        var payload = await responseData(response);
        if (!response.ok) throw new HttpError(response.status);
        var task = taskOf(payload);
        if (!task || !Array.isArray(task.files)) throw new HttpError(0);
        renderTask(task);
        if (showFeedback) showToast("已更新文件状态。");
      } catch (errorValue) {
        showTaskError(errorValue);
        if (showFeedback) showToast(errorMessage(errorValue, "task"));
      } finally {
        state.loading = false;
        if (refresh) refresh.disabled = false;
      }
    }

    if (downloadButton) {
      downloadButton.addEventListener("click", function (event) {
        event.stopPropagation();
        setDownloadOpen(downloadMenu && downloadMenu.hidden);
      });
    }
    if (downloadMenu) {
      downloadMenu.addEventListener("click", function (event) {
        var button = event.target.closest("[data-download]");
        if (!button) return;
        var kind = button.dataset.download;
        if (button.disabled) {
          showToast("当前没有可下载的文件。");
          return;
        }
        setDownloadOpen(false);
        window.location.assign(apiUrl("/api/tasks/" + encodeURIComponent(taskId) + "/downloads/" + encodeURIComponent(kind)));
      });
    }
    document.addEventListener("click", function (event) {
      if (downloadWrap && !downloadWrap.contains(event.target)) setDownloadOpen(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        setDownloadOpen(false);
        if (downloadButton) downloadButton.focus();
      }
    });
    if (showAll) showAll.addEventListener("click", function () {
      state.filter = "all";
      renderSummary(aggregateOf(state.task));
      renderFiles();
    });
    if (refresh) refresh.addEventListener("click", function () { void loadTask(true); });
    if (retry) retry.addEventListener("click", function () { void loadTask(true); });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible" && state.task && aggregateOf(state.task).processing > 0) void loadTask(false);
    });
    window.addEventListener("pagehide", function () { window.clearTimeout(state.timer); });
    void loadTask(false);
  }

  function initialize() {
    mountIcons(document);
    var page = document.body && document.body.dataset.page;
    if (page === "upload") initializeUpload();
    if (page === "task-center") initializeTaskCenter();
  }

  initialize();
}());
