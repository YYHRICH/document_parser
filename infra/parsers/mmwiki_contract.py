"""杨欣川 mmwiki-0.1 输入片段的边界契约。

这里只描述外部交换格式；进入领域层时仍转换为 ParsedDocument，避免领域模型
反向依赖上游的私有 JSON 结构。
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MmwikiTableContent(BaseModel):
    """mmwiki ``items.content.table`` 的已确认结构。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    # 行优先的二维字符串矩阵；不编码 rowspan/colspan。
    rows: list[list[str]] = Field(default_factory=list)
    # 原始 HTML 是合并单元格等结构信息的唯一事实来源。
    html: str


class MmwikiBBox(BaseModel):
    """mmwiki 左上角原点、0-1000 归一化坐标。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    values: tuple[
        float | int, float | int, float | int, float | int
    ]
    coordinate_system: str = "normalized_1000"
    origin: str = "top_left"
    # 杨侧当前真实包未携带页面物理尺寸；有值时才能换算成 pt。
    page_width: float | int | None = Field(default=None, gt=0)
    page_height: float | int | None = Field(default=None, gt=0)
    page_unit: str = "pt"

    @model_validator(mode="after")
    def validate_coordinate_contract(self) -> "MmwikiBBox":
        if self.coordinate_system != "normalized_1000" or self.origin != "top_left":
            raise ValueError("mmwiki bbox 必须使用 normalized_1000/top_left。")
        if any(value < 0 or value > 1000 for value in self.values):
            raise ValueError("mmwiki bbox 坐标必须位于 0 到 1000。")
        left, top, right, bottom = self.values
        if left > right or top > bottom:
            raise ValueError("mmwiki bbox 必须满足 left<=right 且 top<=bottom。")
        return self

    def to_page_coordinates(self) -> tuple[float, float, float, float]:
        """按页面物理宽高把 normalized_1000 换算为 page_unit 坐标。"""

        if self.page_width is None or self.page_height is None:
            raise ValueError("缺少 page_width/page_height，无法换算为页面物理坐标。")
        left, top, right, bottom = self.values
        return (
            float(left) / 1000 * float(self.page_width),
            float(top) / 1000 * float(self.page_height),
            float(right) / 1000 * float(self.page_width),
            float(bottom) / 1000 * float(self.page_height),
        )
