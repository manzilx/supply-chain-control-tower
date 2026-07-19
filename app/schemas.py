from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


Severity = Literal["low", "medium", "high", "critical"]
Criticality = Literal["low", "medium", "high", "mission-critical"]
DocumentKind = Literal[
    "drawing", "spec", "GA", "QAP", "ITP", "MDR", "test_cert", "MOM"
]
BomStatus = Literal[
    "spec_missing", "planned", "requisitioned", "ordered", "delivered"
]
MilestonePhase = Literal[
    "engineering", "procurement", "fabrication", "delivery", "installation", "commissioning"
]


class CompanyProfile(BaseModel):
    company_name: str = "Northwind Heavy Engineering"
    sector: str = "Industrial EPC"
    active_projects: int = 4
    planner_horizon_days: int = 90
    target_service_level_pct: float = 97.5


class SupplierRecord(BaseModel):
    name: str
    category: str
    country: str
    lead_time_days: int
    on_time_delivery_pct: float
    quality_ppm: int
    annual_spend_usd: float
    approved_alternatives: int = 0
    risk_flags: List[str] = Field(default_factory=list)


class InventoryItem(BaseModel):
    sku: str
    description: str
    category: str
    supplier_name: str
    on_hand_qty: float
    reorder_point_qty: float
    safety_stock_qty: float
    daily_demand_qty: float
    lead_time_days: int
    unit_cost_usd: float
    criticality: Criticality = "medium"


class PurchaseOrder(BaseModel):
    po_number: str
    supplier_name: str
    sku: str
    quantity: float
    due_in_days: int
    value_usd: float
    status: Literal["planned", "released", "in_transit", "delayed", "received"]
    expedite_possible: bool = False


class DemandSignal(BaseModel):
    sku: str
    next_30_day_demand_qty: float
    next_90_day_demand_qty: float
    confidence_pct: float = 75.0


class Incident(BaseModel):
    title: str
    severity: Severity
    description: str
    supplier_name: Optional[str] = None
    sku: Optional[str] = None
    days_open: int = 0


class AgentRequest(BaseModel):
    company: CompanyProfile
    suppliers: List[SupplierRecord]
    inventory: List[InventoryItem]
    purchase_orders: List[PurchaseOrder]
    demand_signals: List[DemandSignal]
    incidents: List[Incident] = Field(default_factory=list)
    ask: str = "What should the supply chain team do this week?"


class RiskRecord(BaseModel):
    title: str
    risk_type: str
    severity: Severity
    score: int = Field(ge=0, le=100)
    summary: str
    supplier_name: Optional[str] = None
    sku: Optional[str] = None
    owner: str


class RecommendedAction(BaseModel):
    title: str
    priority: Literal["P1", "P2", "P3"]
    owner: str
    due_in_days: int
    rationale: str


class WatchMetric(BaseModel):
    label: str
    value: str
    direction: Literal["up", "down", "steady"] = "steady"


class AgentResponse(BaseModel):
    generated_at: datetime
    overall_risk_score: int
    executive_summary: str
    ai_assistant_response: str
    top_risks: List[RiskRecord]
    recommended_actions: List[RecommendedAction]
    watch_metrics: List[WatchMetric]
    assumptions: List[str]


# --- M2: Projects, BOM, Procurement Plan -------------------------------------


class Document(BaseModel):
    doc_id: str
    tenant_id: str = "arcforge"
    kind: DocumentKind
    title: str
    url: Optional[str] = None
    version: str = "A"


class Milestone(BaseModel):
    code: str
    name: str
    phase: MilestonePhase
    required_on_site_date: date


class Project(BaseModel):
    project_id: str
    tenant_id: str = "arcforge"
    name: str
    client: str
    site: str
    sector: str = "Industrial EPC"
    currency: str = "USD"
    start_date: date
    milestones: List[Milestone] = Field(default_factory=list)


class BOMItem(BaseModel):
    bom_item_id: str
    tenant_id: str = "arcforge"
    project_id: str
    parent_item_id: Optional[str] = None
    level: int = 1
    code: str
    description: str
    category: Optional[str] = None
    quantity: float
    uom: str = "EA"
    unit_cost_usd: Optional[float] = None
    supplier_name: Optional[str] = None
    spec_doc_id: Optional[str] = None
    drawing_id: Optional[str] = None
    long_lead_days: Optional[int] = None
    planned_need_date: Optional[date] = None
    milestone_code: Optional[str] = None
    status: BomStatus = "planned"


class BOMItemPatch(BaseModel):
    """Partial update for BOM lines — used by autofill apply."""

    category: Optional[str] = None
    supplier_name: Optional[str] = None


class ProcurementPackage(BaseModel):
    package_id: str
    project_id: str
    milestone_code: str
    milestone_name: str
    required_on_site_date: date
    bom_item_ids: List[str]
    item_count: int
    total_value_usd: float
    earliest_need_date: Optional[date] = None
    long_lead_count: int = 0
    missing_spec_count: int = 0


class PlanFlag(BaseModel):
    bom_item_id: str
    code: str
    description: str
    reason: str
    severity: Severity
    milestone_code: Optional[str] = None
    days_until_need: Optional[int] = None
    long_lead_days: Optional[int] = None


class PlanSummary(BaseModel):
    bom_item_count: int
    packages_count: int
    long_lead_count: int
    missing_spec_count: int
    total_value_usd: float
    earliest_need_date: Optional[date] = None
    latest_need_date: Optional[date] = None


class ProcurementPlan(BaseModel):
    project_id: str
    project_name: str
    generated_at: datetime
    summary: PlanSummary
    packages: List[ProcurementPackage]
    long_lead_items: List[PlanFlag]
    missing_spec_items: List[PlanFlag]
    assumptions: List[str]


class BomUploadResult(BaseModel):
    project_id: str
    rows_parsed: int
    rows_accepted: int
    rows_rejected: int
    errors: List[str] = Field(default_factory=list)
    bom_items: List[BOMItem]


class IngestSheetPreview(BaseModel):
    sheet: str
    entity: Optional[Literal["project", "bom", "supplier"]] = None
    rows_total: int
    rows_valid: int
    mapped: dict          # canonical field -> source header
    unmapped: List[str]
    errors: List[str]
    sample: List[dict]    # first 5 normalised rows


class IngestPreviewReply(BaseModel):
    staging_id: str
    filename: str
    sheets: List[IngestSheetPreview]
    total_valid: int
    total_rows: int


class IngestCommitRequest(BaseModel):
    staging_id: str
    default_project_id: Optional[str] = None


class IngestCommitReply(BaseModel):
    created: dict         # {projects, bom_items, suppliers}
    errors: List[str]
    refs: List[str]


AlertSeverity = Literal["critical", "high", "medium", "low", "info"]


class Alert(BaseModel):
    alert_id: str
    severity: AlertSeverity
    category: str            # approval | schedule | vendor | commercial | expediting | engineering
    title: str
    detail: str
    href: str


class AlertFeed(BaseModel):
    generated_at: datetime
    total: int
    counts: dict             # severity -> count
    alerts: List[Alert]


class PortfolioCounts(BaseModel):
    projects: int
    bom_lines: int
    prs: int
    rfqs: int
    pos: int


class PortfolioCompletionBucket(BaseModel):
    label: str
    count: int


class PortfolioSpend(BaseModel):
    total_budget_usd: float
    total_committed_usd: float
    total_awarded_usd: float
    committed_pct: float
    open_prs: int


class PortfolioScheduleItem(BaseModel):
    project_id: str
    project_name: str
    milestone_code: str
    milestone_name: str
    required_on_site_date: date
    days_until: int
    completion_pct: float
    at_risk: bool


class PortfolioSchedule(BaseModel):
    at_risk: List[PortfolioScheduleItem]
    upcoming_14d: List[PortfolioScheduleItem]


class PortfolioActivity(BaseModel):
    at: datetime
    action: str
    entity_kind: str
    subject: str
    summary: str
    project_id: Optional[str] = None


class SearchIndexItem(BaseModel):
    kind: Literal["project", "bom", "vendor", "pr", "po"]
    id: str
    title: str
    subtitle: Optional[str] = None
    href: str
    project_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class SearchIndex(BaseModel):
    generated_at: datetime
    items: List[SearchIndexItem]


class PortfolioSummary(BaseModel):
    generated_at: datetime
    counts: PortfolioCounts
    average_completion_pct: float
    completion_buckets: List[PortfolioCompletionBucket]
    spend: PortfolioSpend
    schedule: PortfolioSchedule
    activity: List[PortfolioActivity]


class ProjectProgress(BaseModel):
    """Blended physical/schedule/commercial completion for a project.

    completion_pct = 0.40*milestones + 0.40*bom_delivered + 0.20*spend_committed.
    Committed spend is the value of BOM lines in `ordered` or `delivered`
    status (a self-contained proxy that needs no sourcing-store join).
    """
    project_id: str
    completion_pct: float            # blended 0-100
    milestones_pct: float
    bom_delivered_pct: float
    spend_committed_pct: float
    milestones_passed: int
    milestones_total: int
    bom_delivered: int
    bom_total: int
    committed_value_usd: float
    budget_value_usd: float


# --- M3: Sourcing (PR → RFQ → Quote → Award → PO) ----------------------------


PRStatus = Literal["draft", "rfq_issued", "quoted", "awarded", "po_created", "cancelled"]
RFQStatus = Literal["open", "quotes_received", "evaluated", "awarded", "cancelled"]
SourcingStrategy = Literal["single_source", "multi_source", "rate_contract", "emergency_buy"]
Incoterm = Literal["EXW", "FCA", "FOB", "CIF", "CIP", "DAP", "DDP"]


SapStatus = Literal["draft", "submitting", "synced", "failed"]


class PurchaseRequisition(BaseModel):
    pr_no: str
    tenant_id: str = "arcforge"
    project_id: str
    bom_item_id: Optional[str] = None
    code: str
    description: str
    quantity: float
    uom: str = "EA"
    need_by: Optional[date] = None
    milestone_code: Optional[str] = None
    budget_value_usd: Optional[float] = None
    buyer: str = "Unassigned"
    strategy: SourcingStrategy = "multi_source"
    status: PRStatus = "draft"
    rfq_no: Optional[str] = None
    award_id: Optional[str] = None
    po_no: Optional[str] = None
    created_at: datetime
    # SAP CPI integration fields (Phase 0)
    sap_pr_no: Optional[str] = None
    sap_status: SapStatus = "draft"
    sap_last_synced_at: Optional[datetime] = None
    sap_error: Optional[str] = None


class RFQ(BaseModel):
    rfq_no: str
    tenant_id: str = "arcforge"
    pr_no: str
    project_id: str
    code: str
    description: str
    quantity: float
    uom: str = "EA"
    vendors: List[str] = Field(default_factory=list)
    issued_at: datetime
    due_at: datetime
    status: RFQStatus = "open"
    notes: Optional[str] = None


class Quote(BaseModel):
    quote_id: str
    tenant_id: str = "arcforge"
    rfq_no: str
    vendor: str
    unit_price_usd: float
    quantity: float
    total_usd: float
    lead_time_days: int
    incoterm: Incoterm = "CIP"
    validity_days: int = 30
    received_at: datetime
    notes: Optional[str] = None


class QuoteEvaluation(BaseModel):
    vendor: str
    quote_id: str
    total_usd: float
    lead_time_days: int
    price_index: float  # 1.0 = lowest
    lead_time_index: float  # 1.0 = shortest
    otd_pct: Optional[float] = None
    quality_ppm: Optional[int] = None
    reliability_score: float  # 0–100 composite
    composite_score: float  # 0–100, higher is better
    rank: int


class QuoteComparison(BaseModel):
    rfq_no: str
    generated_at: datetime
    evaluations: List[QuoteEvaluation]
    recommended_vendor: Optional[str] = None
    recommendation_rationale: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


# --- Technical Bid Evaluation (TBE) ----------------------------------------


ComplianceLevel = Literal["full", "partial", "deviation", "non_compliant", "not_assessed"]
CriterionCategory = Literal[
    "spec_compliance",
    "scope_of_supply",
    "materials",
    "performance",
    "quality",
    "documentation",
    "warranty",
    "spares_service",
    "delivery_terms",
    "experience",
    "commercial_terms",
]


class TechnicalCriterion(BaseModel):
    criterion_id: str
    name: str
    description: str
    category: CriterionCategory
    weight: float = Field(ge=0, le=1)  # 0..1; sum across criteria for an RFQ should ~= 1.0
    mandatory: bool = False  # if true, a non-compliant score on this disqualifies the vendor


class CriterionScore(BaseModel):
    criterion_id: str
    score: int = Field(ge=0, le=100)
    compliance: ComplianceLevel = "not_assessed"
    note: str = ""
    deviation_text: Optional[str] = None


class TechnicalEvaluation(BaseModel):
    rfq_no: str
    quote_id: str
    vendor: str
    criteria_scores: List[CriterionScore] = Field(default_factory=list)
    technical_score: int = 0
    technical_grade: Literal["A", "B", "C", "D", "F"] = "F"
    disqualified: bool = False
    disqualification_reason: Optional[str] = None
    notes: str = ""
    source: Literal["manual", "grok", "deterministic"] = "manual"
    evaluated_by: str = "Control Tower"
    evaluated_at: datetime


class CombinedEvaluation(BaseModel):
    vendor: str
    quote_id: str
    commercial_score: float       # 0..100 (from QuoteComparison.composite_score)
    technical_score: int          # 0..100
    combined_score: float         # weighted blend
    commercial_rank: int
    technical_rank: int
    combined_rank: int
    deviations_count: int
    disqualified: bool = False
    notes: List[str] = Field(default_factory=list)


class TBE(BaseModel):
    """Technical Bid Evaluation — combined commercial + technical comparison."""

    rfq_no: str
    generated_at: datetime
    criteria: List[TechnicalCriterion]
    technical_evaluations: List[TechnicalEvaluation]
    commercial: Optional[QuoteComparison] = None
    combined: List[CombinedEvaluation]
    commercial_weight: float = 0.6     # default 60% commercial / 40% technical
    technical_weight: float = 0.4
    recommended_vendor: Optional[str] = None
    recommendation_rationale: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class SetCriteriaRequest(BaseModel):
    criteria: List[TechnicalCriterion]


class SetTechnicalEvaluationRequest(BaseModel):
    criteria_scores: List[CriterionScore]
    notes: Optional[str] = None
    evaluated_by: Optional[str] = None


class SetWeightsRequest(BaseModel):
    commercial_weight: float = Field(ge=0, le=1)
    technical_weight: float = Field(ge=0, le=1)


# --- Audit Trail ------------------------------------------------------------


AuditEntityKind = Literal[
    "bom_item", "project", "pr", "rfq", "quote", "award", "po",
    "shipment", "shipment_event", "technical_evaluation", "sap_event",
    "vendor", "spec", "approval", "ai_brief", "system",
]

AuditAction = Literal[
    "created", "updated", "deleted",
    "uploaded",       # BOM CSV upload
    "issued",         # RFQ issued
    "received",       # quote received
    "evaluated",      # technical evaluation
    "compared",       # quote comparison
    "awarded",
    "po_drafted",
    "submitted_to_sap",
    "sap_status_changed",
    "stage_advanced", # shipment stage
    "gr_posted",
    "ir_posted",
    "delivered",
    "approved",
    "rejected",
    "exported",
    "ai_generated",
    "followup_sent",
]

AuditSource = Literal["ui", "api", "sap_webhook", "ai", "scheduled_job", "csv_upload", "system"]


class AuditEvent(BaseModel):
    event_id: str
    occurred_at: datetime
    actor: str = "system"                # user_id, "system", "grok", "sap_cpi"
    action: AuditAction
    entity_kind: AuditEntityKind
    entity_id: str                       # e.g. "PR-00001", "HYD-CV-001", "SPO-00012"
    subject: str                         # short human label
    summary: str                         # one-line human readable
    source: AuditSource = "system"
    tenant_id: str = ""                  # empty = legacy/unscoped; new emits must set it
    # Lineage links — keep all known parent refs to enable forward/backward trace
    bom_item_id: Optional[str] = None
    bom_code: Optional[str] = None       # material code (e.g. "VALVE-16-A105") — pivot key
    project_id: Optional[str] = None
    pr_no: Optional[str] = None
    rfq_no: Optional[str] = None
    quote_id: Optional[str] = None
    award_id: Optional[str] = None
    po_no: Optional[str] = None
    vendor: Optional[str] = None         # vendor name — pivot key
    sap_doc_no: Optional[str] = None
    # Optional value diff or payload (kept small)
    before: Optional[dict] = None
    after: Optional[dict] = None
    metadata: Optional[dict] = None


class PivotCount(BaseModel):
    """One row in a pivot list — used by /audit/pivots/{kind}."""

    key: str                              # bom_code | po_no | vendor name
    label: str                            # display label
    event_count: int
    last_at: Optional[datetime] = None
    # Context — populated where applicable
    description: Optional[str] = None
    project_id: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    value_usd: Optional[float] = None
    related_pos: int = 0
    related_rfqs: int = 0
    related_vendors: int = 0


class AuditPage(BaseModel):
    events: List[AuditEvent]
    total: int                            # total matching the filter (before pagination)
    has_more: bool
    next_offset: Optional[int] = None


class TraceStage(BaseModel):
    """One node in the BOM-to-Delivery chain."""

    stage: Literal[
        "bom_item", "spec", "pr", "rfq", "quotes", "technical_eval",
        "award", "po", "sap", "shipment", "delivery", "invoice",
    ]
    label: str
    entity_id: Optional[str] = None
    status: Optional[str] = None
    occurred_at: Optional[datetime] = None
    actor: Optional[str] = None
    detail: Optional[str] = None
    payload: Optional[dict] = None        # small extract of key fields
    children: List[str] = Field(default_factory=list)
    complete: bool = False


class TraceabilityChain(BaseModel):
    """Forward chain from a BOM item (or any entity) to delivery."""

    root_kind: AuditEntityKind
    root_id: str
    project_id: Optional[str] = None
    stages: List[TraceStage]
    generated_at: datetime
    events_count: int


class Award(BaseModel):
    award_id: str
    tenant_id: str = "arcforge"
    rfq_no: str
    pr_no: str
    vendor: str
    quote_id: str
    awarded_value_usd: float
    rationale: str
    awarded_at: datetime
    awarded_by: str = "Control Tower"


class SourcingPO(BaseModel):
    po_no: str
    tenant_id: str = "arcforge"
    pr_no: str
    rfq_no: str
    award_id: str
    project_id: str
    vendor: str
    code: str
    description: str
    quantity: float
    uom: str
    unit_price_usd: float
    value_usd: float
    incoterm: Incoterm
    need_by: Optional[date] = None
    lead_time_days: int
    created_at: datetime
    status: Literal["draft", "released", "in_transit", "delivered"] = "draft"
    # SAP CPI integration fields (Phase 0)
    sap_po_no: Optional[str] = None
    sap_status: SapStatus = "draft"
    sap_last_synced_at: Optional[datetime] = None
    sap_error: Optional[str] = None
    sap_gr_qty: Optional[float] = None   # goods receipt qty from SAP
    sap_ir_value_usd: Optional[float] = None  # invoice receipt value from SAP


class SourcingTimelineEvent(BaseModel):
    kind: Literal["pr_created", "rfq_issued", "quote_received", "evaluated", "awarded", "po_created"]
    at: datetime
    ref_id: str
    title: str
    detail: str


class SourcingTimeline(BaseModel):
    po_no: str
    events: List[SourcingTimelineEvent]


class CreatePRRequest(BaseModel):
    project_id: str
    bom_item_id: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    uom: Optional[str] = None
    need_by: Optional[date] = None
    milestone_code: Optional[str] = None
    budget_value_usd: Optional[float] = None
    buyer: Optional[str] = None
    strategy: Optional[SourcingStrategy] = None


class CreateRFQRequest(BaseModel):
    pr_no: str
    vendors: List[str]
    due_in_days: int = 10
    notes: Optional[str] = None


class CreateQuoteRequest(BaseModel):
    vendor: str
    unit_price_usd: float
    lead_time_days: int
    quantity: Optional[float] = None
    incoterm: Incoterm = "CIP"
    validity_days: int = 30
    notes: Optional[str] = None


class AwardRFQRequest(BaseModel):
    quote_id: str
    rationale: Optional[str] = None
    awarded_by: Optional[str] = None


# --- M4: Vendor Intelligence + Expediting -----------------------------------


ScoreDimension = Literal["delivery", "quality", "price", "responsiveness", "claims", "risk"]
Grade = Literal["A", "B", "C", "D", "F"]
ExpediteUrgency = Literal["ok", "watch", "nudge", "escalate"]
EmailTone = Literal["standard", "firm", "urgent"]


class ScorecardComponent(BaseModel):
    dimension: ScoreDimension
    score: int = Field(ge=0, le=100)
    grade: Grade
    label: str
    value: str
    note: str


class VendorAlternate(BaseModel):
    name: str
    category: str
    country: str
    composite_score: int
    lead_time_days: int
    on_time_delivery_pct: float
    reason: str


class VendorScorecard(BaseModel):
    vendor: str
    category: str
    country: str
    lead_time_days: int
    annual_spend_usd: float
    composite_score: int
    composite_grade: Grade
    components: List[ScorecardComponent]
    flags: List[str]
    single_source_exposure: bool
    concentration_pct: float
    approved_alternatives: int
    alternates: List[VendorAlternate]


class VendorSummary(BaseModel):
    vendor: str
    category: str
    country: str
    composite_score: int
    composite_grade: Grade
    annual_spend_usd: float
    on_time_delivery_pct: float
    quality_ppm: int
    flags_count: int
    single_source_exposure: bool


class VendorBriefing(BaseModel):
    """LLM-generated risk briefing for a single vendor (with deterministic fallback)."""

    vendor: str
    headline: str
    body: str
    watchlist: List[str]
    generated_at: datetime
    source: Literal["grok", "deterministic"]


class RiskMitigationsReply(BaseModel):
    """LLM-generated mitigations for a single risk record."""

    risk_title: str
    mitigations: List[str]
    source: Literal["grok", "deterministic"]
    generated_at: datetime


class ExplainRequest(BaseModel):
    kind: Literal["po", "vendor", "risk", "project", "rfq", "pr"]
    id: str  # po_number / vendor name / risk title / project_id / rfq_no / pr_no


class ExplainReply(BaseModel):
    kind: str
    id: str
    headline: str
    body: str
    bullets: List[str]
    source: Literal["grok", "deterministic"]
    generated_at: datetime


class BOMAutofillSuggestion(BaseModel):
    bom_item_id: str
    code: str
    description: str
    current_category: Optional[str] = None
    current_supplier: Optional[str] = None
    suggested_category: Optional[str] = None
    suggested_supplier: Optional[str] = None
    reason: str


class BOMAutofillReply(BaseModel):
    project_id: str
    suggestions: List[BOMAutofillSuggestion]
    source: Literal["grok", "deterministic"]
    generated_at: datetime


class SpecRequestReply(BaseModel):
    bom_item_id: str
    code: str
    to_placeholder: str
    subject: str
    body: str
    source: Literal["grok", "deterministic"]
    generated_at: datetime


class CategoryConcentration(BaseModel):
    category: str
    vendor_count: int
    total_spend_usd: float
    top_vendor: str
    top_vendor_share_pct: float
    single_source: bool


class ExpediteItem(BaseModel):
    po_number: str
    supplier_name: str
    sku: Optional[str] = None
    description: Optional[str] = None
    quantity: float
    value_usd: float
    due_in_days: int
    status: str
    predicted_slip_days: int
    slip_probability_pct: int
    urgency: ExpediteUrgency
    reasons: List[str]
    source: Literal["scenario", "sourcing"]
    project_id: Optional[str] = None
    last_followup_at: Optional[datetime] = None
    followup_count: int = 0


class ExpediteSummary(BaseModel):
    total: int
    ok: int
    watch: int
    nudge: int
    escalate: int
    value_at_risk_usd: float


class ExpediteQueue(BaseModel):
    generated_at: datetime
    items: List[ExpediteItem]
    summary: ExpediteSummary


class FollowupEmail(BaseModel):
    po_number: str
    vendor: str
    tone: EmailTone
    to_placeholder: str
    subject: str
    body: str
    requested_documents: List[str]
    generated_at: datetime


class DraftFollowupRequest(BaseModel):
    tone: EmailTone = "standard"
    request_documents: bool = True
    extra_notes: Optional[str] = None


class LogFollowupRequest(BaseModel):
    tone: Optional[EmailTone] = None


# --- M5: Logistics + Commercial + Risk simulations --------------------------


ShipmentStage = Literal[
    "manufacturing",
    "ready_to_dispatch",
    "dispatched",
    "in_transit",
    "at_port",
    "at_customs",
    "last_mile",
    "delivered",
]
FreightMode = Literal["sea", "air", "road", "rail", "local"]


class ShipmentEvent(BaseModel):
    event_id: str
    po_ref: str
    stage: ShipmentStage
    at: datetime
    location: Optional[str] = None
    note: Optional[str] = None


class Shipment(BaseModel):
    po_ref: str
    tenant_id: str = "arcforge"
    source: Literal["scenario", "sourcing"]
    vendor: str
    code: Optional[str] = None
    description: Optional[str] = None
    origin_country: Optional[str] = None
    destination_site: Optional[str] = None
    value_usd: float
    quantity: float
    mode: FreightMode
    current_stage: ShipmentStage
    required_on_site: Optional[date] = None
    estimated_arrival: Optional[date] = None
    bottleneck: Optional[str] = None
    slack_days: Optional[int] = None
    events: List[ShipmentEvent]


class LogisticsSummary(BaseModel):
    total: int
    in_motion: int
    at_bottleneck: int
    delivered: int
    value_in_motion_usd: float


class LogisticsQueue(BaseModel):
    generated_at: datetime
    shipments: List[Shipment]
    summary: LogisticsSummary


class ModeRecommendation(BaseModel):
    po_ref: str
    current_mode: FreightMode
    recommended_mode: FreightMode
    transit_days_estimate: int
    cost_multiplier: float
    rationale: str
    days_until_need: Optional[int] = None


class AddShipmentEventRequest(BaseModel):
    stage: ShipmentStage
    location: Optional[str] = None
    note: Optional[str] = None


# --- Commercial --------------------------------------------------------------


class CommercialLine(BaseModel):
    ref_id: str
    tenant_id: str = "arcforge"
    project_id: str
    code: str
    description: str
    vendor: Optional[str] = None
    budget_value_usd: Optional[float] = None
    quoted_value_usd: Optional[float] = None
    awarded_value_usd: Optional[float] = None
    final_po_value_usd: Optional[float] = None
    savings_usd: float = 0
    variance_pct: float = 0
    currency: str = "USD"
    state: Literal["budget_only", "quoted", "awarded", "delivered"] = "budget_only"


class ProjectCommercialSummary(BaseModel):
    project_id: str
    project_name: str
    line_count: int
    total_budget_usd: float
    total_quoted_usd: float
    total_awarded_usd: float
    total_savings_usd: float
    savings_pct: float
    variance_pct: float
    over_budget_lines: int


class CommercialSummary(BaseModel):
    generated_at: datetime
    total_budget_usd: float
    total_awarded_usd: float
    total_savings_usd: float
    savings_pct: float
    projects: List[ProjectCommercialSummary]
    top_savings: List[CommercialLine]
    top_overruns: List[CommercialLine]


# --- Risk simulations -------------------------------------------------------


SimulationScenario = Literal["vendor_slip_2w", "customs_hold", "alt_vendor"]


class SimulationRequest(BaseModel):
    scenario: SimulationScenario
    target: str
    alternate_vendor: Optional[str] = None
    custom_slip_days: Optional[int] = None


class AffectedItem(BaseModel):
    ref_id: str
    code: str
    description: str
    impact: str
    original_need_date: Optional[date] = None
    new_expected_date: Optional[date] = None


class MilestoneImpact(BaseModel):
    project_id: str
    project_name: str
    milestone_code: str
    milestone_name: str
    original_date: date
    new_date: date
    slip_days: int


class SimulationResult(BaseModel):
    scenario: SimulationScenario
    target: str
    generated_at: datetime
    headline: str
    severity: Severity
    cost_delta_usd: float
    schedule_delta_days: int
    affected_items: List[AffectedItem]
    milestone_impacts: List[MilestoneImpact]
    mitigations: List[str]
    assumptions: List[str]
    narrative: Optional[str] = None  # LLM-synthesized executive narrative; None on deterministic fallback


# --- M6: AI Command Center --------------------------------------------------


AgentPersona = Literal[
    "sourcing", "expediting", "vendor_risk", "logistics", "commercial", "planning", "reporting", "general"
]
WeeklyCategory = Literal[
    "sourcing", "expediting", "vendor_risk", "logistics", "commercial", "planning"
]


class WeeklyPlanItem(BaseModel):
    priority: Literal["P1", "P2", "P3"]
    category: WeeklyCategory
    title: str
    why: str
    expected_impact: str
    owner: str
    due_in_days: int
    confidence: int = Field(ge=0, le=100)
    supporting_refs: List[str]
    href: Optional[str] = None
    primary_action: Optional[str] = None


class WeeklyPlan(BaseModel):
    generated_at: datetime
    week_of: date
    headline: str
    kpi_snapshot: List["KpiSnapshot"]
    items: List[WeeklyPlanItem]
    assumptions: List[str]
    synthesized_narrative: Optional[str] = None  # 1-2 paragraph LLM synthesis over the whole plan


class KpiSnapshot(BaseModel):
    label: str
    value: str
    tone: Literal["neutral", "good", "warn", "bad"] = "neutral"


WeeklyPlan.model_rebuild()


# --- M7: Auth + Tenants + Approvals -----------------------------------------


Role = Literal["admin", "procurement_head", "buyer", "expeditor", "viewer"]


class Tenant(BaseModel):
    tenant_id: str
    name: str
    sector: str


class User(BaseModel):
    user_id: str
    email: str
    display_name: str
    tenant_id: str
    role: Role


class Persona(BaseModel):
    """Public representation of a seeded user shown on the login picker."""

    user_id: str
    display_name: str
    email: str
    role: Role
    tenant_id: str
    tenant_name: str


class LoginRequest(BaseModel):
    user_id: str


class LoginReply(BaseModel):
    token: str
    user: User
    tenant: Tenant
    permissions: List[str]


class MeReply(BaseModel):
    user: User
    tenant: Tenant
    permissions: List[str]


class SwitchTenantRequest(BaseModel):
    tenant_id: str


ApprovalStatus = Literal["pending", "approved", "rejected", "auto_approved"]
ApprovalKind = Literal[
    "po_create",
    "award_single_source",
    "quote_above_budget",
    "variation_order",
    "vendor_onboarding",
]


class ApprovalRule(BaseModel):
    kind: ApprovalKind
    condition_summary: str
    required_role: Role
    auto_below_value_usd: Optional[float] = None


class Approval(BaseModel):
    approval_id: str
    tenant_id: str
    kind: ApprovalKind
    title: str
    summary: str
    payload: dict
    requested_by: str
    requested_by_name: str
    requested_at: datetime
    required_role: Role
    status: ApprovalStatus
    decided_by: Optional[str] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    result_ref: Optional[str] = None  # e.g. PO number after approval commits


class DecideApprovalRequest(BaseModel):
    note: Optional[str] = None


class GatedAwardReply(BaseModel):
    status: Literal["applied", "pending_approval"]
    award: Optional[Award] = None
    po: Optional[SourcingPO] = None
    approval: Optional[Approval] = None


class GatedQuoteReply(BaseModel):
    status: Literal["applied", "pending_approval"]
    quote: Optional[Quote] = None
    approval: Optional[Approval] = None


class GatedVendorReply(BaseModel):
    status: Literal["applied", "pending_approval"]
    scorecard: Optional[VendorScorecard] = None
    approval: Optional[Approval] = None


class ToolCallRecord(BaseModel):
    tool: str
    input: dict
    output_summary: str  # short human-readable summary shown inline
    # Either a dict or a list of dicts; kept loose on purpose so the UI can
    # render any tool's structured output with a generic JSON viewer.
    output_preview: Optional[object] = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatRequest(BaseModel):
    message: str
    history: List[ChatTurn] = Field(default_factory=list)
    project_id: Optional[str] = None
    page: Optional[str] = None  # current frontend route, for context-aware answers


class ChatReply(BaseModel):
    reply: str
    tool_calls: List[ToolCallRecord]
    persona: AgentPersona
    source: Literal["grok", "claude", "openai", "deterministic"]
    generated_at: datetime


# --- SAP CPI Integration -----------------------------------------------------


SapMode = Literal["mock", "live", "disabled"]
SapEventKind = Literal[
    "pr_released",
    "pr_rejected",
    "po_released",
    "po_blocked",
    "gr_posted",
    "ir_posted",
    "po_closed",
]


class SapHealth(BaseModel):
    mode: SapMode
    base_url: Optional[str] = None
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error: Optional[str] = None
    token_valid_until: Optional[datetime] = None
    submissions_total: int = 0
    submissions_failed: int = 0
    events_received: int = 0


class SapSubmitReply(BaseModel):
    """Returned by /api/prs/{n}/submit-to-sap and /api/sourcing-pos/{n}/submit-to-sap."""

    ok: bool
    pr_no: Optional[str] = None
    po_no: Optional[str] = None
    sap_pr_no: Optional[str] = None
    sap_po_no: Optional[str] = None
    sap_status: SapStatus
    sap_error: Optional[str] = None
    submitted_at: datetime


class SapEvent(BaseModel):
    """Inbound webhook payload from CPI when SAP raises a status change."""

    kind: SapEventKind
    sap_doc_no: str  # SAP PR or PO number
    ct_ref: Optional[str] = None  # Control Tower's PR/PO number (BEDNR)
    new_status: Optional[str] = None
    quantity: Optional[float] = None  # for GR events
    value_usd: Optional[float] = None  # for IR events
    occurred_at: datetime
    raw: Optional[dict] = None  # full SAP payload for audit


class SapEventReply(BaseModel):
    accepted: bool
    matched_ct_ref: Optional[str] = None
    applied_to: Optional[str] = None  # "PR" or "PO"
    note: Optional[str] = None
