from tools.build_dataset_delivery import candidate_score, source_key


def test_source_key_aligns_parser_specific_markdown_names():
    assert source_key({"relative_output": "分类/同一文档/full.md"}) == "分类/同一文档"
    assert source_key({"relative_output": "分类/同一文档/同一文档.md"}) == "分类/同一文档"


def test_candidate_score_rejects_empty_and_failed_outputs():
    usable = {"model": "anydoc", "quality_state": "pass_with_warnings", "empty_input": False, "issue_severities": {}, "input_chars": 10}
    empty = {"model": "mineru", "quality_state": "rejected", "empty_input": True, "issue_severities": {"critical": 1}, "input_chars": 0}
    assert candidate_score(usable) > candidate_score(empty, asset_count=100)
