const state = {
  parsers: [],
  lastResponse: null,
};

const $ = (id) => document.getElementById(id);

function setStatus(text) {
  $("appStatus").textContent = text;
}

function parseJsonInput(value) {
  const raw = value.trim();
  if (!raw) {
    return {};
  }
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Options must be a JSON object.");
  }
  return parsed;
}

function populateParserSelects() {
  const selects = [$("parserSelect"), $("reparseParser")];
  for (const select of selects) {
    select.innerHTML = "";
    const auto = document.createElement("option");
    auto.value = "";
    auto.textContent = "Auto route";
    select.appendChild(auto);
    for (const parser of state.parsers) {
      const option = document.createElement("option");
      option.value = parser.parser_id;
      option.textContent = `${parser.display_name} (${parser.parser_id})`;
      select.appendChild(option);
    }
  }
}

function buildOptions(baseOptions) {
  return {
    ...baseOptions,
    route_profile: $("routeProfile").value,
    allow_cloud: $("allowCloud").checked,
    libreoffice_available: $("libreofficeAvailable").checked,
  };
}

function renderArtifactLinks(parseId, artifacts) {
  const target = $("artifactsOutput");
  target.innerHTML = "";
  if (!artifacts.length) {
    target.textContent = "No artifacts.";
    return;
  }
  for (const artifact of artifacts) {
    const row = document.createElement("div");
    const link = document.createElement("a");
    const safePath = artifact.path.split("/").map(encodeURIComponent).join("/");
    link.href = `/api/parses/${parseId}/artifacts/${safePath}`;
    link.textContent = artifact.path;
    link.target = "_blank";
    row.appendChild(link);
    const meta = document.createElement("span");
    meta.textContent = ` ${artifact.artifact_type} ${artifact.file_type} ${artifact.size_bytes}b`;
    row.appendChild(meta);
    target.appendChild(row);
  }
}

async function loadQualityPackage(parseId) {
  const meta = $("qualityMeta");
  const output = $("qualityOutput");
  if (!parseId || parseId === "n/a") {
    meta.textContent = "No quality package loaded.";
    output.textContent = "";
    return;
  }
  meta.textContent = "Loading quality package...";
  try {
    const response = await fetch(`/api/parses/${encodeURIComponent(parseId)}/quality-package`);
    if (response.status === 404) {
      meta.textContent = "No quality package attached yet.";
      output.textContent = "";
      return;
    }
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || `Quality package load failed: ${response.status}`);
    }
    meta.textContent = `Quality package: ${payload.package_path}`;
    output.textContent = JSON.stringify(payload.quality_package, null, 2);
  } catch (error) {
    meta.textContent = error.message;
    output.textContent = "";
  }
}

function renderResponse(payload) {
  state.lastResponse = payload;
  const documentData = payload.document;
  const provenance = documentData.provenance || {};
  const routing = documentData.routing_decision || {};
  const parseId = payload.parse_id || "n/a";
  $("reparseId").value = parseId;
  $("resultMeta").textContent = [
    `parse_id: ${parseId}`,
    `parser: ${provenance.parser_id || documentData.provenance?.parser_id || "n/a"}`,
    `route: ${routing.reason || provenance.routing_mode || "n/a"}`,
    `artifacts: ${payload.native_artifact_count ?? 0}`,
  ].join(" | ");
  $("routingOutput").textContent = JSON.stringify(routing, null, 2);
  $("documentOutput").textContent = JSON.stringify(
    {
      filename: documentData.filename,
      file_type: documentData.file_type,
      provenance,
      confidence: documentData.confidence,
      capabilities: documentData.capabilities,
      warnings: documentData.warnings,
      tables: (documentData.tables || []).length,
      blocks: (documentData.blocks || []).length,
      assets: (documentData.assets || []).length,
    },
    null,
    2
  );
  $("markdownOutput").textContent = documentData.markdown || "";
  renderArtifactLinks(parseId, documentData.native_artifacts || []);
  loadQualityPackage(parseId);
}

async function loadParsers() {
  const response = await fetch("/api/parsers");
  if (!response.ok) {
    throw new Error(`Failed to load parsers: ${response.status}`);
  }
  const data = await response.json();
  state.parsers = data.parsers || [];
  populateParserSelects();
}

async function submitParse(event) {
  event.preventDefault();
  const fileInput = $("fileInput");
  const file = fileInput.files[0];
  if (!file) {
    setStatus("Choose a file first.");
    return;
  }

  let options;
  try {
    options = buildOptions(parseJsonInput($("extraOptions").value));
  } catch (error) {
    setStatus(error.message);
    return;
  }

  const formData = new FormData();
  formData.set("file", file);
  if ($("parserSelect").value) {
    formData.set("parser_id", $("parserSelect").value);
  }
  formData.set("options_json", JSON.stringify(options));

  setStatus("Parsing...");
  const response = await fetch("/api/parses", {
    method: "POST",
    body: formData,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || `Parse failed: ${response.status}`);
  }
  renderResponse(payload);
  setStatus("Parse complete.");
}

async function submitReparse(event) {
  event.preventDefault();
  const parseId = $("reparseId").value.trim();
  if (!parseId) {
    setStatus("Enter parse ID first.");
    return;
  }

  let options;
  try {
    options = parseJsonInput($("reparseOptions").value);
  } catch (error) {
    setStatus(error.message);
    return;
  }

  setStatus("Reparsing...");
  const response = await fetch(`/api/parses/${encodeURIComponent(parseId)}/reparse`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      parser_id: $("reparseParser").value || null,
      options,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || `Reparse failed: ${response.status}`);
  }
  renderResponse(payload);
  setStatus("Reparse complete.");
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadParsers();
    setStatus("Ready");
  } catch (error) {
    setStatus(error.message);
  }

  $("parseForm").addEventListener("submit", (event) => {
    submitParse(event).catch((error) => setStatus(error.message));
  });
  $("reparseForm").addEventListener("submit", (event) => {
    submitReparse(event).catch((error) => setStatus(error.message));
  });
});
