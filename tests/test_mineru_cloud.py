"""MinerU Cloud 适配器边界值回归。"""

from tools.mineru_cloud import _content_list_to_blocks


def test_empty_table_image_path_is_normalized_to_none():
    blocks, tables = _content_list_to_blocks(
        [
            {
                "type": "table",
                "img_path": "",
                "table_caption": ["测试表"],
                "table_body": "<table><tr><td>A</td><td>B</td></tr></table>",
                "bbox": [1, 2, 3, 4],
                "page_idx": 0,
            }
        ]
    )

    assert len(blocks) == len(tables) == 1
    assert tables[0].image_path is None
    assert tables[0].page_number == 1


def test_non_empty_table_image_path_is_preserved():
    _, tables = _content_list_to_blocks(
        [
            {
                "type": "table",
                "img_path": "images/table-1.jpg",
                "table_body": "<table><tr><td>A</td></tr></table>",
                "page_idx": 0,
            }
        ]
    )

    assert tables[0].image_path == "images/table-1.jpg"


def test_formula_native_metadata_is_preserved():
    blocks, tables = _content_list_to_blocks(
        [
            {
                "type": "equation_interline",
                "text": "x <= 1",
                "math_content": "x \\leq 1",
                "math_type": "latex",
                "image_source": "images/formula.png",
                "bbox": [10, 20, 100, 40],
                "page_idx": 0,
            }
        ]
    )

    assert not tables
    assert blocks[0].kind.value == "formula"
    assert blocks[0].native_type == "equation_interline"
    assert blocks[0].metadata["math_content"] == "x \\leq 1"
    assert blocks[0].metadata["math_type"] == "latex"
