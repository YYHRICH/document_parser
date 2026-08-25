"""稳定 ID 单元测试：确定性、区分度、跨调用稳定。"""

from document_parser.domain.quality.ids import binding_id, block_id, issue_id, relation_id, stable_id

DOC_KEY = "sha256-abc"


def test_stable_id_deterministic():
    assert stable_id("abc") == stable_id("abc")
    assert stable_id("abc") != stable_id("abd")


def test_binding_id_deterministic():
    a = binding_id(DOC_KEY, "table-001", "r1c2", "TN3K", ["Train 10%"])
    b = binding_id(DOC_KEY, "table-001", "r1c2", "TN3K", ["Train 10%"])
    assert a == b


def test_binding_id_distinguishes_column_path():
    a = binding_id(DOC_KEY, "t1", "r1c1", "RK", ["采购信息", "供应商", "含税单价"])
    b = binding_id(DOC_KEY, "t1", "r1c1", "RK", ["供应商", "含税单价"])
    c = binding_id(DOC_KEY, "t1", "r1c1", "RK", ["采购信息", "供应商", "交付周期"])
    assert len({a, b, c}) == 3


def test_binding_id_distinguishes_cell_and_row():
    a = binding_id(DOC_KEY, "t1", "r1c1", "RK", ["C"])
    b = binding_id(DOC_KEY, "t1", "r2c1", "RK", ["C"])
    c = binding_id(DOC_KEY, "t1", "r1c1", "RK2", ["C"])
    assert len({a, b, c}) == 3


def test_relation_id_deterministic_and_distinct():
    a = relation_id(DOC_KEY, "parent_child", "h1", "h2")
    b = relation_id(DOC_KEY, "parent_child", "h1", "h2")
    assert a == b
    c = relation_id(DOC_KEY, "reference_of", "h1", "h2")
    d = relation_id(DOC_KEY, "parent_child", "h1", "h3")
    assert len({a, c, d}) == 3


def test_issue_id_orders_affected_ids():
    a = issue_id(DOC_KEY, "QL-CONT-001", ["b2", "b1"])
    b = issue_id(DOC_KEY, "QL-CONT-001", ["b1", "b2"])
    assert a == b  # 排序后等价
    c = issue_id(DOC_KEY, "QL-CONT-001", ["b1", "b3"])
    assert a != c


def test_block_id_uses_source_and_order():
    a = block_id(DOC_KEY, "mineru-content-0001", 0)
    b = block_id(DOC_KEY, "mineru-content-0001", 1)
    assert a != b
    assert block_id(DOC_KEY, "mineru-content-0001", 0) == a
