import type {
  AddShipmentEventRequest,
  AgentRequest,
  AgentResponse,
  Approval,
  Award,
  AwardRFQRequest,
  BOMItem,
  BomUploadResult,
  CaptureDeviceOut,
  CategoryConcentration,
  ChatReply,
  ChatRequest,
  CommercialLine,
  CommercialSummary,
  ConfirmGrnReply,
  ConfirmGrnRequest,
  CreateEnrolmentRequest,
  CreatePRRequest,
  CreateQuoteRequest,
  CreateRFQRequest,
  CreateStoreRequest,
  DecideApprovalRequest,
  DraftFollowupRequest,
  EnrolmentInviteOut,
  ExpediteItem,
  ExpediteQueue,
  FollowupEmail,
  LogFollowupRequest,
  GatedAwardReply,
  GatedQuoteReply,
  GatedVendorReply,
  GrnDetail,
  GrnSummary,
  LedgerEntryOut,
  LoginReply,
  LogisticsQueue,
  MeReply,
  ModeRecommendation,
  Persona,
  PortfolioSummary,
  ProcurementPlan,
  Project,
  ProjectProgress,
  AiStatus,
  AlertFeed,
  IngestCommitReply,
  IngestPreviewReply,
  SearchIndex,
  SiteStoreOut,
  StockBalance,
  SupplierRecord,
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
  Tenant,
  VendorScorecard,
  VendorSummary,
  WeeklyPlan,
} from "@/lib/types";
import { getTenantOverride, getToken, setToken } from "@/lib/token-store";

// Empty string = relative URLs (prod behind reverse proxy). Only fall back to
// the dev backend when NEXT_PUBLIC_API_BASE is genuinely unset (next dev).
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8010";

export class ApiError extends Error {
  status: number;
  body: string;
  constructor(status: number, message: string, body: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

/** Base fetch wrapper: auto-injects Authorization + tenant override. */
// Hard ceiling on any single JSON call. Generous enough never to false-abort a
// legit multi-turn AI request, but turns a truly hung/unreachable backend into
// a clean error toast instead of an infinite spinner. SSE streams use a
// separate first-byte connect timeout (see STREAM_CONNECT_TIMEOUT_MS).
const REQUEST_TIMEOUT_MS = 45000;
// Abort an SSE chat if the backend never sends the first byte within this window.
// Once bytes arrive the stream may run as long as the agent needs.
const STREAM_CONNECT_TIMEOUT_MS = 45000;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const override = getTenantOverride();
  if (override && !headers.has("X-Tenant-Override")) {
    headers.set("X-Tenant-Override", override);
  }

  // Only arm the timeout when the caller hasn't supplied its own signal.
  const controller = init.signal ? null : new AbortController();
  const timer = controller
    ? setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
    : null;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      ...init,
      headers,
      signal: init.signal ?? controller?.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, `${init.method ?? "GET"} ${path} timed out after ${REQUEST_TIMEOUT_MS / 1000}s`, "");
    }
    // Network-level failure (backend down, DNS, CORS) — give a usable message.
    throw new ApiError(0, `${init.method ?? "GET"} ${path} — network error`, "");
  } finally {
    if (timer) clearTimeout(timer);
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    // On auth failure (expired/invalid token), clear the session so the
    // AuthProvider's RequireAuth wrapper kicks us back to /login instead
    // of leaving raw "Token expired" JSON on every page.
    if (res.status === 401 && token) {
      setToken(null);
    }
    throw new ApiError(res.status, body || `${init.method ?? "GET"} ${path} failed (${res.status})`, body);
  }
  // 204 no content
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// --- Legacy risk-analyze endpoints (public) --------------------------------

export async function fetchDemoScenario(): Promise<AgentRequest> {
  return request<AgentRequest>("/api/demo");
}

export async function analyzeScenario(payload: AgentRequest): Promise<AgentResponse> {
  return postJson<AgentResponse>("/api/analyze", payload);
}

// --- Auth (no token required for login/personas) --------------------------

export async function fetchPersonas(): Promise<Persona[]> {
  return request<Persona[]>("/api/auth/personas");
}

export async function login(userId: string): Promise<LoginReply> {
  return postJson<LoginReply>("/api/auth/login", { user_id: userId });
}

export async function fetchMe(): Promise<MeReply> {
  return getJson<MeReply>("/api/auth/me");
}

export async function fetchTenants(): Promise<Tenant[]> {
  return getJson<Tenant[]>("/api/tenants");
}

// --- Projects / BOM -----------------------------------------------------------

export function fetchProjects(): Promise<Project[]> {
  return getJson<Project[]>("/api/projects");
}

export function fetchPortfolioSummary(): Promise<PortfolioSummary> {
  return getJson<PortfolioSummary>("/api/portfolio/summary");
}

export function fetchSearchIndex(): Promise<SearchIndex> {
  return getJson<SearchIndex>("/api/search/index");
}

export function fetchAlerts(): Promise<AlertFeed> {
  return getJson<AlertFeed>("/api/alerts");
}

export function fetchProjectsProgress(): Promise<ProjectProgress[]> {
  return getJson<ProjectProgress[]>("/api/projects/progress");
}

export function fetchProjectProgress(id: string): Promise<ProjectProgress> {
  return getJson<ProjectProgress>(`/api/projects/${encodeURIComponent(id)}/progress`);
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
  return request<BomUploadResult>(
    `/api/projects/${encodeURIComponent(id)}/bom/upload`,
    { method: "POST", body },
  );
}

export type BomItemPatch = {
  category?: string | null;
  supplier_name?: string | null;
};

export function updateBomItem(
  projectId: string,
  bomItemId: string,
  patch: BomItemPatch,
): Promise<BOMItem> {
  return patchJson<BOMItem>(
    `/api/projects/${encodeURIComponent(projectId)}/bom/${encodeURIComponent(bomItemId)}`,
    patch,
  );
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
export function addQuote(rfqNo: string, req: CreateQuoteRequest): Promise<GatedQuoteReply> {
  return postJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/quotes`, req);
}
export function fetchQuoteComparison(rfqNo: string): Promise<QuoteComparison> {
  return getJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/compare`);
}
export function awardRfq(rfqNo: string, req: AwardRFQRequest): Promise<GatedAwardReply> {
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
export function createVendor(supplier: SupplierRecord): Promise<GatedVendorReply> {
  return postJson<GatedVendorReply>("/api/vendors", supplier);
}
export function proposeVendorOnboarding(supplier: SupplierRecord): Promise<GatedVendorReply> {
  return postJson<GatedVendorReply>("/api/ai/propose-vendor", supplier);
}
export async function deleteVendor(name: string): Promise<void> {
  await request<void>(`/api/vendors/${encodeURIComponent(name)}`, { method: "DELETE" });
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
export function logFollowupSent(
  poNumber: string,
  req: LogFollowupRequest = {},
): Promise<ExpediteItem> {
  return postJson(`/api/expediting/${encodeURIComponent(poNumber)}/log-followup`, req);
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

/** SSE chat — live status/tool events while the agent works. */
export async function streamChat(
  req: ChatRequest,
  handlers: {
    onStatus?: (status: string) => void;
    onTool?: (tool: string) => void;
    onReply: (reply: ChatReply) => void;
  },
): Promise<void> {
  const path = "/api/chat/stream";
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const override = getTenantOverride();
  if (override) headers.set("X-Tenant-Override", override);

  const controller = new AbortController();
  let connectTimer: ReturnType<typeof setTimeout> | null = setTimeout(
    () => controller.abort(),
    STREAM_CONNECT_TIMEOUT_MS,
  );
  const clearConnectTimer = () => {
    if (connectTimer) {
      clearTimeout(connectTimer);
      connectTimer = null;
    }
  };

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      cache: "no-store",
      headers,
      body: JSON.stringify(req),
      signal: controller.signal,
    });
  } catch (err) {
    clearConnectTimer();
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        0,
        `POST ${path} timed out waiting for first byte after ${STREAM_CONNECT_TIMEOUT_MS / 1000}s`,
        "",
      );
    }
    throw new ApiError(0, `POST ${path} — network error`, "");
  }

  if (!res.ok) {
    clearConnectTimer();
    const body = await res.text().catch(() => "");
    if (res.status === 401 && token) {
      setToken(null);
    }
    throw new ApiError(res.status, body || `chat stream failed (${res.status})`, body);
  }
  if (!res.body) {
    clearConnectTimer();
    throw new ApiError(res.status, "chat stream failed (no body)", "");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let event = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      clearConnectTimer();
      buf += decoder.decode(value, { stream: true });
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trimEnd();
        buf = buf.slice(nl + 1);
        if (line.startsWith("event: ")) {
          event = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (event === "status") handlers.onStatus?.(data);
          else if (event === "tool") handlers.onTool?.(data);
          else if (event === "reply") handlers.onReply(JSON.parse(data) as ChatReply);
          else if (event === "error") throw new Error(data || "stream error");
        }
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        0,
        `POST ${path} timed out waiting for first byte after ${STREAM_CONNECT_TIMEOUT_MS / 1000}s`,
        "",
      );
    }
    throw err;
  } finally {
    clearConnectTimer();
  }
}

export function fetchAiStatus(): Promise<AiStatus> {
  return getJson<AiStatus>("/api/ai/status");
}

// --- Ingestion engine -------------------------------------------------------

export async function ingestPreview(file: File): Promise<IngestPreviewReply> {
  const body = new FormData();
  body.append("file", file);
  return request<IngestPreviewReply>("/api/ingest/preview", { method: "POST", body });
}

export function ingestCommit(
  stagingId: string,
  defaultProjectId?: string | null,
): Promise<IngestCommitReply> {
  return postJson<IngestCommitReply>("/api/ingest/commit", {
    staging_id: stagingId,
    default_project_id: defaultProjectId ?? null,
  });
}

// AI features — vendor briefing, risk mitigations, BOM autofill, spec request, explain
export function fetchVendorBriefing(name: string): Promise<import("@/lib/types").VendorBriefing> {
  return getJson(`/api/vendors/intel/${encodeURIComponent(name)}/briefing`);
}
export function fetchRiskMitigations(risk: import("@/lib/types").RiskRecord): Promise<import("@/lib/types").RiskMitigationsReply> {
  return postJson("/api/risks/mitigations", risk);
}
export function fetchBomAutofill(projectId: string): Promise<import("@/lib/types").BOMAutofillReply> {
  return postJson(`/api/projects/${encodeURIComponent(projectId)}/bom/autofill`, {});
}
export function fetchSpecRequest(projectId: string, bomItemId: string): Promise<import("@/lib/types").SpecRequestReply> {
  return postJson(`/api/projects/${encodeURIComponent(projectId)}/bom/${encodeURIComponent(bomItemId)}/spec-request`, {});
}
export function fetchExplain(kind: import("@/lib/types").ExplainKind, id: string): Promise<import("@/lib/types").ExplainReply> {
  return postJson("/api/explain", { kind, id });
}

// Audit Trail
export function fetchAudit(params: Record<string, string | number | undefined> = {}): Promise<import("@/lib/types").AuditPage> {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  });
  const qs = q.toString();
  return getJson(`/api/audit${qs ? "?" + qs : ""}`);
}
export function fetchAuditStats(): Promise<Record<string, unknown>> {
  return getJson("/api/audit/stats");
}
export function fetchEntityAudit(kind: string, eid: string): Promise<import("@/lib/types").AuditEvent[]> {
  return getJson(`/api/audit/entity/${encodeURIComponent(kind)}/${encodeURIComponent(eid)}`);
}
export function fetchTraceBom(bomItemId: string): Promise<import("@/lib/types").TraceabilityChain> {
  return getJson(`/api/audit/trace/bom/${encodeURIComponent(bomItemId)}`);
}
export function fetchTracePr(prNo: string): Promise<import("@/lib/types").TraceabilityChain> {
  return getJson(`/api/audit/trace/pr/${encodeURIComponent(prNo)}`);
}
export function fetchTracePo(poNo: string): Promise<import("@/lib/types").TraceabilityChain> {
  return getJson(`/api/audit/trace/po/${encodeURIComponent(poNo)}`);
}
export function fetchPivotMaterials(): Promise<import("@/lib/types").PivotCount[]> {
  return getJson("/api/audit/pivots/materials");
}
export function fetchPivotPos(): Promise<import("@/lib/types").PivotCount[]> {
  return getJson("/api/audit/pivots/pos");
}
export function fetchPivotVendors(): Promise<import("@/lib/types").PivotCount[]> {
  return getJson("/api/audit/pivots/vendors");
}
function auditCsvPath(params: Record<string, string | undefined> = {}): string {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v) q.set(k, v);
  });
  const qs = q.toString();
  return `/api/audit/export.csv${qs ? "?" + qs : ""}`;
}

/** Authenticated audit CSV download (blob + programmatic save). */
export async function downloadAuditCsv(
  params: Record<string, string | undefined> = {},
): Promise<void> {
  const path = auditCsvPath(params);
  const headers = new Headers();
  const token = getToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const override = getTenantOverride();
  if (override && !headers.has("X-Tenant-Override")) {
    headers.set("X-Tenant-Override", override);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, `GET ${path} timed out after ${REQUEST_TIMEOUT_MS / 1000}s`, "");
    }
    throw new ApiError(0, `GET ${path} — network error`, "");
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    if (res.status === 401 && token) {
      setToken(null);
    }
    throw new ApiError(res.status, body || `GET ${path} failed (${res.status})`, body);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "audit-export.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Technical Bid Evaluation
export function fetchCriteria(rfqNo: string): Promise<import("@/lib/types").TechnicalCriterion[]> {
  return getJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/criteria`);
}
export function setCriteria(rfqNo: string, criteria: import("@/lib/types").TechnicalCriterion[]): Promise<import("@/lib/types").TechnicalCriterion[]> {
  return postJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/criteria`, { criteria });
}
export function fetchTechnicalEvaluations(rfqNo: string): Promise<import("@/lib/types").TechnicalEvaluation[]> {
  return getJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/technical`);
}
export function setTechnicalEvaluation(
  rfqNo: string,
  quoteId: string,
  body: { criteria_scores: import("@/lib/types").CriterionScore[]; notes?: string; evaluated_by?: string },
): Promise<import("@/lib/types").TechnicalEvaluation> {
  return postJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/technical/${encodeURIComponent(quoteId)}`, body);
}
export function autoEvaluate(rfqNo: string): Promise<import("@/lib/types").TechnicalEvaluation[]> {
  return postJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/auto-evaluate`, {});
}
export function setTbeWeights(rfqNo: string, commercial: number, technical: number): Promise<{ commercial_weight: number; technical_weight: number }> {
  return postJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/weights`, { commercial_weight: commercial, technical_weight: technical });
}
export function fetchTbe(rfqNo: string): Promise<import("@/lib/types").TBE> {
  return getJson(`/api/rfqs/${encodeURIComponent(rfqNo)}/tbe`);
}

// SAP CPI integration
export function submitPrToSap(prNo: string): Promise<import("@/lib/types").SapSubmitReply> {
  return postJson(`/api/prs/${encodeURIComponent(prNo)}/submit-to-sap`, {});
}
export function submitPoToSap(poNo: string): Promise<import("@/lib/types").SapSubmitReply> {
  return postJson(`/api/sourcing-pos/${encodeURIComponent(poNo)}/submit-to-sap`, {});
}
export function fetchSapHealth(): Promise<import("@/lib/types").SapHealth> {
  return getJson("/api/integrations/sap/health");
}
export function resyncSap(): Promise<{ prs_reconciled: number; pos_reconciled: number }> {
  return postJson("/api/integrations/sap/resync", {});
}

// M7: Approvals
export function fetchApprovals(): Promise<Approval[]> {
  return getJson<Approval[]>("/api/approvals");
}
export function approveApproval(id: string, req: DecideApprovalRequest = {}): Promise<Approval> {
  return postJson<Approval>(`/api/approvals/${encodeURIComponent(id)}/approve`, req);
}
export function rejectApproval(id: string, req: DecideApprovalRequest = {}): Promise<Approval> {
  return postJson<Approval>(`/api/approvals/${encodeURIComponent(id)}/reject`, req);
}

// --- Storemark: Site Store / GRN ---

export function fetchStockBalances(): Promise<StockBalance[]> {
  return getJson<StockBalance[]>("/api/store/stock");
}
export function fetchCodeLedger(code: string, storeId?: string): Promise<LedgerEntryOut[]> {
  const q = new URLSearchParams();
  if (storeId) q.set("store_id", storeId);
  const qs = q.toString();
  return getJson<LedgerEntryOut[]>(`/api/store/stock/${encodeURIComponent(code)}/ledger${qs ? "?" + qs : ""}`);
}
export function fetchStoreGrns(
  params: { status?: string; triage?: boolean; store_id?: string } = {},
): Promise<GrnSummary[]> {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.triage !== undefined) q.set("triage", String(params.triage));
  if (params.store_id) q.set("store_id", params.store_id);
  const qs = q.toString();
  return getJson<GrnSummary[]>(`/api/store/grns${qs ? "?" + qs : ""}`);
}
export function fetchStoreGrn(grnId: string): Promise<GrnDetail> {
  return getJson<GrnDetail>(`/api/store/grns/${encodeURIComponent(grnId)}`);
}

/**
 * The GRN photo endpoint requires an Authorization header, so a plain <img src>
 * can't hit it directly — fetch the blob with the same auth-header logic as
 * the private `request()` helper, then hand back an object URL. Caller owns
 * the URL's lifetime and must revokeObjectURL it (e.g. on unmount / selection change).
 */
export async function fetchGrnPhotoObjectUrl(grnId: string): Promise<string> {
  const path = `/api/store/grns/${encodeURIComponent(grnId)}/photo`;
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const override = getTenantOverride();
  if (override) headers.set("X-Tenant-Override", override);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, `GET ${path} timed out after ${REQUEST_TIMEOUT_MS / 1000}s`, "");
    }
    throw new ApiError(0, `GET ${path} — network error`, "");
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    if (res.status === 401 && token) {
      setToken(null);
    }
    throw new ApiError(res.status, body || `GET ${path} failed (${res.status})`, body);
  }

  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export function confirmGrn(grnId: string, req: ConfirmGrnRequest): Promise<ConfirmGrnReply> {
  return postJson<ConfirmGrnReply>(`/api/store/grns/${encodeURIComponent(grnId)}/confirm`, req);
}
export function rejectGrn(grnId: string, reason: string): Promise<GrnDetail> {
  return postJson<GrnDetail>(`/api/store/grns/${encodeURIComponent(grnId)}/reject`, { reason });
}

export function fetchStores(): Promise<SiteStoreOut[]> {
  return getJson<SiteStoreOut[]>("/api/store/stores");
}
export function createStore(req: CreateStoreRequest): Promise<SiteStoreOut> {
  return postJson<SiteStoreOut>("/api/store/stores", req);
}

export function fetchFieldDevices(): Promise<CaptureDeviceOut[]> {
  return getJson<CaptureDeviceOut[]>("/api/field-admin/devices");
}
export function createEnrolment(req: CreateEnrolmentRequest): Promise<EnrolmentInviteOut> {
  return postJson<EnrolmentInviteOut>("/api/field-admin/enrolments", req);
}
export function revokeDevice(deviceId: string): Promise<CaptureDeviceOut> {
  return postJson<CaptureDeviceOut>(`/api/field-admin/devices/${encodeURIComponent(deviceId)}/revoke`, {});
}
