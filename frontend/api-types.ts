// 本文件由 scripts/gen_frontend_types.py 自动生成，请勿手改。
// 单一事实源：api/dto.py + domain 模型 -> OpenAPI -> 本文件。
// 重新生成：.venv\Scripts\python.exe scripts\gen_frontend_types.py

// 一次实际执行且可回放的白名单修复。
export type AppliedRepair = {
  repair_id: string;
  rule_id: string;
  description: string;
  affected_block_ids?: string[];
  replayable?: boolean;
  evidence?: Record<string, unknown>;
};

// 解析结果附属资源类型；当前统一输出重点覆盖图片。
export type AssetKind = "image", "attachment", "table_snapshot";

// 下游统一使用的文档块类型。
export type BlockKind = "heading", "paragraph", "list", "table", "image", "formula", "header", "footer", "page_number", "aside", "footnote", "reference";

export type Body_create_parse_api_parses_post = {
  file: string;
  parser_id?: string | null;
  options_json?: string | null;
  native_output_dir?: string | null;
};

export type Body_lifecycle_put_source_api_lifecycle_sources_post = {
  file: string;
};

// 质量层稳定文档节点。
export type CanonicalBlock = {
  block_id: string;
  kind: string;
  order_index: number;
  content: string;
  source_locator: CanonicalSourceLocator;
  metadata?: Record<string, unknown>;
};

// 带顺序、表格绑定、关系和来源的质量层文档图。
export type CanonicalDocument = {
  schema_name?: string;
  document_id: string;
  blocks: CanonicalBlock[];
  tables?: CanonicalTable[];
  table_bindings?: TableFieldBinding[];
  relations?: CanonicalRelation[];
  metadata?: Record<string, unknown>;
};

// 标题、引用等文档内关系及其可验证依据。
export type CanonicalRelation = {
  relation_id: string;
  relation_type: string;
  from_id: string;
  to_id: string;
  status: QualityCapabilityState;
  evidence?: Record<string, unknown>;
};

// 质量层节点、关系或字段绑定回到解析器原始证据的位置。
export type CanonicalSourceLocator = {
  source_block_id: string;
  page_number?: number | null;
  bbox?: unknown[] | null;
  bbox_granularity?: string | null;
  container?: string | null;
  container_name?: string | null;
  cell_ref?: string | null;
  range_ref?: string | null;
  table_cell?: string | null;
  provenance_status: QualityCapabilityState;
};

// 质量层确认后的规范表格；Markdown 只是它的派生表示。
export type CanonicalTable = {
  table_id: string;
  block_id: string;
  table_kind?: string;
  source_locator: CanonicalSourceLocator;
  num_rows: number;
  num_cols: number;
  header_rows?: number | null;
  header_row_indices?: number[];
  title_row_indices?: number[];
  header_state?: QualityCapabilityState;
  row_header_columns?: number[];
  view_scope?: TableViewScope;
  source_has_filter?: boolean | null;
  source_row_count?: number | null;
  emitted_row_count?: number | null;
  hidden_row_count?: number | null;
  cells?: TableCell[];
  grid?: TableGridSlot[][];
  parent_table_id?: string | null;
  parent_cell_id?: string | null;
  nesting_depth?: number;
  metadata?: Record<string, unknown>;
};

// 质量层对单项能力的结论与数量证据。
export type CapabilityAssessment = {
  state: QualityCapabilityState;
  evidence?: Record<string, unknown>;
};

// Markdown 引用的统一二进制资源。
//
// ``path`` 是相对于输出目录的 POSIX 路径，Markdown 可直接用它作为链接；
// ``content`` 在 Python 调用中保持 bytes，在 JSON 中自动编码为 URL-safe
// Base64。业务方可以统一遍历 assets 保存文件。
export type DocumentAsset = {
  asset_id?: string | null;
  path: string;
  kind: AssetKind;
  file_type: string;
  content: string;
  sha256?: string | null;
  width?: number | null;
  height?: number | null;
  anchor?: SourceAnchor | null;
  referenced_by_block_ids?: string[];
  metadata?: Record<string, unknown>;
};

// 解析器无关的最小文档块。
export type DocumentBlock = {
  id?: string;
  source_block_id?: string | null;
  order_index?: number | null;
  kind: BlockKind;
  native_type?: string | null;
  text?: string | null;
  heading_level?: number | null;
  markdown: string;
  anchor?: SourceAnchor;
  metadata?: Record<string, unknown>;
};

// 预检阶段产生的文件特征，供路由器选择能力。
export type DocumentSignals = {
  extension: string;
  size_bytes: number;
  page_count?: number | null;
  has_text_layer?: boolean | null;
  scanned_page_ratio?: number | null;
  language_hint?: string | null;
};

// 统一结果中某项原始证据的可用程度。
export type EvidenceAvailability = "available", "partial", "unavailable", "failed";

// 声明某项 page/bbox/table/OCR 证据是否真实可用。
export type EvidenceCapability = {
  state: EvidenceAvailability;
  granularity?: string | null;
  reason?: string | null;
  evidence?: Record<string, unknown>;
};

// 路由 fallback 中一次实际失败或跳过的尝试。
export type FallbackAttempt = {
  parser_id: string;
  status: string;
  reason: string;
  duration_ms?: number;
};

// 将 issues 和能力阻断项汇总为最终准入依据。
export type GateSummary = {
  critical_issue_count?: number;
  warning_or_info_issue_count?: number;
  reparse_issue_count?: number;
  capability_blockers?: string[];
  blocking_reasons?: string[];
  critical_false_pass?: boolean;
};

export type HTTPValidationError = {
  detail?: ValidationError[];
};

export type IssueSeverity = "critical", "warning", "info";

export type IssueStatus = "unfixed", "repaired", "manual_review_required", "reparse_required", "rejected";

// 解析器原生产物的安全文件引用，不把大型 JSON/二进制塞入公共结果。
export type NativeArtifact = {
  artifact_id: string;
  artifact_type: string;
  path: string;
  file_type: string;
  size_bytes: number;
  sha256: string;
  required_for_quality?: boolean;
  metadata?: Record<string, unknown>;
};

// 图片或扫描页的行/词级 OCR 证据。
export type OcrSpan = {
  level: string;
  text: string;
  bbox: unknown[];
  confidence?: number | null;
  page_number?: number | null;
  rotation_angle?: number | null;
};

// 文本、布局、阅读顺序和表格的质量分。
export type ParseConfidence = {
  text?: number;
  layout?: number;
  reading_order?: number;
  table?: number;
  overall?: number;
};

export type ParseJobResponse = {
  parse_id: string;
  package_path: string;
  document: ParsedDocument;
  native_artifact_count: number;
};

export type ParseRecordResponse = {
  parse_id: string;
  package_path: string;
  document: ParsedDocument;
};

// 所有解析方式必须输出的稳定文档协议。
//
// 外层调用统一读取 ``markdown``；需要结构化检索时读取 ``blocks``；需要保存
// 图片时遍历 ``assets``。这三个字段在所有解析器结果中始终存在。
export type ParsedDocument = {
  document_id?: string;
  filename: string;
  file_type: string;
  source_size_bytes?: number | null;
  source_sha256?: string | null;
  routing_decision?: RoutingDecision | null;
  markdown: string;
  blocks: DocumentBlock[];
  assets?: DocumentAsset[];
  tables?: ParsedTable[];
  ocr_spans?: OcrSpan[];
  retrieval_chunks?: RetrievalChunk[];
  visual_evidence?: VisualEvidence[];
  confidence: ParseConfidence;
  provenance: ParserProvenance;
  warnings?: string[];
  native_artifacts?: NativeArtifact[];
  capabilities?: Record<string, EvidenceCapability>;
  alternatives?: Record<string, unknown>[];
  schema_name?: string;
  created_at?: string;
};

// 朱统一层交给质量层的表格结构证据。
export type ParsedTable = {
  table_id: string;
  block_id: string;
  html?: string | null;
  markdown?: string | null;
  caption?: string | null;
  image_path?: string | null;
  page_number?: number | null;
  bbox?: unknown[] | null;
  num_rows?: number | null;
  num_cols?: number | null;
  table_kind?: string;
  source_container?: string | null;
  source_container_name?: string | null;
  source_range?: string | null;
  header_rows?: number | null;
  row_header_columns?: number[];
  view_scope?: TableViewScope;
  source_has_filter?: boolean | null;
  source_row_count?: number | null;
  emitted_row_count?: number | null;
  hidden_row_count?: number | null;
  cells?: TableCell[];
  grid?: TableGridSlot[][];
  parent_table_id?: string | null;
  parent_cell_id?: string | null;
  nesting_depth?: number;
  metadata?: Record<string, unknown>;
};

// 一个解析连接器声明的可用能力。
export type ParserCapability = {
  parser_id: string;
  provider: string;
  display_name: string;
  formats: string[];
  model_versions?: string[];
  default_model_version?: string | null;
  requires_network?: boolean;
  requires_gpu?: boolean;
  available?: boolean;
  unavailable_reason?: string | null;
};

export type ParserListResponse = {
  parsers: ParserCapability[];
};

// 记录解析器、参数和耗时，保证结果可解释与复现。
export type ParserProvenance = {
  parser_id: string;
  requested_parser_id?: string | null;
  routing_mode?: RoutingMode | null;
  model?: string | null;
  version?: string;
  parameters?: Record<string, unknown>;
  format_conversion_duration_ms?: number;
  markitdown_duration_ms?: number;
  parse_duration_ms?: number;
  peak_memory_mb?: number | null;
  fallback_history?: FallbackAttempt[];
};

// Canonical 中某项能力或关系的证据状态。
export type QualityCapabilityState = "verified", "inferred", "manual_review_required", "reparse_required", "rejected", "unavailable";

// 一条可定位、可跟踪、可复核的质量问题。
export type QualityIssue = {
  issue_id: string;
  rule_id: string;
  severity: IssueSeverity;
  category: string;
  status: IssueStatus;
  message: string;
  affected_block_ids?: string[];
  evidence?: Record<string, unknown>;
};

// 质量层交给 Wiki 的统一返回协议。
//
// 物理交付固定包含 ``optimized.md``、``structure.json`` 和
// ``quality_issues.json``。大表追加 ``table_index.sqlite3``，避免在
// JSON 中展开海量单元格和字段绑定。``optimized_markdown`` 保留在
// 内存/API 返回中，落盘时单独写入 Markdown。
export type QualityPackage = {
  schema_name?: string;
  document_id: string;
  optimized_markdown: string;
  canonical_document: CanonicalDocument;
  quality_report: QualityReport;
};

export type QualityPackageResponse = {
  parse_id: string;
  package_path: string;
  quality_package: QualityPackage;
};

// 质量层给编排、审核台和前端的正式报告。
export type QualityReport = {
  contract_version?: string;
  document_id: string;
  state: QualityState;
  issues?: QualityIssue[];
  resolved_issues?: QualityIssue[];
  applied_repairs?: AppliedRepair[];
  rejected_repairs?: Record<string, unknown>[];
  capability_matrix: Record<string, CapabilityAssessment>;
  gate_summary: GateSummary;
  metrics?: Record<string, unknown>;
  reparse_recommendation?: ReparseRecommendation | null;
};

// 整篇文档的最终准入状态。
export type QualityState = "pass", "pass_with_warnings", "reparse_required", "rejected";

// 质量层返回给路由层的重新解析建议。
export type ReparseRecommendation = {
  parser_id: string;
  reason: string;
  parser_options?: Record<string, unknown>;
};

export type ReparseRequest = {
  parser_id?: string | null;
  options?: Record<string, unknown>;
};

// 杨多模态层产出的可检索单元及其证据关联。
export type RetrievalChunk = {
  chunk_id: string;
  item_ids?: string[];
  text: string;
  breadcrumb?: string | null;
  modalities?: string[];
  asset_ids?: string[];
  page_refs?: number[];
  context_item_ids?: string[];
  searchable?: boolean;
  needs_review?: boolean;
  metadata?: Record<string, unknown>;
};

// 张云雅路由层交给统一接入层的稳定决策协议。
export type RoutingDecision = {
  schema_name?: string;
  mode: RoutingMode;
  requested_parser_id?: string | null;
  selected_parser_id: string;
  reason: string;
  signals: DocumentSignals;
  parser_options?: Record<string, unknown>;
  fallback_parser_ids?: string[];
  allow_automatic_fallback?: boolean;
  unavailable_reasons?: Record<string, string>;
  created_at?: string;
};

// 模型由系统自动选择，或由用户明确指定。
export type RoutingMode = "auto", "manual";

// 文档块到原文的定位信息。
export type SourceAnchor = {
  page_number?: number | null;
  page_end?: number | null;
  bbox?: unknown[] | null;
  page_width?: number | null;
  page_height?: number | null;
  coordinate_system?: string | null;
  origin?: string | null;
  page_unit?: string | null;
  bbox_granularity?: string | null;
  provenance_status?: string | null;
  section_path?: string[];
  table_cell?: string | null;
  container?: string | null;
  container_name?: string | null;
  cell_ref?: string | null;
  range_ref?: string | null;
  source_object_id?: string | null;
  original_text?: string | null;
};

// 解析器提供的物理表格网格单元。
export type TableCell = {
  cell_id?: string | null;
  text: string;
  raw_value?: unknown | null;
  display_value?: string | null;
  normalized_value?: string | null;
  value_type?: string | null;
  formula?: string | null;
  start_row: number;
  start_col: number;
  row_span?: number;
  col_span?: number;
  column_header?: boolean;
  row_header?: boolean;
  roles?: string[];
  visible?: boolean | null;
  bbox?: unknown[] | null;
  source_anchor?: SourceAnchor | null;
};

// 行键、完整列路径和值之间的可回溯表格绑定。
export type TableFieldBinding = {
  binding_id: string;
  table_id: string;
  block_id: string;
  row_key: string;
  row_path?: string[];
  column_path: string[];
  row_cell_ids?: string[];
  column_cell_ids?: string[];
  value_cell_id?: string | null;
  value: string;
  source_locator: CanonicalSourceLocator;
  status: QualityCapabilityState;
  evidence?: Record<string, unknown>;
};

// 逻辑网格中的原始单元格或合并覆盖位置。
export type TableGridSlot = {
  kind: TableSlotKind;
  cell_id?: string | null;
  origin_cell_id?: string | null;
};

// 逻辑网格槽位类型；合并覆盖位不是新的源单元格。
export type TableSlotKind = "origin", "covered";

// 表格输出覆盖的是全量行、可见行还是未知视图。
export type TableViewScope = "all_rows", "visible_rows", "unknown";

export type ValidationError = {
  loc: string | number[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
};

export type VisualClaim = {
  statement: string;
  provenance: VisualClaimProvenance;
};

export type VisualClaimProvenance = "extracted", "inferred", "ambiguous";

// 一张图片的 Caption 或 OCR 结果槽位。
export type VisualEvidence = {
  id: string;
  kind: VisualEvidenceKind;
  text?: string;
  asset_id: string;
  parent_item_ids?: string[];
  parent_chunk_ids?: string[];
  page_refs?: number[];
  status: VisualEvidenceStatus;
  searchable?: boolean;
  provenance?: VisualEvidenceProvenance | null;
  claims?: VisualClaim[];
  reason?: string | null;
  error?: string | null;
};

export type VisualEvidenceKind = "image_caption", "image_ocr";

export type VisualEvidenceProvenance = {
  source: string;
  model: string;
  model_version?: string | null;
  prompt_version?: string | null;
  task?: string | null;
};

export type VisualEvidenceStatus = "ready", "skipped", "ambiguous", "error", "missing";
