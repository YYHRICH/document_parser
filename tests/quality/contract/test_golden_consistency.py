"""Golden 单一事实源一致性测试（D-01 落地）。

约束（spec §2.1）：
- annotations/quality/golden.jsonl 是人工质量标注的唯一事实源；
- expected/golden/quality_expectations.jsonl 是面向测试的派生产物；
- 两者对同一 sample_id 的关键期望必须一致；不一致时 CI 必须失败并给出差异，
  禁止静默任选一份。

派生期望必须与人工标注逐项一致，任何漂移都直接失败。
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ANNOTATIONS = (
    REPO_ROOT / "datasets" / "shared-dev-v1" / "annotations" / "quality" / "golden.jsonl"
)
EXPECTED = (
    REPO_ROOT / "datasets" / "shared-dev-v1" / "expected" / "golden" / "quality_expectations.jsonl"
)

def _load_jsonl(path: Path) -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        entries[entry["sample_id"]] = entry
    return entries


def test_golden_files_exist():
    assert ANNOTATIONS.exists(), f"缺少标注文件: {ANNOTATIONS}"
    assert EXPECTED.exists(), f"缺少期望文件: {EXPECTED}"


def test_annotations_are_the_source_of_truth():
    """annotations 是事实源：每个样本至少包含 sample_id 与 expected_state。"""
    annotations = _load_jsonl(ANNOTATIONS)
    assert annotations, "annotations 文件为空"
    for sample_id, entry in annotations.items():
        assert entry.get("expected_state"), f"{sample_id} 缺少 expected_state"
        assert entry.get("must_produce"), f"{sample_id} 缺少 must_produce"


def test_expected_derives_from_annotations():
    """expected 不得包含 annotations 之外的样本；反之亦然（两份不得独立维护）。"""
    annotations = _load_jsonl(ANNOTATIONS)
    expected = _load_jsonl(EXPECTED)
    only_expected = set(expected) - set(annotations)
    only_annotations = set(annotations) - set(expected)
    assert not only_expected, f"expected 含 annotations 没有的样本: {sorted(only_expected)}"
    assert not only_annotations, f"annotations 含 expected 没有的样本: {sorted(only_annotations)}"


def test_expected_matches_annotations():
    """派生期望必须逐项等于人工标注，不能只比较部分字段。"""
    annotations = _load_jsonl(ANNOTATIONS)
    expected = _load_jsonl(EXPECTED)
    assert expected == annotations
