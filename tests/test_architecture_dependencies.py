"""Static dependency-direction guard for the separated parser platform.

The test reads source imports instead of importing the application.  This keeps
the guard useful even when an optional parser runtime is unavailable.
"""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOTS = (
    "common",
    "core",
    "normalizers",
    "parsers",
    "routing",
    "orchestration",
    "quality",
    "composition",
    "backend",
    "tools",
)

FORBIDDEN_IMPORTS = {
    "core": {"backend", "composition", "normalizers", "orchestration", "parsers", "quality", "routing", "tools"},
    "normalizers": {"backend", "composition", "orchestration", "parsers", "quality", "routing", "tools"},
    "parsers": {"backend", "composition", "orchestration", "quality", "routing", "tools"},
    "routing": {"backend", "composition", "orchestration", "parsers", "quality", "tools"},
    "orchestration": {"backend", "composition", "parsers", "quality", "routing", "tools"},
    "quality": {"backend", "composition", "normalizers", "orchestration", "parsers", "routing", "tools"},
    "composition": {"backend"},
}


def _package_parts(source_path: Path) -> tuple[str, ...]:
    relative = source_path.relative_to(PROJECT_ROOT)
    return ("document_parser", *relative.parts[:-1])


def _imported_root(source_path: Path, node: ast.ImportFrom) -> str:
    if node.level == 0:
        module = node.module or ""
        parts = module.split(".") if module else []
        if parts and parts[0] == "document_parser":
            parts = parts[1:]
        return parts[0] if parts else ""

    package = list(_package_parts(source_path))
    package = package[: len(package) - node.level + 1]
    if node.module:
        package.extend(node.module.split("."))
    return package[1] if len(package) > 1 else ""


def _import_roots(source_path: Path) -> set[str]:
    roots: set[str] = set()
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts and parts[0] == "document_parser":
                    parts = parts[1:]
                if parts:
                    roots.add(parts[0])
        elif isinstance(node, ast.ImportFrom):
            root = _imported_root(source_path, node)
            if root:
                roots.add(root)
    return roots


def test_package_dependency_direction_is_explicit() -> None:
    violations: list[str] = []
    for package in PACKAGE_ROOTS:
        package_path = PROJECT_ROOT / package
        for source_path in sorted(package_path.rglob("*.py")):
            for imported in sorted(_import_roots(source_path) & FORBIDDEN_IMPORTS.get(package, set())):
                violations.append(f"{package}/{source_path.relative_to(package_path)} -> {imported}")
    assert not violations, "Forbidden package dependencies:\n" + "\n".join(violations)


def test_composition_and_parser_adapter_ownership_is_explicit() -> None:
    assert not (PROJECT_ROOT / "core" / "gateway.py").exists()
    assert not (PROJECT_ROOT / "tools" / "mineru_cloud.py").exists()
    assert (PROJECT_ROOT / "composition" / "gateway.py").is_file()
    assert (PROJECT_ROOT / "parsers" / "mineru" / "cloud_client.py").is_file()
