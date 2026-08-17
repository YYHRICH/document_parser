# shared-dev-v1

公开合成共享开发数据集，供路由、Adapter、ParsedDocument 和质量层共同联调。

- Development：12 个唯一文件，覆盖企业知识库、事故复盘、工单扫描件、采购表格、跨页/合并单元格表格、技术报告引用、报销票据、使用量仪表盘、长知识库页面、设备控制面板照片和 DOCX 变更申请单。
- Smoke：sdp-001、sdp-004、sdp-007、sdp-008
- Golden：sdp-004、sdp-005、sdp-006、sdp-007
- 所有样例均为项目生成，无客户数据和个人信息，按 CC0-1.0 synthetic fixture 使用

`manifest.jsonl` 是文件身份、类别、子集和 SHA-256 的唯一事实源。最终输入文件在 `files/`；PDF/图片样例的可复现源在 `sources/tex/`，DOCX 回归样例由确定性的 Open XML 构建。

质量层只读取 ParsedDocument 2.2；Golden 文件描述应产生、延续或安全拒绝的关系，不绑定解析器私有结构。对于扫描件、票据、截图和设备照片，OCR 标注同时记录应提取的业务字段与应安全降级的场景。