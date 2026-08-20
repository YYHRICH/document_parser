"""Golden 单一事实源一致性测试（D-01 落地）。

约束（spec §2.1）：
- annotations/quality/golden.jsonl 是人工质量标注的唯一事实源；
- expected/golden/quality_expectations.jsonl 是面向测试的派生产物；
- 两者对同一 sample_id 的关键期望必须一致；不一致时 CI 必须失败并给出差异，
  禁止静默任选一份。

当前已知冲突（D-01）：sdp-004 的 expected_column_paths 两份标注不一致，
待数据负责人确认；测试将其显式标记为 xfail，不静默通过。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ANNOTATIONS = (
    REPO_ROOT / "datasets" / "shared-dev-v1" / "annotations" / "quality" / "golden.jsonl"
)
EXPECTED = (
    REPO_ROOT / "datasets" / "shared-dev-v1" / "expected" / "golden" / "quality_expectations.jsonl"
)

# 已登记冲突的 sample（annotations 为事实源，expected 未同步）：
# - sdp-004 (D-01): expected_column_paths 采购版 vs 训练集版
# - sdp-005 (D-16): must_produce 不一致（annotations 细分 3 项 vs expected 1 项）
# - sdp-006 (D-16): must_produce 不一致（annotations 多 heading_level）
# - sdp-007 (D-16): must_produce/forbidden 不一致
# 结论：4 个 golden 样本的两份文件从未同步过，需数据负责人统一后消解。
KNOWN_CONFLICTS = {"sdp-004", "sdp-005", "sdp-006", "sdp-007"}

# 必须一致的关键字段
COMPARE_FIELDS = ("expected_state", "must_produce", "forbidden")


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


def test_expected_matches_annotations_for_shared_fields():
    """两份文件对同一样本的关键字段必须一致（已知冲突除外）。"""
    annotations = _load_jsonl(ANNOTATIONS)
    expected = _load_jsonl(EXPECTED)
    mismatches: list[str] = []
    for sample_id in sorted(set(annotations) & set(expected)):
        if sample_id in KNOWN_CONFLICTS:
            continue
        for field in COMPARE_FIELDS:
            ann_value = annotations[sample_id].get(field)
            exp_value = expected[sample_id].get(field)
            # 排序后比较列表，忽略顺序差异
            if sorted(ann_value or []) != sorted(exp_value or []) if isinstance(ann_value, list) else ann_value != exp_value:
                mismatches.append(
                    f"{sample_id}.{field}: annotations={ann_value!r} != expected={exp_value!r}"
                )
    assert not mismatches, "golden 两份文件漂移:\n" + "\n".join(mismatches)


def test_known_conflicts_still_differ():
    """已登记冲突必须确实存在差异；解决后从 KNOWN_CONFLICTS 移除并更新决策记录。"""
    annotations = _load_jsonl(ANNOTATIONS)
    expected = _load_jsonl(EXPECTED)
    resolved: list[str] = []
    for sample_id in KNOWN_CONFLICTS:
        ann = annotations.get(sample_id, {})
        exp = expected.get(sample_id, {})
        if all(ann.get(f) == exp.get(f) for f in COMPARE_FIELDS):
            resolved.append(sample_id)
    assert not resolved, (
        f"以下登记冲突已解决（两份一致），请从 KNOWN_CONFLICTS 移除: {resolved}"
    )
    pytest.xfail(
        "D-01/D-16: 4 个 golden 样本标注漂移待数据负责人确认"
        "（sdp-004 column_path / sdp-005/006/007 must_produce / sdp-007 forbidden）"
    )
