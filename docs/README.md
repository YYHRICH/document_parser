# 项目文档导航

本目录只把当前仍有效的开发依据放在根层。实验报告统一放在 `reports/`，阶段性分工、周报和被替代的设计统一放在 `archive/`。历史归档用于追溯决策，不作为当前实现依据。

## 开始使用

- [项目总览与运行方式](../README.md)
- [开发环境配置](dev-environment-setup.md)
- [解析器配置和路由说明](配置和路由情况须知.md)
- [Wiki 三文件交付契约](../contracts/wiki_ingest/README.md)

## 当前架构与开发依据

- [DDD 架构说明](architecture-ddd.md)
- [统一文档包要求](unified-document-package-requirements.md)
- [质量层输入要求](quality_input_requirements.md)
- [质量层决策记录](quality-decisions.md)
- [质量层 DDD 开发指南](quality-layer-ddd-dev-guide.md)
- [质量层扩展开发入口](quality-from-scratch-dev-guide.md)
- [复杂表格与大表深化设计](quality-layer-deepening-design.md)

## 系统对接

- [LLM-Wiki 全流程说明](LLM-Wiki全流程说明.md)
- [数据集、多模态和生命周期交付契约](dataset-delivery-multimodal-lifecycle-contract.md)
- [多模态产物对齐说明](杨欣川多模态产物对齐说明.md)

## 报告与历史资料

- [实验、项目和演示报告](reports/README.md)
- [历史资料说明](archive/README.md)
- [当前与历史工程规格](../specs/README.md)

如果文档描述与运行时代码、自动化测试或根目录 README 冲突，以运行时代码、测试、根目录 README 和 `contracts/wiki_ingest/README.md` 为准。
