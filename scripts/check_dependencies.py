"""Check production import direction for the target DDD layers.

规则：
- 只有 ``domain / app / api / trigger / infra`` 五个分层目录被检查；
- 绝对与相对导入都会解析出目标层；
- ``app/bootstrap.py`` 是组合根，允许感知任何层（只做依赖注入装配）；
- 非分层目录（scripts/tools/tests/examples）暂不纳入分层检查。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

LAYERS = ("domain", "app", "api", "trigger", "infra")
ALLOWED = {
    "domain": {"domain"},
    "app": {"app", "domain", "api"},
    "api": {"api", "domain"},
    "trigger": {"trigger", "app", "api", "domain"},
    "infra": {"infra", "domain"},
}
IGNORED = {"tests", "scripts", "tools", "benchmarks", "examples"}
COMPOSITION_ROOTS = {Path("app") / "bootstrap.py", Path("trigger") / "http" / "app.py"}


def layer_for(path: Path, root: Path) -> str | None:
    relative = path.relative_to(root)
    return relative.parts[0] if relative.parts and relative.parts[0] in LAYERS else None


def resolve_relative(current_parts: tuple[str, ...], level: int, module: str | None) -> str:
    """把相对导入解析成完整模块路径（不含文件本身）。"""

    module = (module or "").strip()
    parts = list(current_parts)
    up = level - 1
    if up > 0:
        parts = parts[: max(0, len(parts) - up)]
    if module:
        parts.extend(module.split("."))
    return ".".join(parts)


def imported_layer(node: ast.AST, current_parts: tuple[str, ...]) -> str | None:
    if isinstance(node, ast.Import):
        names = [alias.name.split(".")[0] for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        if node.level:
            resolved = resolve_relative(current_parts, node.level, node.module)
        else:
            resolved = node.module or ""
        if not resolved:
            return None
        names = [resolved.split(".")[0]]
    else:
        return None
    return next((name for name in names if name in LAYERS), None)


def check(root: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if any(part in IGNORED or part == "__pycache__" for part in relative.parts):
            continue
        if relative in COMPOSITION_ROOTS:
            continue
        current = layer_for(path, root)
        if current is None:
            continue
        current_parts = tuple(relative.parts[:-1])
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            violations.append(f"{relative}: syntax error: {error}")
            continue
        for node in ast.walk(tree):
            target = imported_layer(node, current_parts)
            if target and target not in ALLOWED[current]:
                violations.append(
                    f"{relative}:{getattr(node, 'lineno', '?')}: "
                    f"{current} cannot import {target}"
                )
    return violations


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations = check(root)
    if violations:
        print("Dependency violations:")
        print("\n".join(violations))
        return 1
    print("DDD dependency check: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
