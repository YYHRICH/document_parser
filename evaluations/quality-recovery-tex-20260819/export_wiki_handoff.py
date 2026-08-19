"""把已有真实质量 Agent 四件套导出为 WikiHandoff。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
sys.path = [entry for entry in sys.path if entry not in {"", str(EVAL_ROOT)}]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT.parent)]

from quality import build_wiki_handoff, write_wiki_handoff  # noqa: E402
from document_parser import QualityPackage  # noqa: E402


def load_package(report_path: Path) -> QualityPackage:
    package_dir = report_path.parent
    canonical = json.loads(
        (package_dir / "canonical_document.json").read_text(encoding="utf-8")
    )
    return QualityPackage.model_validate(
        {
            "document_id": canonical["document_id"],
            "optimized_markdown": (package_dir / "optimized.md").read_text(
                encoding="utf-8"
            ),
            "canonical_document": canonical,
            "quality_report": json.loads(report_path.read_text(encoding="utf-8")),
            "package_manifest": json.loads(
                (package_dir / "package_manifest.json").read_text(encoding="utf-8")
            ),
        }
    )


def main() -> None:
    for report_path in sorted(
        (EVAL_ROOT / "quality").glob("*/*/quality_report.json")
    ):
        handoff = build_wiki_handoff(load_package(report_path))
        output_dir = report_path.parent / "wiki_handoff"
        write_wiki_handoff(handoff, output_dir, replace_existing=True)
        print(
            f"{report_path.parent.parent.name}/{report_path.parent.name}: "
            f"chunks={len(handoff.chunks)}, citations={len(handoff.citations)}, "
            f"state={handoff.quality_state.value}"
        )


if __name__ == "__main__":
    main()
