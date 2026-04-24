from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .ai_assist import generate_ai_brief
from .analytics import analyze_supply_chain
from .planning import (
    build_procurement_plan,
    get_bom,
    get_project,
    list_projects,
    upload_bom_csv,
)
from .sample_data import build_demo_request
from .schemas import (
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
)
from .sourcing import (
    add_quote,
    award_rfq,
    build_timeline,
    compare_quotes,
    create_pr,
    get_po,
    get_pr,
    get_quotes,
    get_rfq,
    issue_rfq,
    list_awards,
    list_pos,
    list_prs,
    list_rfqs,
    suggest_vendors,
)
from .vendor_intel import (
    get_vendor_scorecard,
    list_category_concentration,
    list_vendor_summaries,
)
from .expediting import (
    build_expedite_queue,
    draft_followup_email,
    get_expedite_item,
)
from .logistics import (
    add_event,
    get_shipment,
    list_shipments,
    recommend_mode,
)
from .commercial import (
    build_commercial_summary,
    get_project_commercials,
)
from .simulations import run_simulation
from .agent import dispatch as agent_dispatch
from .weekly_plan import build_weekly_plan


def _allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="Engineering Supply Chain Agent",
    version="0.1.0",
    description="API for an AI-assisted supply chain cockpit for engineering companies.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "Engineering Supply Chain Agent API",
        "frontend": "Run the React app in .start/frontend",
        "health": "/api/health",
    }


@app.get("/api/demo", response_model=AgentRequest)
async def demo_data() -> AgentRequest:
    return build_demo_request()


@app.post("/api/analyze", response_model=AgentResponse)
async def analyze(request: AgentRequest) -> AgentResponse:
    draft = analyze_supply_chain(request, ai_response="")
    ai_brief = generate_ai_brief(request, draft.top_risks)
    return analyze_supply_chain(request, ai_response=ai_brief)


# --- M2: Projects / BOM / Procurement Plan -----------------------------------


@app.get("/api/projects", response_model=list[Project])
async def api_list_projects() -> list[Project]:
    return list_projects()


@app.get("/api/projects/{project_id}", response_model=Project)
async def api_get_project(project_id: str) -> Project:
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.get("/api/projects/{project_id}/bom", response_model=list[BOMItem])
async def api_get_bom(project_id: str) -> list[BOMItem]:
    if not get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return get_bom(project_id)


@app.get("/api/projects/{project_id}/procurement-plan", response_model=ProcurementPlan)
async def api_procurement_plan(project_id: str) -> ProcurementPlan:
    plan = build_procurement_plan(project_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Project not found")
    return plan


@app.post("/api/projects/{project_id}/bom/upload", response_model=BomUploadResult)
async def api_upload_bom(project_id: str, file: UploadFile) -> BomUploadResult:
    if not get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded")
    return upload_bom_csv(project_id, text)


# --- M3: Sourcing (PR → RFQ → Quote → Award → PO) ----------------------------


@app.get("/api/prs", response_model=list[PurchaseRequisition])
async def api_list_prs() -> list[PurchaseRequisition]:
    return list_prs()


@app.post("/api/prs", response_model=PurchaseRequisition)
async def api_create_pr(request: CreatePRRequest) -> PurchaseRequisition:
    if not get_project(request.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return create_pr(request)


@app.get("/api/prs/{pr_no}", response_model=PurchaseRequisition)
async def api_get_pr(pr_no: str) -> PurchaseRequisition:
    pr = get_pr(pr_no)
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    return pr


@app.get("/api/prs/{pr_no}/suggested-vendors", response_model=list[str])
async def api_suggest_vendors(pr_no: str) -> list[str]:
    pr = get_pr(pr_no)
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    return suggest_vendors(pr.project_id, pr.bom_item_id)


@app.get("/api/rfqs", response_model=list[RFQ])
async def api_list_rfqs() -> list[RFQ]:
    return list_rfqs()


@app.post("/api/rfqs", response_model=RFQ)
async def api_issue_rfq(request: CreateRFQRequest) -> RFQ:
    if not request.vendors:
        raise HTTPException(status_code=400, detail="At least one vendor is required.")
    rfq = issue_rfq(request)
    if not rfq:
        raise HTTPException(status_code=404, detail="PR not found or already awarded")
    return rfq


@app.get("/api/rfqs/{rfq_no}", response_model=RFQ)
async def api_get_rfq(rfq_no: str) -> RFQ:
    rfq = get_rfq(rfq_no)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return rfq


@app.get("/api/rfqs/{rfq_no}/quotes", response_model=list[Quote])
async def api_get_quotes(rfq_no: str) -> list[Quote]:
    if not get_rfq(rfq_no):
        raise HTTPException(status_code=404, detail="RFQ not found")
    return get_quotes(rfq_no)


@app.post("/api/rfqs/{rfq_no}/quotes", response_model=Quote)
async def api_add_quote(rfq_no: str, request: CreateQuoteRequest) -> Quote:
    quote = add_quote(rfq_no, request)
    if not quote:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return quote


@app.get("/api/rfqs/{rfq_no}/compare", response_model=QuoteComparison)
async def api_compare_quotes(rfq_no: str) -> QuoteComparison:
    comparison = compare_quotes(rfq_no)
    if not comparison:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return comparison


@app.post("/api/rfqs/{rfq_no}/award", response_model=Award)
async def api_award_rfq(rfq_no: str, request: AwardRFQRequest) -> Award:
    award = award_rfq(rfq_no, request)
    if not award:
        raise HTTPException(status_code=404, detail="RFQ or quote not found")
    return award


@app.get("/api/awards", response_model=list[Award])
async def api_list_awards() -> list[Award]:
    return list_awards()


@app.get("/api/sourcing-pos", response_model=list[SourcingPO])
async def api_list_sourcing_pos() -> list[SourcingPO]:
    return list_pos()


@app.get("/api/sourcing-pos/{po_no}", response_model=SourcingPO)
async def api_get_sourcing_po(po_no: str) -> SourcingPO:
    po = get_po(po_no)
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    return po


@app.get("/api/sourcing-pos/{po_no}/timeline", response_model=SourcingTimeline)
async def api_get_sourcing_po_timeline(po_no: str) -> SourcingTimeline:
    timeline = build_timeline(po_no)
    if not timeline:
        raise HTTPException(status_code=404, detail="PO not found")
    return timeline


# --- M4: Vendor Intelligence + Expediting -----------------------------------


@app.get("/api/vendors/intel", response_model=list[VendorSummary])
async def api_list_vendor_intel() -> list[VendorSummary]:
    return list_vendor_summaries()


@app.get("/api/vendors/concentration", response_model=list[CategoryConcentration])
async def api_vendor_concentration() -> list[CategoryConcentration]:
    return list_category_concentration()


@app.get("/api/vendors/intel/{name}", response_model=VendorScorecard)
async def api_vendor_scorecard(name: str) -> VendorScorecard:
    scorecard = get_vendor_scorecard(name)
    if not scorecard:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return scorecard


@app.get("/api/expediting/queue", response_model=ExpediteQueue)
async def api_expediting_queue() -> ExpediteQueue:
    return build_expedite_queue()


@app.get("/api/expediting/queue/{po_number}", response_model=ExpediteItem)
async def api_expediting_item(po_number: str) -> ExpediteItem:
    item = get_expedite_item(po_number)
    if not item:
        raise HTTPException(status_code=404, detail="PO not found in expedite queue")
    return item


@app.post(
    "/api/expediting/{po_number}/draft-followup",
    response_model=FollowupEmail,
)
async def api_draft_followup(po_number: str, request: DraftFollowupRequest) -> FollowupEmail:
    email = draft_followup_email(po_number, request)
    if not email:
        raise HTTPException(status_code=404, detail="PO not found")
    return email


# --- M5: Logistics + Commercial + Simulations -------------------------------


@app.get("/api/logistics/shipments", response_model=LogisticsQueue)
async def api_logistics_queue() -> LogisticsQueue:
    return list_shipments()


@app.get("/api/logistics/shipments/{po_ref}", response_model=Shipment)
async def api_logistics_shipment(po_ref: str) -> Shipment:
    s = get_shipment(po_ref)
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return s


@app.post("/api/logistics/shipments/{po_ref}/events", response_model=ShipmentEvent)
async def api_logistics_add_event(
    po_ref: str, request: AddShipmentEventRequest
) -> ShipmentEvent:
    event = add_event(po_ref, request)
    if not event:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return event


@app.get("/api/logistics/shipments/{po_ref}/recommend-mode", response_model=ModeRecommendation)
async def api_logistics_recommend_mode(po_ref: str) -> ModeRecommendation:
    rec = recommend_mode(po_ref)
    if not rec:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return rec


@app.get("/api/commercial/summary", response_model=CommercialSummary)
async def api_commercial_summary() -> CommercialSummary:
    return build_commercial_summary()


@app.get(
    "/api/commercial/projects/{project_id}",
    response_model=list[CommercialLine],
)
async def api_commercial_project(project_id: str) -> list[CommercialLine]:
    return get_project_commercials(project_id)


@app.post("/api/risk/simulate", response_model=SimulationResult)
async def api_simulate(request: SimulationRequest) -> SimulationResult:
    try:
        return run_simulation(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- M6: AI Command Center --------------------------------------------------


@app.get("/api/weekly-plan", response_model=WeeklyPlan)
async def api_weekly_plan() -> WeeklyPlan:
    return build_weekly_plan()


@app.post("/api/chat", response_model=ChatReply)
async def api_chat(request: ChatRequest) -> ChatReply:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    return agent_dispatch(request.message, request.history)
