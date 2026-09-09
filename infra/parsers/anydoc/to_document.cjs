// AnyDoc Node API bridge: one invocation writes both Markdown and a safe
// structured sidecar. Binary asset bodies are intentionally omitted here;
// they remain parser-native artifacts and do not belong in the table payload.
const fs = require('fs');
const path = require('path');

async function main() {
  const [modulePath, inputPath, jsonPath, markdownPath, extension] = process.argv.slice(2);
  if (!modulePath || !inputPath || !jsonPath || !markdownPath) {
    throw new Error('usage: node to_document.cjs <module> <input> <json> <markdown> [extension]');
  }
  const anydoc = require(modulePath);
  const bytes = new Uint8Array(fs.readFileSync(inputPath));
  const format = extension ? anydoc.formatFromExtension(extension) : null;
  const markdown = await anydoc.toMarkdownBytes(bytes, format || undefined);
  fs.writeFileSync(markdownPath, markdown, 'utf8');

  let document = null;
  let structuredError = null;
  let assets = [];
  try {
    const parsed = await anydoc.toDocument(bytes, format || undefined);
    document = {
      blocks: parsed.blocks || [],
      notes: parsed.notes || [],
    };
    assets = (parsed.assets || []).map((asset) => ({
      id: asset.id,
      mediaType: asset.mediaType,
      originPart: asset.originPart,
      sizeBytes: asset.data ? asset.data.length : 0,
    }));
  } catch (error) {
    structuredError = {
      code: error && error.code ? String(error.code) : 'unknown',
      message: error && error.message ? String(error.message) : String(error),
    };
  }
  const sidecar = {
    schema_name: 'AnyDocDocumentSidecar',
    document,
    assets,
    structured_error: structuredError,
  };
  fs.writeFileSync(jsonPath, JSON.stringify(sidecar), 'utf8');
}

main().catch((error) => {
  process.stderr.write((error && error.stack) ? error.stack : String(error));
  process.exitCode = 1;
});
