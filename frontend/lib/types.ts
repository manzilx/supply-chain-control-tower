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
  tenant_id: string;
  name: string;
  client: string;
  site: string;
  sector: string;
  currency: string;
  start_date: string;
  milestones: Milestone[];
};

export type AlertSeverity = "critical" | "high" | "medium" | "low" | "info";

export type Alert = {
  alert_id: string;
  severity: AlertSeverity;
  category: string;
  title: string;
  detail: string;
  href: string;
};

export type AlertFeed = {
  generated_at: string;
  total: number;
  counts: Record<string, number>;
  alerts: Alert[];
};

export type PortfolioCounts = {
  projects: number;
  bom_lines: number;
  prs: number;
  rfqs: number;
  pos: number;
};

export type PortfolioCompletionBucket = { label: string; count: number };

export type PortfolioSpend = {
  total_budget_usd: number;
  total_committed_usd: number;
  total_awarded_usd: number;
  committed_pct: number;
  open_prs: number;
};

export type PortfolioScheduleItem = {
  project_id: string;
  project_name: string;
  milestone_code: string;
  milestone_name: string;
  required_on_site_date: string;
  days_until: number;
  completion_pct: number;
  at_risk: boolean;
};

export type PortfolioSchedule = {
  at_risk: PortfolioScheduleItem[];
  upcoming_14d: PortfolioScheduleItem[];
};

export type PortfolioActivity = {
  at: string;
  action: string;
  entity_kind: string;
  subject: string;
  summary: string;
  project_id?: string | null;
};

export type PortfolioSummary = {
  generated_at: string;
  counts: PortfolioCounts;
  average_completion_pct: number;
  completion_buckets: PortfolioCompletionBucket[];
  spend: PortfolioSpend;
  schedule: PortfolioSchedule;
  activity: PortfolioActivity[];
};

export type SearchKind = "project" | "bom" | "vendor" | "pr" | "po";

export type SearchIndexItem = {
  kind: SearchKind;
  id: string;
  title: string;
  subtitle?: string | null;
  href: string;
  project_id?: string | null;
  tags: string[];
};

export type SearchIndex = {
  generated_at: string;
  items: SearchIndexItem[];
};

export type ProjectProgress = {
  project_id: string;
  completion_pct: number;
  milestones_pct: number;
  bom_delivered_pct: number;
  spend_committed_pct: number;
  milestones_passed: number;
  milestones_total: number;
  bom_delivered: number;
  bom_total: number;
  committed_value_usd: number;
  budget_value_usd: number;
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

export type SapStatus = "draft" | "submitting" | "synced" | "failed";

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
  // SAP CPI
  sap_pr_no?: string | null;
  sap_status?: SapStatus;
  sap_last_synced_at?: string | null;
  sap_error?: string | null;
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

// --- Technical Bid Evaluation (TBE) -------------------------------------

export type ComplianceLevel =
  | "full" | "partial" | "deviation" | "non_compliant" | "not_assessed";

export type CriterionCategory =
  | "spec_compliance" | "scope_of_supply" | "materials" | "performance"
  | "quality" | "documentation" | "warranty" | "spares_service"
  | "delivery_terms" | "experience" | "commercial_terms";

export type TechnicalCriterion = {
  criterion_id: string;
  name: string;
  description: string;
  category: CriterionCategory;
  weight: number;
  mandatory: boolean;
};

export type CriterionScore = {
  criterion_id: string;
  score: number;
  compliance: ComplianceLevel;
  note: string;
  deviation_text?: string | null;
};

export type TechnicalEvaluation = {
  rfq_no: string;
  quote_id: string;
  vendor: string;
  criteria_scores: CriterionScore[];
  technical_score: number;
  technical_grade: "A" | "B" | "C" | "D" | "F";
  disqualified: boolean;
  disqualification_reason?: string | null;
  notes: string;
  source: "manual" | "grok" | "deterministic";
  evaluated_by: string;
  evaluated_at: string;
};

export type CombinedEvaluation = {
  vendor: string;
  quote_id: string;
  commercial_score: number;
  technical_score: number;
  combined_score: number;
  commercial_rank: number;
  technical_rank: number;
  combined_rank: number;
  deviations_count: number;
  disqualified: boolean;
  notes: string[];
};

export type TBE = {
  rfq_no: string;
  generated_at: string;
  criteria: TechnicalCriterion[];
  technical_evaluations: TechnicalEvaluation[];
  commercial?: QuoteComparison | null;
  combined: CombinedEvaluation[];
  commercial_weight: number;
  technical_weight: number;
  recommended_vendor?: string | null;
  recommendation_rationale?: string | null;
  notes: string[];
};

// --- Audit Trail --------------------------------------------------------

export type AuditEntityKind =
  | "bom_item" | "project" | "pr" | "rfq" | "quote" | "award" | "po"
  | "shipment" | "shipment_event" | "technical_evaluation" | "sap_event"
  | "vendor" | "spec" | "approval" | "ai_brief" | "system";

export type AuditAction =
  | "created" | "updated" | "deleted"
  | "uploaded" | "issued" | "received" | "evaluated" | "compared"
  | "awarded" | "po_drafted" | "submitted_to_sap" | "sap_status_changed"
  | "stage_advanced" | "gr_posted" | "ir_posted" | "delivered"
  | "approved" | "rejected" | "exported" | "ai_generated";

export type AuditSource = "ui" | "api" | "sap_webhook" | "ai" | "scheduled_job" | "csv_upload" | "system";

export type AuditEvent = {
  event_id: string;
  occurred_at: string;
  actor: string;
  action: AuditAction;
  entity_kind: AuditEntityKind;
  entity_id: string;
  subject: string;
  summary: string;
  source: AuditSource;
  tenant_id?: string;
  bom_item_id?: string | null;
  bom_code?: string | null;
  project_id?: string | null;
  pr_no?: string | null;
  rfq_no?: string | null;
  quote_id?: string | null;
  award_id?: string | null;
  po_no?: string | null;
  vendor?: string | null;
  sap_doc_no?: string | null;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
};

export type PivotCount = {
  key: string;
  label: string;
  event_count: number;
  last_at?: string | null;
  description?: string | null;
  project_id?: string | null;
  category?: string | null;
  status?: string | null;
  value_usd?: number | null;
  related_pos: number;
  related_rfqs: number;
  related_vendors: number;
};

export type AuditPage = {
  events: AuditEvent[];
  total: number;
  has_more: boolean;
  next_offset?: number | null;
};

export type TraceStage = {
  stage:
    | "bom_item" | "spec" | "pr" | "rfq" | "quotes" | "technical_eval"
    | "award" | "po" | "sap" | "site_grn" | "shipment" | "delivery" | "invoice";
  label: string;
  entity_id?: string | null;
  status?: string | null;
  occurred_at?: string | null;
  actor?: string | null;
  detail?: string | null;
  payload?: Record<string, unknown> | null;
  children: string[];
  complete: boolean;
};

export type TraceabilityChain = {
  root_kind: AuditEntityKind;
  root_id: string;
  project_id?: string | null;
  stages: TraceStage[];
  generated_at: string;
  events_count: number;
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
  // SAP CPI
  sap_po_no?: string | null;
  sap_status?: SapStatus;
  sap_last_synced_at?: string | null;
  sap_error?: string | null;
  sap_gr_qty?: number | null;
  sap_ir_value_usd?: number | null;
};

// --- SAP CPI integration shapes -----------------------------------------

export type SapMode = "mock" | "live" | "disabled";

export type SapHealth = {
  mode: SapMode;
  base_url?: string | null;
  last_success_at?: string | null;
  last_error_at?: string | null;
  last_error?: string | null;
  token_valid_until?: string | null;
  submissions_total: number;
  submissions_failed: number;
  events_received: number;
};

export type SapSubmitReply = {
  ok: boolean;
  pr_no?: string | null;
  po_no?: string | null;
  sap_pr_no?: string | null;
  sap_po_no?: string | null;
  sap_status: SapStatus;
  sap_error?: string | null;
  submitted_at: string;
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
  last_followup_at?: string | null;
  followup_count?: number;
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

export type LogFollowupRequest = {
  tone?: EmailTone | null;
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
  narrative?: string | null;  // LLM-synthesized executive narrative
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
  href?: string | null;
  primary_action?: string | null;
};

export type WeeklyPlan = {
  generated_at: string;
  week_of: string;
  headline: string;
  kpi_snapshot: KpiSnapshot[];
  items: WeeklyPlanItem[];
  assumptions: string[];
  synthesized_narrative?: string | null;
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

export type IngestSheetPreview = {
  sheet: string;
  entity?: "project" | "bom" | "supplier" | null;
  rows_total: number;
  rows_valid: number;
  mapped: Record<string, string>;
  unmapped: string[];
  errors: string[];
  sample: Record<string, unknown>[];
};

export type IngestPreviewReply = {
  staging_id: string;
  filename: string;
  sheets: IngestSheetPreview[];
  total_valid: number;
  total_rows: number;
};

export type IngestCommitReply = {
  created: { projects: number; bom_items: number; suppliers: number };
  errors: string[];
  refs: string[];
};

export type AiStatus = {
  enabled: boolean;
  provider: string;
  model?: string | null;
  base_url?: string | null;
  stats: {
    calls: number;
    errors: number;
    last_latency_ms?: number | null;
    last_at?: string | null;
  };
};

export type ChatRequest = {
  message: string;
  history?: ChatTurn[];
  project_id?: string | null;
  page?: string | null;
};

export type ChatReply = {
  reply: string;
  tool_calls: ToolCallRecord[];
  persona: AgentPersona;
  source: "grok" | "claude" | "openai" | "deterministic";
  generated_at: string;
};

// --- AI feature shapes (Bundles 1-4) -------------------------------------

export type AISource = "grok" | "deterministic";

export type VendorBriefing = {
  vendor: string;
  headline: string;
  body: string;
  watchlist: string[];
  generated_at: string;
  source: AISource;
};

export type RiskMitigationsReply = {
  risk_title: string;
  mitigations: string[];
  source: AISource;
  generated_at: string;
};

export type ExplainKind = "po" | "vendor" | "risk" | "project" | "rfq" | "pr";

export type ExplainReply = {
  kind: string;
  id: string;
  headline: string;
  body: string;
  bullets: string[];
  source: AISource;
  generated_at: string;
};

export type BOMAutofillSuggestion = {
  bom_item_id: string;
  code: string;
  description: string;
  current_category?: string | null;
  current_supplier?: string | null;
  suggested_category?: string | null;
  suggested_supplier?: string | null;
  reason: string;
};

export type BOMAutofillReply = {
  project_id: string;
  suggestions: BOMAutofillSuggestion[];
  source: AISource;
  generated_at: string;
};

export type SpecRequestReply = {
  bom_item_id: string;
  code: string;
  to_placeholder: string;
  subject: string;
  body: string;
  source: AISource;
  generated_at: string;
};

// --- M7: Auth + Tenants + Approvals --------------------------------------

export type Role =
  | "admin"
  | "procurement_head"
  | "buyer"
  | "expeditor"
  | "viewer"
  | "storekeeper";

export type Tenant = {
  tenant_id: string;
  name: string;
  sector: string;
};

export type User = {
  user_id: string;
  email: string;
  display_name: string;
  tenant_id: string;
  role: Role;
};

export type Persona = {
  user_id: string;
  display_name: string;
  email: string;
  role: Role;
  tenant_id: string;
  tenant_name: string;
};

export type LoginReply = {
  token: string;
  user: User;
  tenant: Tenant;
  permissions: string[];
};

export type MeReply = {
  user: User;
  tenant: Tenant;
  permissions: string[];
};

export type ApprovalStatus = "pending" | "approved" | "rejected" | "auto_approved";
export type ApprovalKind =
  | "po_create"
  | "award_single_source"
  | "quote_above_budget"
  | "variation_order"
  | "vendor_onboarding";

export type Approval = {
  approval_id: string;
  tenant_id: string;
  kind: ApprovalKind;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
  requested_by: string;
  requested_by_name: string;
  requested_at: string;
  required_role: Role;
  status: ApprovalStatus;
  decided_by?: string | null;
  decided_by_name?: string | null;
  decided_at?: string | null;
  decision_note?: string | null;
  result_ref?: string | null;
};

export type DecideApprovalRequest = {
  note?: string;
};

export type GatedAwardReply =
  | { status: "applied"; award: Award; po?: SourcingPO | null; approval?: null }
  | { status: "pending_approval"; approval: Approval; award?: null; po?: null };

export type GatedQuoteReply =
  | { status: "applied"; quote: Quote; approval?: null }
  | { status: "pending_approval"; approval: Approval; quote?: null };

export type GatedVendorReply =
  | { status: "applied"; scorecard: VendorScorecard; approval?: null }
  | { status: "pending_approval"; approval: Approval; scorecard?: null };

// --- Storemark: Site Store / GRN ---

export type SiteStoreOut = {
  store_id: string;
  tenant_id: string;
  project_id: string;
  name: string;
  location_note: string | null;
  active: boolean;
  created_at: string;
};

export type CreateStoreRequest = {
  project_id: string;
  name: string;
  location_note?: string | null;
};

export type StorePersonRole = "storekeeper" | "foreman";

export type CreateEnrolmentRequest = {
  store_id: string;
  person_name: string;
  person_role: StorePersonRole;
};

export type EnrolmentInviteOut = {
  code: string;
  store_id: string;
  person_name: string;
  person_role: StorePersonRole;
  expires_at: string;
};

export type CaptureDeviceOut = {
  device_id: string;
  person_name: string;
  person_role: StorePersonRole;
  store_id: string | null;
  project_id: string | null;
  enrolled_at: string;
  enrolled_by: string;
  last_seen_at: string | null;
  last_sequence_no: number;
  revoked_at: string | null;
};

export type MatchCandidate = {
  po_no: string;
  vendor: string;
  code: string;
  description: string;
  score: number;
  remaining_qty: number;
  uom: string;
};

export type GrnMatchStatus = "unmatched" | "auto" | "suggested" | "confirmed" | "no_po";

export type GrnLineOut = {
  grn_line_id: string;
  line_no: number;
  description_raw: string;
  code: string | null;
  uom_raw: string | null;
  uom: string | null;
  qty_challan: number | null;
  qty_received: number;
  qty_damaged: number;
  qty_rejected: number;
  batch_no: string | null;
  po_no: string | null;
  match_status: GrnMatchStatus;
  match_confidence: number | null;
  match_candidates: MatchCandidate[] | null;
  over_receipt: boolean;
};

export type GrnStatus =
  | "captured"
  | "extracting"
  | "matched"
  | "suggested"
  | "triage"
  | "confirmed"
  | "cancelled"
  | "superseded";

export type GrnSourceKind = "contractor" | "free_issue";
export type GrnExtractionStatus = "pending" | "running" | "done" | "failed" | "skipped";

export type GrnSummary = {
  grn_id: string;
  grn_no: string | null;
  status: GrnStatus;
  source_kind: GrnSourceKind;
  vendor_name: string | null;
  challan_no: string | null;
  store_id: string;
  line_count: number;
  observed_at: string;
  confirmed_at: string | null;
};

export type GrnDetail = {
  grn_id: string;
  grn_no: string | null;
  tenant_id: string;
  store_id: string;
  project_id: string;
  device_id: string;
  status: GrnStatus;
  source_kind: GrnSourceKind;
  challan_no: string | null;
  challan_date: string | null;
  vendor_name_raw: string | null;
  vendor_name: string | null;
  vehicle_no: string | null;
  remarks: string | null;
  photo_sha256: string;
  extraction_status: GrnExtractionStatus;
  extraction_model: string | null;
  observed_at: string;
  received_at: string;
  confirmed_at: string | null;
  confirmed_by: string | null;
  confirmed_via: string | null;
  created_at: string;
  lines: GrnLineOut[];
};

export type ConfirmLine = {
  line_no: number;
  po_no?: string | null;
  no_po?: boolean;
  qty_received: number;
  qty_damaged?: number;
  qty_rejected?: number;
  uom?: string | null;
  batch_no?: string | null;
};

export type ConfirmGrnRequest = {
  lines: ConfirmLine[];
};

export type ConfirmGrnReply = {
  grn_id: string;
  grn_no: string | null;
  status: GrnStatus;
  ledger_entries: number;
  pos_updated: string[];
  pos_delivered: string[];
};

export type StockBalance = {
  code: string;
  description: string;
  uom: string;
  store_id: string;
  contractor_qty: number;
  free_issue_qty: number;
  total_qty: number;
  last_movement_at: string;
};

export type LedgerEntryOut = {
  entry_id: string;
  store_id: string;
  code: string;
  description: string;
  uom: string;
  movement: string;
  qty_signed: number;
  source_kind: GrnSourceKind;
  ref_kind: string;
  ref_id: string;
  po_no: string | null;
  vendor: string | null;
  effective_at: string;
  entered_at: string;
  entered_by: string;
};

export type VendorOtdRow = {
  vendor: string;
  po_no: string;
  need_by: string | null;
  first_receipt_at: string | null;
  full_receipt_at: string | null;
  on_time: boolean | null;
};
