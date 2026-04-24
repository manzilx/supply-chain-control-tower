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
    name: str
    client: str
    site: str
    sector: str = "Industrial EPC"
    currency: str = "USD"
    start_date: date
    milestones: List[Milestone] = Field(default_factory=list)


class BOMItem(BaseModel):
    bom_item_id: str
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


# --- M3: Sourcing (PR → RFQ → Quote → Award → PO) ----------------------------


PRStatus = Literal["draft", "rfq_issued", "quoted", "awarded", "po_created", "cancelled"]
RFQStatus = Literal["open", "quotes_received", "evaluated", "awarded", "cancelled"]
SourcingStrategy = Literal["single_source", "multi_source", "rate_contract", "emergency_buy"]
Incoterm = Literal["EXW", "FCA", "FOB", "CIF", "CIP", "DAP", "DDP"]


class PurchaseRequisition(BaseModel):
    pr_no: str
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


class RFQ(BaseModel):
    rfq_no: str
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


class Award(BaseModel):
    award_id: str
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


class WeeklyPlan(BaseModel):
    generated_at: datetime
    week_of: date
    headline: str
    kpi_snapshot: List["KpiSnapshot"]
    items: List[WeeklyPlanItem]
    assumptions: List[str]


class KpiSnapshot(BaseModel):
    label: str
    value: str
    tone: Literal["neutral", "good", "warn", "bad"] = "neutral"


WeeklyPlan.model_rebuild()


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


class ChatReply(BaseModel):
    reply: str
    tool_calls: List[ToolCallRecord]
    persona: AgentPersona
    source: Literal["claude", "openai", "deterministic"]
    generated_at: datetime
