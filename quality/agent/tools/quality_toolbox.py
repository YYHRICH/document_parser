"""把 既有确定性质量能力 能力暴露成 Agno Agent 可调用的工具。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quality.agent.models import CandidateValidation, RepairedDocumentCandidate
from quality.agent.revision import (
    DocumentRevision,
    InMemoryRevisionStore,
    materialize_revision_candidate,
)
from quality.agent.tools.document_read import DocumentReadTools
from quality.agent.validator import CandidateValidator, normalize_candidate_declarations
from quality.config import QualityConfig
from quality.pipeline import run_pipeline


@dataclass
class QualityToolbox:
    """一个文档 session 的 既有确定性质量能力 工具集合。

    Agent 只能通过这个对象读取文档、查看差异和验证候选；提交 revision
    由 runtime 在验证通过后执行。Agent 不会直接获得 ParsedDocument 的
    可变引用或任意文件系统权限。
    """

    store: InMemoryRevisionStore
    current_revision: DocumentRevision
    quality_config: QualityConfig = field(default_factory=QualityConfig)
    validator: CandidateValidator = field(default_factory=CandidateValidator)
    last_candidate: RepairedDocumentCandidate | None = None
    last_validation: CandidateValidation | None = None

    @classmethod
    def open(
        cls,
        document,
        *,
        quality_config: QualityConfig | None = None,
    ) -> "QualityToolbox":
        store = InMemoryRevisionStore()
        return cls(
            store=store,
            current_revision=store.open(document),
            quality_config=quality_config or QualityConfig(),
        )

    def read_tools(self) -> DocumentReadTools:
        return DocumentReadTools(self.current_revision)

    def _parse_candidate(
        self,
        candidate: RepairedDocumentCandidate | dict[str, Any],
    ) -> RepairedDocumentCandidate:
        parsed = (
            candidate
            if isinstance(candidate, RepairedDocumentCandidate)
            else RepairedDocumentCandidate.model_validate(candidate)
        )
        return normalize_candidate_declarations(self.current_revision, parsed)

    def get_quality_diagnostics(self) -> dict[str, Any]:
        """返回当前 revision 的紧凑质量问题，供 Agent 定向生成 Patch。"""

        package = run_pipeline(
            self.current_revision.document,
            config=self.quality_config,
            relation_overrides=self.current_revision.relation_overrides,
        )
        report = package.quality_report
        reference_blocks_available = any(
            getattr(block.kind, "value", block.kind) == "reference"
            for block in self.current_revision.document.blocks
        )
        return {
            "revision_id": self.current_revision.revision_id,
            "quality_state": report.state.value,
            "blocking_reasons": list(report.gate_summary.blocking_reasons),
            "capability_blockers": list(report.gate_summary.capability_blockers),
            "issues": [
                self._diagnostic_issue(issue, reference_blocks_available)
                for issue in report.issues
            ],
        }

    @staticmethod
    def _diagnostic_issue(issue, reference_blocks_available: bool) -> dict[str, Any]:
        category = issue.category
        if category in {
            "content_completeness",
            "provenance",
            "reference_structure",
            "evidence_availability",
        }:
            repairability = "parser_limited"
        elif category == "citation_binding" and not reference_blocks_available:
            repairability = "parser_limited"
        elif category in {
            "heading_level_missing",
            "heading_level_granularity_suspect",
            "heading_parent_missing",
            "reading_order_conflict",
            "table_grid",
            "table_header_structure",
            "table_field_binding",
            "cross_page_table",
            "column_drift",
            "citation_binding",
        }:
            repairability = "repairable"
        else:
            repairability = "manual_review"
        return {
            "issue_id": issue.issue_id,
            "category": category,
            "severity": issue.severity.value,
            "message": issue.message,
            "affected_block_ids": list(issue.affected_block_ids),
            "evidence_refs": issue.evidence.get("evidence_refs", []),
            "repairability": repairability,
            "agent_action": (
                "attempt_patch"
                if repairability == "repairable"
                else "preserve_and_report"
            ),
        }

    def repairable_issue_count(self, page_number: int | None = None) -> int:
        diagnostics = self.get_quality_diagnostics()
        if page_number is None:
            return sum(
                issue.get("repairability") == "repairable"
                for issue in diagnostics.get("issues", [])
            )

        document = self.current_revision.document
        page_object_ids = {
            str(block.id)
            for block in document.blocks
            if block.anchor.page_number == page_number
        }
        page_object_ids.update(
            table.table_id
            for table in document.tables
            if table.page_number == page_number
        )
        return sum(
            issue.get("repairability") == "repairable"
            and bool(
                page_object_ids.intersection(issue.get("affected_block_ids", []))
                or page_object_ids.intersection(
                    ref.get("object_id", "")
                    for ref in issue.get("evidence_refs", [])
                )
            )
            for issue in diagnostics.get("issues", [])
        )

    def validate_candidate(self, candidate: RepairedDocumentCandidate | dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_candidate(candidate)
        validation = self.validator.validate(self.current_revision, parsed)
        self.last_candidate = parsed
        self.last_validation = validation
        self.store.record_attempt(self.current_revision, parsed, validation)
        return validation.model_dump(mode="json")

    def validate_candidate_for_page(
        self,
        candidate: RepairedDocumentCandidate | dict[str, Any],
        page_number: int,
    ) -> dict[str, Any]:
        """宿主页面循环使用的带 scope 约束验证，不暴露给 Agent。"""

        parsed = self._parse_candidate(candidate)
        validation = self.validator.validate(
            self.current_revision,
            parsed,
            expected_page=page_number,
        )
        self.last_candidate = parsed
        self.last_validation = validation
        self.store.record_attempt(self.current_revision, parsed, validation)
        return validation.model_dump(mode="json")

    def get_repair_diff(self, candidate: RepairedDocumentCandidate | dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_candidate(candidate)
        before = self.current_revision.document
        after, relation_overrides = materialize_revision_candidate(
            self.current_revision, parsed
        )
        before_blocks = {str(block.id): block for block in before.blocks}
        after_blocks = {str(block.id): block for block in after.blocks}
        changed_blocks = []
        for block_id, block in before_blocks.items():
            updated = after_blocks.get(block_id)
            if updated is not None and (
                block.markdown != updated.markdown
                or block.heading_level != updated.heading_level
                or block.order_index != updated.order_index
            ):
                changed_blocks.append({"block_id": block_id})
        before_relations = {patch.key() for patch in self.current_revision.relation_overrides}
        after_relations = {patch.key() for patch in relation_overrides}
        before_tables = {table.table_id: table for table in before.tables}
        changed_tables = [
            {"table_id": table_id}
            for table_id, table in before_tables.items()
            if next(
                (item for item in after.tables if item.table_id == table_id),
                None,
            ) != table
        ]
        return {
            "base_revision": parsed.base_revision,
            "current_revision": self.current_revision.revision_id,
            "operations": [operation.operation for operation in parsed.operations],
            "changed_blocks": changed_blocks,
            "changed_tables": changed_tables,
            "changed_relation_keys": sorted(before_relations ^ after_relations),
            "changed_asset_paths": [
                asset.path
                for asset in before.assets
                if next((item for item in after.assets if item.path == asset.path), None)
                != asset
            ],
            "markdown_changed": after.markdown != before.markdown,
        }

    def rerun_quality_checks(self, candidate: RepairedDocumentCandidate | dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_candidate(candidate)
        validation = self.validator.validate(self.current_revision, parsed)
        if not validation.accepted:
            return {"accepted": False, "validation": validation.model_dump(mode="json")}
        candidate_document, relation_overrides = materialize_revision_candidate(
            self.current_revision, parsed
        )
        package = run_pipeline(
            candidate_document,
            config=self.quality_config,
            relation_overrides=relation_overrides,
        )
        return {
            "accepted": True,
            "quality_state": package.quality_report.state.value,
            "issue_count": len(package.quality_report.issues),
            "gate_summary": package.quality_report.gate_summary.model_dump(mode="json"),
        }

    def commit_revision(self, candidate: RepairedDocumentCandidate | dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_candidate(candidate)
        validation = self.validator.validate(self.current_revision, parsed)
        if not validation.accepted:
            raise ValueError(f"候选未通过验证，禁止 commit：{validation.errors}")
        self.store.record_attempt(self.current_revision, parsed, validation)
        self.last_candidate = parsed
        self.last_validation = validation
        if validation.no_progress:
            return {
                "status": "unchanged",
                "revision_id": self.current_revision.revision_id,
                "parent_revision_id": self.current_revision.parent_revision_id,
            }
        document, relation_overrides = materialize_revision_candidate(
            self.current_revision, parsed
        )
        self.current_revision = self.store.commit(
            self.current_revision, document, parsed, relation_overrides
        )
        return {
            "status": "committed",
            "revision_id": self.current_revision.revision_id,
            "parent_revision_id": self.current_revision.parent_revision_id,
        }

    def rollback_revision(self, reason: str) -> dict[str, Any]:
        self.last_candidate = None
        self.last_validation = None
        return {
            "status": "rolled_back",
            "revision_id": self.current_revision.revision_id,
            "reason": reason,
        }

    def build_quality_package(self) -> dict[str, Any]:
        package = run_pipeline(
            self.current_revision.document,
            config=self.quality_config,
            relation_overrides=self.current_revision.relation_overrides,
        )
        return package.model_dump(mode="json")

    def as_agno_tools(self) -> list[Any]:
        """返回一组无任意副作用的 Agent 工具函数。"""

        read = self.read_tools()
        # Agent 只拥有读取和验证能力；commit、rollback 和最终打包由
        # runtime 在本地验证后执行，避免模型绕过事务边界。
        return [
            *read.as_agno_tools(),
            self.get_quality_diagnostics,
            self.validate_candidate,
            self.get_repair_diff,
            self.rerun_quality_checks,
        ]
