from tools.materialize_dataset_packages import local_image_references


def test_local_image_references_supports_markdown_and_html():
    markdown = "![a](images/a.png)\n<img src='images/b%20c.jpg'>\n![remote](https://x/y.png)"
    assert local_image_references(markdown) == ["images/a.png", "images/b c.jpg"]


def test_local_image_references_rejects_parent_escape():
    try:
        local_image_references("![bad](../secret.png)")
    except ValueError as error:
        assert "unsafe" in str(error)
    else:
        raise AssertionError("parent traversal should be rejected")
