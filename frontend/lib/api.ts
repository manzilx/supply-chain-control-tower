import type {
  AddShipmentEventRequest,
  AgentRequest,
  AgentResponse,
  Award,
  AwardRFQRequest,
  BOMItem,
  BomUploadResult,
  CategoryConcentration,
  ChatReply,
  ChatRequest,
  CommercialLine,
  CommercialSummary,
  CreatePRRequest,
  CreateQuoteRequest,
  CreateRFQRequest,
  DraftFollowupRequest,
  ExpediteItem,
  ExpediteQueue,
  FollowupEmail,
  LogisticsQueue,
  ModeRecommendation,
  ProcurementPlan,
  Project,
  PurchaseRequisition,
  Quote,
  QuoteComparison,
  RFQ,
  Shipment,
  ShipmentEvent,
  SimulationRequest,
  SimulationResult,
  SourcingPO,
  SourcingTimeline,
  VendorScorecard,
  VendorSummary,
  WeeklyPlan,
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8010";

export async function fetchDemoScenario(): Promise<AgentRequest> {
  const response = await fetch(`${API_BASE}/api/demo`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Unable to load the demo scenario.");
  }
  return response.json();
}

export async function analyzeScenario(payload: AgentRequest): Promise<AgentResponse> {
  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Agent analysis failed.");
  }

  return response.json();
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg || `GET ${path} failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export function fetchProjects(): Promise<Project[]> {
  return getJson<Project[]>("/api/projects");
}

export function fetchProject(id: string): Promise<Project> {
  return getJson<Project>(`/api/projects/${encodeURIComponent(id)}`);
}

export function fetchBom(id: string): Promise<BOMItem[]> {
  return getJson<BOMItem[]>(`/api/projects/${encodeURIComponent(id)}/bom`);
}

export function fetchProcurementPlan(id: string): Promise<ProcurementPlan> {
  return getJson<ProcurementPlan>(
    `/api/projects/${encodeURIComponent(id)}/procurement-plan`,
  );
}

export async function uploadBomCsv(id: string, file: File): Promise<BomUploadResult> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(
    `${API_BASE}/api/projects/${encodeURIComponent(id)}/bom/upload`,
    { method: "POST", body },
  );
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg || "BOM upload failed");
  }
  return res.json();
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg || `POST ${path} failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

// PRs
export function fetchPrs(): Promise<PurchaseRequisition[]> {
  return getJson("/api/prs");
}
export function fetchPr(prNo: string): Promise<PurchaseRequisition> {
  return getJson(`/api/prs/${encodeURIComponent(prNo)}`);
}
export function createPr(req: CreatePRRequest): Promise<PurchaseRequisition> {
  return postJson("/api/prs", req);
}
export function fetchSuggestedVendors(prNo: string): Promise<string[]> {
  return getJson(`/api/prs/${encodeURIComponent(prNo)}/suggested-vendors`);
}

// RFQs
export function fetchRfqs(): Promise<RFQ[]> {
  return getJson("/api/rfqs");
}
export function fetchRfq(rfqNo: string): Promise<RFQ> {
  return getJson(`/api/rfqs/${encodeURIComponent(rfqNo)}`);
}
export function issueRfq(req: CreateRFQRequest): Promise<RFQ> {
  return postJson("/api/rfqs", req);
}
export function fetchQuotes(rfqNo: string): Promise<Quote[]> {
  return getJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/quotes`);
}
export function addQuote(rfqNo: string, req: CreateQuoteRequest): Promise<Quote> {
  return postJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/quotes`, req);
}
export function fetchQuoteComparison(rfqNo: string): Promise<QuoteComparison> {
  return getJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/compare`);
}
export function awardRfq(rfqNo: string, req: AwardRFQRequest): Promise<Award> {
  return postJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/award`, req);
}

// Awards / Sourcing POs
export function fetchAwards(): Promise<Award[]> {
  return getJson("/api/awards");
}
export function fetchSourcingPos(): Promise<SourcingPO[]> {
  return getJson("/api/sourcing-pos");
}
export function fetchSourcingPo(poNo: string): Promise<SourcingPO> {
  return getJson(`/api/sourcing-pos/${encodeURIComponent(poNo)}`);
}
export function fetchSourcingTimeline(poNo: string): Promise<SourcingTimeline> {
  return getJson(`/api/sourcing-pos/${encodeURIComponent(poNo)}/timeline`);
}

// M4: Vendor intelligence
export function fetchVendorIntel(): Promise<VendorSummary[]> {
  return getJson("/api/vendors/intel");
}
export function fetchVendorScorecard(name: string): Promise<VendorScorecard> {
  return getJson(`/api/vendors/intel/${encodeURIComponent(name)}`);
}
export function fetchVendorConcentration(): Promise<CategoryConcentration[]> {
  return getJson("/api/vendors/concentration");
}

// M4: Expediting
export function fetchExpediteQueue(): Promise<ExpediteQueue> {
  return getJson("/api/expediting/queue");
}
export function fetchExpediteItem(poNumber: string): Promise<ExpediteItem> {
  return getJson(`/api/expediting/queue/${encodeURIComponent(poNumber)}`);
}
export function draftFollowupEmail(
  poNumber: string,
  req: DraftFollowupRequest,
): Promise<FollowupEmail> {
  return postJson(`/api/expediting/${encodeURIComponent(poNumber)}/draft-followup`, req);
}

// M5: Logistics
export function fetchLogisticsQueue(): Promise<LogisticsQueue> {
  return getJson("/api/logistics/shipments");
}
export function fetchShipment(poRef: string): Promise<Shipment> {
  return getJson(`/api/logistics/shipments/${encodeURIComponent(poRef)}`);
}
export function addShipmentEvent(
  poRef: string,
  req: AddShipmentEventRequest,
): Promise<ShipmentEvent> {
  return postJson(`/api/logistics/shipments/${encodeURIComponent(poRef)}/events`, req);
}
export function fetchModeRecommendation(poRef: string): Promise<ModeRecommendation> {
  return getJson(`/api/logistics/shipments/${encodeURIComponent(poRef)}/recommend-mode`);
}

// M5: Commercial
export function fetchCommercialSummary(): Promise<CommercialSummary> {
  return getJson("/api/commercial/summary");
}
export function fetchProjectCommercials(projectId: string): Promise<CommercialLine[]> {
  return getJson(`/api/commercial/projects/${encodeURIComponent(projectId)}`);
}

// M5: Simulations
export function runSimulation(req: SimulationRequest): Promise<SimulationResult> {
  return postJson("/api/risk/simulate", req);
}

// M6: AI Command Center
export function fetchWeeklyPlan(): Promise<WeeklyPlan> {
  return getJson("/api/weekly-plan");
}
export function sendChat(req: ChatRequest): Promise<ChatReply> {
  return postJson("/api/chat", req);
}
