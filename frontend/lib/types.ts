export type Severity = "low" | "medium" | "high" | "critical";
export type Criticality = "low" | "medium" | "high" | "mission-critical";
export type PurchaseOrderStatus = "planned" | "released" | "in_transit" | "delayed" | "received";

export type CompanyProfile = {
  company_name: string;
  sector: string;
  active_projects: number;
  planner_horizon_days: number;
  target_service_level_pct: number;
};

export type SupplierRecord = {
  name: string;
  category: string;
  country: string;
  lead_time_days: number;
  on_time_delivery_pct: number;
  quality_ppm: number;
  annual_spend_usd: number;
  approved_alternatives: number;
  risk_flags: string[];
};

export type InventoryItem = {
  sku: string;
  description: string;
  category: string;
  supplier_name: string;
  on_hand_qty: number;
  reorder_point_qty: number;
  safety_stock_qty: number;
  daily_demand_qty: number;
  lead_time_days: number;
  unit_cost_usd: number;
  criticality: Criticality;
};

export type PurchaseOrder = {
  po_number: string;
  supplier_name: string;
  sku: string;
  quantity: number;
  due_in_days: number;
  value_usd: number;
  status: PurchaseOrderStatus;
  expedite_possible: boolean;
};

export type DemandSignal = {
  sku: string;
  next_30_day_demand_qty: number;
  next_90_day_demand_qty: number;
  confidence_pct: number;
};

export type Incident = {
  title: string;
  severity: Severity;
  description: string;
  supplier_name?: string | null;
  sku?: string | null;
  days_open: number;
};

export type AgentRequest = {
  company: CompanyProfile;
  suppliers: SupplierRecord[];
  inventory: InventoryItem[];
  purchase_orders: PurchaseOrder[];
  demand_signals: DemandSignal[];
  incidents: Incident[];
  ask: string;
};

export type RiskRecord = {
  title: string;
  risk_type: string;
  severity: Severity;
  score: number;
  summary: string;
  supplier_name?: string | null;
  sku?: string | null;
  owner: string;
};

export type RecommendedAction = {
  title: string;
  priority: "P1" | "P2" | "P3";
  owner: string;
  due_in_days: number;
  rationale: string;
};

export type WatchMetric = {
  label: string;
  value: string;
  direction: "up" | "down" | "steady";
};

export type AgentResponse = {
  generated_at: string;
  overall_risk_score: number;
  executive_summary: string;
  ai_assistant_response: string;
  top_risks: RiskRecord[];
  recommended_actions: RecommendedAction[];
  watch_metrics: WatchMetric[];
  assumptions: string[];
};

export type ScenarioDraft = {
  companyName: string;
  sector: string;
  activeProjects: string;
  horizonDays: string;
  serviceLevel: string;
  ask: string;
  suppliersJson: string;
  inventoryJson: string;
  purchaseOrdersJson: string;
  demandSignalsJson: string;
  incidentsJson: string;
};

// --- M2: Projects, BOM, Procurement Plan ------------------------------------

export type DocumentKind =
  | "drawing"
  | "spec"
  | "GA"
  | "QAP"
  | "ITP"
  | "MDR"
  | "test_cert"
  | "MOM";

export type BomStatus =
  | "spec_missing"
  | "planned"
  | "requisitioned"
  | "ordered"
  | "delivered";

export type MilestonePhase =
  | "engineering"
  | "procurement"
  | "fabrication"
  | "delivery"
  | "installation"
  | "commissioning";

export type Milestone = {
  code: string;
  name: string;
  phase: MilestonePhase;
  required_on_site_date: string;
};

export type Project = {
  project_id: string;
  name: string;
  client: string;
  site: string;
  sector: string;
  currency: string;
  start_date: string;
  milestones: Milestone[];
};

export type BOMItem = {
  bom_item_id: string;
  project_id: string;
  parent_item_id?: string | null;
  level: number;
  code: string;
  description: string;
  category?: string | null;
  quantity: number;
  uom: string;
  unit_cost_usd?: number | null;
  supplier_name?: string | null;
  spec_doc_id?: string | null;
  drawing_id?: string | null;
  long_lead_days?: number | null;
  planned_need_date?: string | null;
  milestone_code?: string | null;
  status: BomStatus;
};

export type ProcurementPackage = {
  package_id: string;
  project_id: string;
  milestone_code: string;
  milestone_name: string;
  required_on_site_date: string;
  bom_item_ids: string[];
  item_count: number;
  total_value_usd: number;
  earliest_need_date?: string | null;
  long_lead_count: number;
  missing_spec_count: number;
};

export type PlanFlag = {
  bom_item_id: string;
  code: string;
  description: string;
  reason: string;
  severity: Severity;
  milestone_code?: string | null;
  days_until_need?: number | null;
  long_lead_days?: number | null;
};

export type PlanSummary = {
  bom_item_count: number;
  packages_count: number;
  long_lead_count: number;
  missing_spec_count: number;
  total_value_usd: number;
  earliest_need_date?: string | null;
  latest_need_date?: string | null;
};

export type ProcurementPlan = {
  project_id: string;
  project_name: string;
  generated_at: string;
  summary: PlanSummary;
  packages: ProcurementPackage[];
  long_lead_items: PlanFlag[];
  missing_spec_items: PlanFlag[];
  assumptions: string[];
};

export type BomUploadResult = {
  project_id: string;
  rows_parsed: number;
  rows_accepted: number;
  rows_rejected: number;
  errors: string[];
  bom_items: BOMItem[];
};

// --- M3: Sourcing -----------------------------------------------------------

export type PRStatus =
  | "draft"
  | "rfq_issued"
  | "quoted"
  | "awarded"
  | "po_created"
  | "cancelled";

export type RFQStatus =
  | "open"
  | "quotes_received"
  | "evaluated"
  | "awarded"
  | "cancelled";

export type SourcingStrategy =
  | "single_source"
  | "multi_source"
  | "rate_contract"
  | "emergency_buy";

export type Incoterm = "EXW" | "FCA" | "FOB" | "CIF" | "CIP" | "DAP" | "DDP";

export type PurchaseRequisition = {
  pr_no: string;
  project_id: string;
  bom_item_id?: string | null;
  code: string;
  description: string;
  quantity: number;
  uom: string;
  need_by?: string | null;
  milestone_code?: string | null;
  budget_value_usd?: number | null;
  buyer: string;
  strategy: SourcingStrategy;
  status: PRStatus;
  rfq_no?: string | null;
  award_id?: string | null;
  po_no?: string | null;
  created_at: string;
};

export type RFQ = {
  rfq_no: string;
  pr_no: string;
  project_id: string;
  code: string;
  description: string;
  quantity: number;
  uom: string;
  vendors: string[];
  issued_at: string;
  due_at: string;
  status: RFQStatus;
  notes?: string | null;
};

export type Quote = {
  quote_id: string;
  rfq_no: string;
  vendor: string;
  unit_price_usd: number;
  quantity: number;
  total_usd: number;
  lead_time_days: number;
  incoterm: Incoterm;
  validity_days: number;
  received_at: string;
  notes?: string | null;
};

export type QuoteEvaluation = {
  vendor: string;
  quote_id: string;
  total_usd: number;
  lead_time_days: number;
  price_index: number;
  lead_time_index: number;
  otd_pct?: number | null;
  quality_ppm?: number | null;
  reliability_score: number;
  composite_score: number;
  rank: number;
};

export type QuoteComparison = {
  rfq_no: string;
  generated_at: string;
  evaluations: QuoteEvaluation[];
  recommended_vendor?: string | null;
  recommendation_rationale?: string | null;
  notes: string[];
};

export type Award = {
  award_id: string;
  rfq_no: string;
  pr_no: string;
  vendor: string;
  quote_id: string;
  awarded_value_usd: number;
  rationale: string;
  awarded_at: string;
  awarded_by: string;
};

export type SourcingPO = {
  po_no: string;
  pr_no: string;
  rfq_no: string;
  award_id: string;
  project_id: string;
  vendor: string;
  code: string;
  description: string;
  quantity: number;
  uom: string;
  unit_price_usd: number;
  value_usd: number;
  incoterm: Incoterm;
  need_by?: string | null;
  lead_time_days: number;
  created_at: string;
  status: "draft" | "released" | "in_transit" | "delivered";
};

export type SourcingTimelineEvent = {
  kind: "pr_created" | "rfq_issued" | "quote_received" | "evaluated" | "awarded" | "po_created";
  at: string;
  ref_id: string;
  title: string;
  detail: string;
};

export type SourcingTimeline = {
  po_no: string;
  events: SourcingTimelineEvent[];
};

export type CreatePRRequest = {
  project_id: string;
  bom_item_id?: string | null;
  code?: string | null;
  description?: string | null;
  quantity?: number | null;
  uom?: string | null;
  need_by?: string | null;
  milestone_code?: string | null;
  budget_value_usd?: number | null;
  buyer?: string | null;
  strategy?: SourcingStrategy | null;
};

export type CreateRFQRequest = {
  pr_no: string;
  vendors: string[];
  due_in_days?: number;
  notes?: string | null;
};

export type CreateQuoteRequest = {
  vendor: string;
  unit_price_usd: number;
  lead_time_days: number;
  quantity?: number | null;
  incoterm?: Incoterm;
  validity_days?: number;
  notes?: string | null;
};

export type AwardRFQRequest = {
  quote_id: string;
  rationale?: string | null;
  awarded_by?: string | null;
};

// --- M4: Vendor Intelligence + Expediting ----------------------------------

export type ScoreDimension =
  | "delivery"
  | "quality"
  | "price"
  | "responsiveness"
  | "claims"
  | "risk";

export type Grade = "A" | "B" | "C" | "D" | "F";

export type ScorecardComponent = {
  dimension: ScoreDimension;
  score: number;
  grade: Grade;
  label: string;
  value: string;
  note: string;
};

export type VendorAlternate = {
  name: string;
  category: string;
  country: string;
  composite_score: number;
  lead_time_days: number;
  on_time_delivery_pct: number;
  reason: string;
};

export type VendorScorecard = {
  vendor: string;
  category: string;
  country: string;
  lead_time_days: number;
  annual_spend_usd: number;
  composite_score: number;
  composite_grade: Grade;
  components: ScorecardComponent[];
  flags: string[];
  single_source_exposure: boolean;
  concentration_pct: number;
  approved_alternatives: number;
  alternates: VendorAlternate[];
};

export type VendorSummary = {
  vendor: string;
  category: string;
  country: string;
  composite_score: number;
  composite_grade: Grade;
  annual_spend_usd: number;
  on_time_delivery_pct: number;
  quality_ppm: number;
  flags_count: number;
  single_source_exposure: boolean;
};

export type CategoryConcentration = {
  category: string;
  vendor_count: number;
  total_spend_usd: number;
  top_vendor: string;
  top_vendor_share_pct: number;
  single_source: boolean;
};

export type ExpediteUrgency = "ok" | "watch" | "nudge" | "escalate";
export type EmailTone = "standard" | "firm" | "urgent";

export type ExpediteItem = {
  po_number: string;
  supplier_name: string;
  sku?: string | null;
  description?: string | null;
  quantity: number;
  value_usd: number;
  due_in_days: number;
  status: string;
  predicted_slip_days: number;
  slip_probability_pct: number;
  urgency: ExpediteUrgency;
  reasons: string[];
  source: "scenario" | "sourcing";
  project_id?: string | null;
};

export type ExpediteSummary = {
  total: number;
  ok: number;
  watch: number;
  nudge: number;
  escalate: number;
  value_at_risk_usd: number;
};

export type ExpediteQueue = {
  generated_at: string;
  items: ExpediteItem[];
  summary: ExpediteSummary;
};

export type FollowupEmail = {
  po_number: string;
  vendor: string;
  tone: EmailTone;
  to_placeholder: string;
  subject: string;
  body: string;
  requested_documents: string[];
  generated_at: string;
};

export type DraftFollowupRequest = {
  tone?: EmailTone;
  request_documents?: boolean;
  extra_notes?: string | null;
};

// --- M5: Logistics + Commercial + Simulations -----------------------------

export type ShipmentStage =
  | "manufacturing"
  | "ready_to_dispatch"
  | "dispatched"
  | "in_transit"
  | "at_port"
  | "at_customs"
  | "last_mile"
  | "delivered";

export type FreightMode = "sea" | "air" | "road" | "rail" | "local";

export type ShipmentEvent = {
  event_id: string;
  po_ref: string;
  stage: ShipmentStage;
  at: string;
  location?: string | null;
  note?: string | null;
};

export type Shipment = {
  po_ref: string;
  source: "scenario" | "sourcing";
  vendor: string;
  code?: string | null;
  description?: string | null;
  origin_country?: string | null;
  destination_site?: string | null;
  value_usd: number;
  quantity: number;
  mode: FreightMode;
  current_stage: ShipmentStage;
  required_on_site?: string | null;
  estimated_arrival?: string | null;
  bottleneck?: string | null;
  slack_days?: number | null;
  events: ShipmentEvent[];
};

export type LogisticsSummary = {
  total: number;
  in_motion: number;
  at_bottleneck: number;
  delivered: number;
  value_in_motion_usd: number;
};

export type LogisticsQueue = {
  generated_at: string;
  shipments: Shipment[];
  summary: LogisticsSummary;
};

export type ModeRecommendation = {
  po_ref: string;
  current_mode: FreightMode;
  recommended_mode: FreightMode;
  transit_days_estimate: number;
  cost_multiplier: number;
  rationale: string;
  days_until_need?: number | null;
};

export type AddShipmentEventRequest = {
  stage: ShipmentStage;
  location?: string | null;
  note?: string | null;
};

export type CommercialLine = {
  ref_id: string;
  project_id: string;
  code: string;
  description: string;
  vendor?: string | null;
  budget_value_usd?: number | null;
  quoted_value_usd?: number | null;
  awarded_value_usd?: number | null;
  final_po_value_usd?: number | null;
  savings_usd: number;
  variance_pct: number;
  currency: string;
  state: "budget_only" | "quoted" | "awarded" | "delivered";
};

export type ProjectCommercialSummary = {
  project_id: string;
  project_name: string;
  line_count: number;
  total_budget_usd: number;
  total_quoted_usd: number;
  total_awarded_usd: number;
  total_savings_usd: number;
  savings_pct: number;
  variance_pct: number;
  over_budget_lines: number;
};

export type CommercialSummary = {
  generated_at: string;
  total_budget_usd: number;
  total_awarded_usd: number;
  total_savings_usd: number;
  savings_pct: number;
  projects: ProjectCommercialSummary[];
  top_savings: CommercialLine[];
  top_overruns: CommercialLine[];
};

export type SimulationScenario = "vendor_slip_2w" | "customs_hold" | "alt_vendor";

export type SimulationRequest = {
  scenario: SimulationScenario;
  target: string;
  alternate_vendor?: string | null;
  custom_slip_days?: number | null;
};

export type AffectedItem = {
  ref_id: string;
  code: string;
  description: string;
  impact: string;
  original_need_date?: string | null;
  new_expected_date?: string | null;
};

export type MilestoneImpact = {
  project_id: string;
  project_name: string;
  milestone_code: string;
  milestone_name: string;
  original_date: string;
  new_date: string;
  slip_days: number;
};

export type SimulationResult = {
  scenario: SimulationScenario;
  target: string;
  generated_at: string;
  headline: string;
  severity: Severity;
  cost_delta_usd: number;
  schedule_delta_days: number;
  affected_items: AffectedItem[];
  milestone_impacts: MilestoneImpact[];
  mitigations: string[];
  assumptions: string[];
};

// --- M6: AI Command Center ------------------------------------------------

export type AgentPersona =
  | "sourcing"
  | "expediting"
  | "vendor_risk"
  | "logistics"
  | "commercial"
  | "planning"
  | "reporting"
  | "general";

export type WeeklyCategory =
  | "sourcing"
  | "expediting"
  | "vendor_risk"
  | "logistics"
  | "commercial"
  | "planning";

export type KpiSnapshot = {
  label: string;
  value: string;
  tone: "neutral" | "good" | "warn" | "bad";
};

export type WeeklyPlanItem = {
  priority: "P1" | "P2" | "P3";
  category: WeeklyCategory;
  title: string;
  why: string;
  expected_impact: string;
  owner: string;
  due_in_days: number;
  confidence: number;
  supporting_refs: string[];
};

export type WeeklyPlan = {
  generated_at: string;
  week_of: string;
  headline: string;
  kpi_snapshot: KpiSnapshot[];
  items: WeeklyPlanItem[];
  assumptions: string[];
};

export type ToolCallRecord = {
  tool: string;
  input: Record<string, unknown>;
  output_summary: string;
  output_preview?: unknown;
};

export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  tool_calls?: ToolCallRecord[];
  created_at?: string;
};

export type ChatRequest = {
  message: string;
  history?: ChatTurn[];
  project_id?: string | null;
};

export type ChatReply = {
  reply: string;
  tool_calls: ToolCallRecord[];
  persona: AgentPersona;
  source: "claude" | "openai" | "deterministic";
  generated_at: string;
};
