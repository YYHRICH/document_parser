"""不读取第三方模型的轻量文件预检。

当前实现只提取 MarkItDown 调用需要的低成本信号，不打开远程 URL。
"""

from pathlib import Path

from ..model.contracts import DocumentSignals, ParseRequest


class SimpleSourceInspector:
    """根据文件名和本地内容大小生成第一版路由信号。"""

    def inspect(self, request: ParseRequest) -> DocumentSignals:
        """检查扩展名、大小和可直接识别的文本特征。"""

        # 路由器和能力目录都使用“带点的小写扩展名”；无扩展名统一视作 .bin。
        extension = Path(request.filename).suffix.lower() or ".bin"
        content = request.content
        # 这里只标记无需解析即可确认的文本格式；PDF 文本层必须由深度预检判断。
        has_text_layer = None
        if extension in {".md", ".txt", ".html", ".csv"}:
            has_text_layer = True
        return DocumentSignals(
            extension=extension,
            size_bytes=len(content),
            has_text_layer=has_text_layer,
        )
