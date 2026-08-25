"""从 FastAPI OpenAPI 契约生成前端 TypeScript 类型。

单一事实源：api/dto.py + domain 模型 -> FastAPI /openapi.json -> frontend/api-types.ts。
用法（仓库根目录下）：

    .\\.venv\\Scripts\\python.exe scripts\\gen_frontend_types.py

重新生成后建议用编辑器打开 frontend/app.js，按 api-types.ts 的契约检查字段。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from document_parser.trigger.http.app import create_app  # noqa: E402

_TYPE_MAP = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "null": "null",
}

_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _prop_name(name: str) -> str:
    return name if _IDENTIFIER.match(name) else json.dumps(name)


def _ts_type(schema: dict, indent: int = 0) -> str:
    if "$ref" in schema:
        return _ref_name(schema["$ref"])
    if "allOf" in schema:
        return " & ".join(_ts_type(item, indent) for item in schema["allOf"])
    if "anyOf" in schema or "oneOf" in schema:
        key = "anyOf" if "anyOf" in schema else "oneOf"
        return " | ".join(_ts_type(item, indent) for item in schema[key])
    if "enum" in schema:
        values = ", ".join(json.dumps(value) for value in schema["enum"])
        return values or "string"

    schema_type = schema.get("type")
    if schema_type == "array":
        items = schema.get("items", {})
        return f"{_ts_type(items, indent)}[]"
    if schema_type == "object":
        properties = schema.get("properties")
        if properties:
            lines = []
            pad = "  " * (indent + 1)
            for name, prop in properties.items():
                required = name in schema.get("required", [])
                suffix = "" if required else "?"
                lines.append(f"{pad}{_prop_name(name)}{suffix}: {_ts_type(prop, indent + 1)};")
            if lines:
                return "{\n" + "\n".join(lines) + "\n" + "  " * indent + "}"
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict) and additional:
            return f"Record<string, {_ts_type(additional, indent)}>"
        return "Record<string, unknown>"

    base = _TYPE_MAP.get(schema_type, "unknown")
    if schema.get("nullable"):
        return f"{base} | null"
    return base


def generate() -> str:
    schema = create_app().openapi()
    components = schema.get("components", {}).get("schemas", {})
    lines = [
        "// 本文件由 scripts/gen_frontend_types.py 自动生成，请勿手改。",
        "// 单一事实源：api/dto.py + domain 模型 -> OpenAPI -> 本文件。",
        "// 重新生成：.venv\\Scripts\\python.exe scripts\\gen_frontend_types.py",
        "",
    ]
    for name in sorted(components):
        component = components[name]
        description = component.get("description")
        if description:
            lines.extend(f"// {line}" for line in description.splitlines())
        lines.append(f"export type {name} = {_ts_type(component)};")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    output = ROOT / "frontend" / "api-types.ts"
    output.write_text(generate(), encoding="utf-8")
    print(f"generated {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())