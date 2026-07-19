from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .auth import (
    current_user,
    issue_token,
    permissions_for,
    require_perm,
    require_role,
)
from .tenants import get_tenant, get_user, list_personas, list_tenants
from .ai_assist import generate_ai_brief
from .analytics import analyze_supply_chain
from .planning import (
    build_procurement_plan,
    compute_project_progress,
    get_bom,
    get_project,
    list_project_progress,
    list_projects,
    patch_bom_item,
    upload_bom_csv,
)
from .sample_data import build_demo_request
from .schemas import (
    AddShipmentEventRequest,
    AgentRequest,
    AgentResponse,
    Alert,
    AlertFeed,
    Approval,
    Award,
    AwardRFQRequest,
    DecideApprovalRequest,
    GatedAwardReply,
    GatedQuoteReply,
    GatedVendorReply,
    IngestCommitReply,
    IngestCommitRequest,
    IngestPreviewReply,
    BOMItem,
    BOMItemPatch,
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
    LogFollowupRequest,
    LoginReply,
    LoginRequest,
    LogisticsQueue,
    MeReply,
    ModeRecommendation,
    Persona,
    PortfolioSummary,
    ProcurementPlan,
    Project,
    ProjectProgress,
    SearchIndex,
    SearchIndexItem,
    PurchaseRequisition,
    Quote,
    QuoteComparison,
    RFQ,
    Shipment,
    ShipmentEvent,
    SupplierRecord,
    SimulationRequest,
    BOMAutofillReply,
    ExplainReply,
    ExplainRequest,
    RiskMitigationsReply,
    RiskRecord,
    SapEvent,
    SapEventReply,
    SapHealth,
    SapSubmitReply,
    AuditEvent,
    AuditPage,
    SetCriteriaRequest,
    SetTechnicalEvaluationRequest,
    SetWeightsRequest,
    TraceabilityChain,
    SimulationResult,
    SpecRequestReply,
    TBE,
    TechnicalCriterion,
    TechnicalEvaluation,
    SourcingPO,
    SourcingTimeline,
    Tenant,
    User,
    VendorBriefing,
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
    log_followup_sent,
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
from .portfolio import build_portfolio_summary
from .simulations import run_simulation
from .agent import dispatch as agent_dispatch
from .weekly_plan import build_weekly_plan


def _allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _origin_regex() -> str:
    """Allow any localhost in non-prod; tighten via env in prod.

    Set ALLOWED_ORIGIN_REGEX in the deployed env (e.g.
    `https://control-tower\\.example\\.com`) to restrict to your real domain.
    """
    env = os.getenv("ALLOWED_ORIGIN_REGEX", "").strip()
    if env:
        return env
    if os.getenv("APP_ENV", "dev").lower() in ("dev", "development"):
        return r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
    return ""  # prod default: only ALLOWED_ORIGINS list


try:
    from fastapi.responses import ORJSONResponse as _DefaultResponse  # ~5-10x faster JSON encode
except ImportError:  # orjson not installed — fall back silently
    from fastapi.responses import JSONResponse as _DefaultResponse  # type: ignore[assignment]

app = FastAPI(
    title="Project Control Tower",
    version="1.0.0",
    description="AI-assisted supply chain cockpit for engineering / EPC procurement.",
    default_response_class=_DefaultResponse,
)


@app.middleware("http")
async def _timing_middleware(request, call_next):
    """Stamp every response with server processing time (ms) — makes perf
    regressions visible in DevTools / curl without extra tooling."""
    import time as _time
    t0 = _time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(_time.perf_counter() - t0) * 1000:.1f}"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_origin_regex=_origin_regex() or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Lifecycle: snapshot persistence ---------------------------------------


@app.on_event("startup")
async def _startup_restore() -> None:
    """Restore in-memory state from disk (if a snapshot exists) and start the
    background snapshot job."""
    from . import persistence
    persistence.restore_all()
    persistence.start_background_snapshot()


@app.on_event("shutdown")
async def _shutdown_snapshot() -> None:
    """Last-chance snapshot on graceful shutdown."""
    from . import persistence
    persistence.snapshot_all()


# --- Health endpoints ------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Kubernetes / Docker / Fly health probe alias."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    """Readiness probe — includes snapshot state."""
    from . import persistence
    return {"status": "ok", "snapshot": persistence.snapshot_status()}


@app.post("/api/admin/snapshot", dependencies=[Depends(require_role("admin"))])
async def api_snapshot() -> dict[str, Any]:
    """Force an immediate snapshot of in-memory state to disk."""
    from . import persistence
    return persistence.snapshot_all()


# --- M7: Auth ---------------------------------------------------------------


@app.get("/api/auth/personas", response_model=list[Persona])
async def api_list_personas() -> list[Persona]:
    """Public list of seeded users for the login persona picker."""

    return list_personas()


@app.post("/api/auth/login", response_model=LoginReply)
async def api_login(request: LoginRequest) -> LoginReply:
    user = get_user(request.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Unknown user")
    tenant = get_tenant(user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=500, detail="User's tenant is missing")
    return LoginReply(
        token=issue_token(user),
        user=user,
        tenant=tenant,
        permissions=permissions_for(user.role),
    )


@app.get("/api/auth/me", response_model=MeReply)
async def api_me(user: Annotated[User, Depends(current_user)]) -> MeReply:
    tenant = get_tenant(user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=500, detail="Tenant missing")
    return MeReply(user=user, tenant=tenant, permissions=permissions_for(user.role))


@app.get(
    "/api/tenants",
    response_model=list[Tenant],
    dependencies=[Depends(require_role("admin"))],
)
async def api_list_tenants() -> list[Tenant]:
    return list_tenants()


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "Engineering Supply Chain Agent API",
        "frontend": "Run the React app in .start/frontend",
        "health": "/api/health",
    }


@app.get("/api/demo", response_model=AgentRequest)
async def demo_data(user: Annotated[User, Depends(current_user)]) -> AgentRequest:
    # Per-tenant slice — topbar shows the tenant's company name, sector and
    # real project count from their own data.
    # build_demo_request returns a shared cached tree; copy before changing.
    req = build_demo_request(user.tenant_id)
    company = req.company.model_copy(
        update={"active_projects": len(list_projects(tenant_id=user.tenant_id))}
    )
    return req.model_copy(update={"company": company})


@app.post("/api/analyze", response_model=AgentResponse)
async def analyze(
    request: AgentRequest,
    user: Annotated[User, Depends(current_user)],
) -> AgentResponse:
    draft = analyze_supply_chain(request, ai_response="")
    ai_brief = generate_ai_brief(request, draft.top_risks)
    return analyze_supply_chain(request, ai_response=ai_brief)


# --- M2: Projects / BOM / Procurement Plan -----------------------------------


@app.get("/api/projects", response_model=list[Project])
async def api_list_projects(
    user: Annotated[User, Depends(current_user)],
) -> list[Project]:
    return list_projects(tenant_id=user.tenant_id)


# NOTE: declared before /api/projects/{project_id} so "progress" isn't
# captured as a project_id by the dynamic route.
@app.get("/api/projects/progress", response_model=list[ProjectProgress])
async def api_list_project_progress(
    user: Annotated[User, Depends(current_user)],
) -> list[ProjectProgress]:
    return list_project_progress(tenant_id=user.tenant_id)


@app.get("/api/projects/{project_id}", response_model=Project)
async def api_get_project(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
) -> Project:
    project = get_project(project_id, tenant_id=user.tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.get("/api/projects/{project_id}/progress", response_model=ProjectProgress)
async def api_get_project_progress(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
) -> ProjectProgress:
    prog = compute_project_progress(project_id, tenant_id=user.tenant_id)
    if not prog:
        raise HTTPException(status_code=404, detail="Project not found")
    return prog


@app.get("/api/projects/{project_id}/bom", response_model=list[BOMItem])
async def api_get_bom(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
) -> list[BOMItem]:
    if not get_project(project_id, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return get_bom(project_id, tenant_id=user.tenant_id)


@app.get("/api/projects/{project_id}/procurement-plan", response_model=ProcurementPlan)
async def api_procurement_plan(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
) -> ProcurementPlan:
    plan = build_procurement_plan(project_id, tenant_id=user.tenant_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Project not found")
    return plan


@app.post("/api/projects/{project_id}/bom/upload", response_model=BomUploadResult)
async def api_upload_bom(
    project_id: str,
    file: UploadFile,
    user: Annotated[User, Depends(require_perm("bom", "create"))],
) -> BomUploadResult:
    if not get_project(project_id, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="Project not found")
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded")
    return upload_bom_csv(project_id, text, tenant_id=user.tenant_id)


@app.patch("/api/projects/{project_id}/bom/{bom_item_id}", response_model=BOMItem)
async def api_patch_bom_item(
    project_id: str,
    bom_item_id: str,
    body: BOMItemPatch,
    user: Annotated[User, Depends(require_perm("bom", "create"))],
) -> BOMItem:
    """Update category and/or supplier on a BOM line (autofill apply)."""
    fields_set = body.model_fields_set
    updated = patch_bom_item(
        project_id,
        bom_item_id,
        category=body.category,
        supplier_name=body.supplier_name,
        update_category="category" in fields_set,
        update_supplier="supplier_name" in fields_set,
        tenant_id=user.tenant_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="BOM item not found")
    return updated


# --- M3: Sourcing (PR → RFQ → Quote → Award → PO) ----------------------------


@app.get("/api/prs", response_model=list[PurchaseRequisition])
async def api_list_prs(
    user: Annotated[User, Depends(current_user)],
) -> list[PurchaseRequisition]:
    return list_prs(tenant_id=user.tenant_id)


@app.post("/api/prs", response_model=PurchaseRequisition)
async def api_create_pr(
    request: CreatePRRequest,
    user: Annotated[User, Depends(require_perm("pr", "create"))],
) -> PurchaseRequisition:
    if not get_project(request.project_id, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="Project not found")
    pr = create_pr(request, tenant_id=user.tenant_id)
    if not pr:
        raise HTTPException(status_code=404, detail="Project not found")
    return pr


@app.get("/api/prs/{pr_no}", response_model=PurchaseRequisition)
async def api_get_pr(
    pr_no: str,
    user: Annotated[User, Depends(current_user)],
) -> PurchaseRequisition:
    pr = get_pr(pr_no, tenant_id=user.tenant_id)
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    return pr


@app.get("/api/prs/{pr_no}/suggested-vendors", response_model=list[str])
async def api_suggest_vendors(
    pr_no: str,
    user: Annotated[User, Depends(current_user)],
) -> list[str]:
    pr = get_pr(pr_no, tenant_id=user.tenant_id)
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    return suggest_vendors(pr.project_id, pr.bom_item_id)


@app.get("/api/rfqs", response_model=list[RFQ])
async def api_list_rfqs(
    user: Annotated[User, Depends(current_user)],
) -> list[RFQ]:
    return list_rfqs(tenant_id=user.tenant_id)


@app.post("/api/rfqs", response_model=RFQ)
async def api_issue_rfq(
    request: CreateRFQRequest,
    user: Annotated[User, Depends(require_perm("rfq", "create"))],
) -> RFQ:
    if not request.vendors:
        raise HTTPException(status_code=400, detail="At least one vendor is required.")
    rfq = issue_rfq(request, tenant_id=user.tenant_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="PR not found or already awarded")
    return rfq


@app.get("/api/rfqs/{rfq_no}", response_model=RFQ)
async def api_get_rfq(
    rfq_no: str,
    user: Annotated[User, Depends(current_user)],
) -> RFQ:
    rfq = get_rfq(rfq_no, tenant_id=user.tenant_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return rfq


@app.get("/api/rfqs/{rfq_no}/quotes", response_model=list[Quote])
async def api_get_quotes(
    rfq_no: str,
    user: Annotated[User, Depends(current_user)],
) -> list[Quote]:
    if not get_rfq(rfq_no, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="RFQ not found")
    return get_quotes(rfq_no, tenant_id=user.tenant_id)


@app.post("/api/rfqs/{rfq_no}/quotes", response_model=GatedQuoteReply)
async def api_add_quote(
    rfq_no: str,
    request: CreateQuoteRequest,
    user: Annotated[User, Depends(require_perm("quote", "create"))],
) -> GatedQuoteReply:
    from .approvals import gate_quote
    if not get_rfq(rfq_no, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="RFQ not found")
    reply = gate_quote(rfq_no, request, user)
    if reply.status == "applied" and reply.quote is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return reply


@app.get("/api/rfqs/{rfq_no}/compare", response_model=QuoteComparison)
async def api_compare_quotes(
    rfq_no: str,
    user: Annotated[User, Depends(current_user)],
) -> QuoteComparison:
    comparison = compare_quotes(rfq_no, tenant_id=user.tenant_id)
    if not comparison:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return comparison


@app.post("/api/rfqs/{rfq_no}/award", response_model=GatedAwardReply)
async def api_award_rfq(
    rfq_no: str,
    request: AwardRFQRequest,
    user: Annotated[User, Depends(require_perm("award", "create"))],
) -> GatedAwardReply:
    from .approvals import gate_award
    if not get_rfq(rfq_no, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="RFQ not found")
    reply = gate_award(rfq_no, request, user)
    if reply.status == "applied" and reply.award is None:
        raise HTTPException(status_code=404, detail="RFQ or quote not found")
    return reply


# --- M7.3: Approvals --------------------------------------------------------


@app.get("/api/approvals", response_model=list[Approval])
async def api_list_approvals(
    user: Annotated[User, Depends(current_user)],
) -> list[Approval]:
    from .approvals import list_approvals
    return list_approvals(user.tenant_id, user)


@app.post("/api/approvals/{approval_id}/approve", response_model=Approval)
async def api_approve(
    approval_id: str,
    user: Annotated[User, Depends(require_perm("approval", "decide"))],
    request: Optional[DecideApprovalRequest] = None,
) -> Approval:
    from .approvals import decide
    result = decide(user.tenant_id, approval_id, user, approve=True, note=(request.note if request else None))
    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return result


@app.post("/api/approvals/{approval_id}/reject", response_model=Approval)
async def api_reject(
    approval_id: str,
    user: Annotated[User, Depends(require_perm("approval", "decide"))],
    request: Optional[DecideApprovalRequest] = None,
) -> Approval:
    from .approvals import decide
    result = decide(user.tenant_id, approval_id, user, approve=False, note=(request.note if request else None))
    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return result


# --- Ingestion engine --------------------------------------------------------


@app.post("/api/ingest/preview", response_model=IngestPreviewReply)
async def api_ingest_preview(
    file: UploadFile,
    user: Annotated[User, Depends(require_perm("ingest", "preview"))],
) -> IngestPreviewReply:
    """Parse + classify + column-map an uploaded workbook/CSV. Stages the
    validated rows and returns a full preview; nothing is written yet."""
    from .ingest import preview
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (10 MB max)")
    try:
        return preview(file.filename or "upload", raw, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ingest/commit", response_model=IngestCommitReply)
async def api_ingest_commit(
    request: IngestCommitRequest,
    user: Annotated[User, Depends(require_perm("ingest", "commit"))],
) -> IngestCommitReply:
    from .ingest import commit
    try:
        return commit(request.staging_id, user, request.default_project_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))


# --- Alerts feed ------------------------------------------------------------


@app.get("/api/alerts", response_model=AlertFeed)
async def api_alerts(
    user: Annotated[User, Depends(current_user)],
) -> AlertFeed:
    from .alerts import build_alert_feed
    return build_alert_feed(user)


# --- Technical Bid Evaluation (TBE) -----------------------------------------


@app.get("/api/rfqs/{rfq_no}/criteria", response_model=list[TechnicalCriterion])
async def api_get_criteria(
    rfq_no: str,
    user: Annotated[User, Depends(current_user)],
) -> list[TechnicalCriterion]:
    from .tbe import get_criteria
    from .sourcing import get_rfq
    rfq = get_rfq(rfq_no, tenant_id=user.tenant_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return get_criteria(rfq_no, rfq.description)


@app.post("/api/rfqs/{rfq_no}/criteria", response_model=list[TechnicalCriterion])
async def api_set_criteria(
    rfq_no: str,
    request: SetCriteriaRequest,
    user: Annotated[User, Depends(require_perm("rfq", "create"))],
) -> list[TechnicalCriterion]:
    from .tbe import set_criteria
    from .sourcing import get_rfq
    if not get_rfq(rfq_no, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="RFQ not found")
    return set_criteria(rfq_no, request.criteria)


@app.get("/api/rfqs/{rfq_no}/technical", response_model=list[TechnicalEvaluation])
async def api_list_technical(
    rfq_no: str,
    user: Annotated[User, Depends(current_user)],
) -> list[TechnicalEvaluation]:
    from .tbe import list_evaluations
    from .sourcing import get_rfq
    if not get_rfq(rfq_no, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="RFQ not found")
    return list_evaluations(rfq_no)


@app.post(
    "/api/rfqs/{rfq_no}/technical/{quote_id}",
    response_model=TechnicalEvaluation,
)
async def api_set_technical(
    rfq_no: str,
    quote_id: str,
    request: SetTechnicalEvaluationRequest,
    user: Annotated[User, Depends(require_perm("rfq", "create"))],
) -> TechnicalEvaluation:
    from .tbe import set_evaluation
    from .sourcing import get_rfq, get_quotes
    rfq = get_rfq(rfq_no, tenant_id=user.tenant_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    quote = next(
        (q for q in get_quotes(rfq_no, tenant_id=user.tenant_id) if q.quote_id == quote_id),
        None,
    )
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found on this RFQ")
    return set_evaluation(
        rfq_no=rfq_no,
        quote_id=quote_id,
        vendor=quote.vendor,
        scores=request.criteria_scores,
        notes=request.notes or "",
        evaluated_by=request.evaluated_by or "Control Tower",
        source="manual",
    )


@app.post("/api/rfqs/{rfq_no}/auto-evaluate", response_model=list[TechnicalEvaluation])
async def api_auto_evaluate(
    rfq_no: str,
    user: Annotated[User, Depends(require_perm("rfq", "create"))],
) -> list[TechnicalEvaluation]:
    from .tbe import auto_evaluate
    from .sourcing import get_rfq
    if not get_rfq(rfq_no, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="RFQ not found")
    return auto_evaluate(rfq_no)


@app.post("/api/rfqs/{rfq_no}/weights", response_model=dict[str, float])
async def api_set_weights(
    rfq_no: str,
    request: SetWeightsRequest,
    user: Annotated[User, Depends(require_perm("rfq", "create"))],
) -> dict[str, float]:
    from .tbe import set_weights
    from .sourcing import get_rfq
    if not get_rfq(rfq_no, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="RFQ not found")
    c, t = set_weights(rfq_no, request.commercial_weight, request.technical_weight)
    return {"commercial_weight": c, "technical_weight": t}


@app.get("/api/rfqs/{rfq_no}/tbe", response_model=TBE)
async def api_tbe(
    rfq_no: str,
    user: Annotated[User, Depends(current_user)],
) -> TBE:
    from .tbe import build_tbe
    from .sourcing import get_rfq
    if not get_rfq(rfq_no, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="RFQ not found")
    return build_tbe(rfq_no)


# --- Audit Trail ------------------------------------------------------------


@app.get("/api/audit", response_model=AuditPage)
async def api_audit(
    user: Annotated[User, Depends(current_user)],
    actor: Optional[str] = None,
    action: Optional[str] = None,
    entity_kind: Optional[str] = None,
    entity_id: Optional[str] = None,
    project_id: Optional[str] = None,
    bom_item_id: Optional[str] = None,
    bom_code: Optional[str] = None,
    pr_no: Optional[str] = None,
    rfq_no: Optional[str] = None,
    po_no: Optional[str] = None,
    vendor: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> AuditPage:
    from .audit import query
    return query(
        actor=actor, action=action, entity_kind=entity_kind, entity_id=entity_id,
        project_id=project_id, bom_item_id=bom_item_id, bom_code=bom_code,
        pr_no=pr_no, rfq_no=rfq_no, po_no=po_no, vendor=vendor,
        search=search,
        tenant_id=user.tenant_id,
        limit=min(max(limit, 1), 500),
        offset=max(offset, 0),
    )


@app.get("/api/audit/pivots/materials")
async def api_pivot_materials(
    user: Annotated[User, Depends(current_user)],
) -> list[Any]:
    from .audit import pivot_materials
    return pivot_materials(tenant_id=user.tenant_id)


@app.get("/api/audit/pivots/pos")
async def api_pivot_pos(
    user: Annotated[User, Depends(current_user)],
) -> list[Any]:
    from .audit import pivot_pos
    return pivot_pos(tenant_id=user.tenant_id)


@app.get("/api/audit/pivots/vendors")
async def api_pivot_vendors(
    user: Annotated[User, Depends(current_user)],
) -> list[Any]:
    from .audit import pivot_vendors
    return pivot_vendors(tenant_id=user.tenant_id)


@app.get("/api/audit/stats")
async def api_audit_stats(
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    from .audit import stats
    return stats(tenant_id=user.tenant_id)


@app.get("/api/audit/entity/{kind}/{eid}", response_model=list[AuditEvent])
async def api_audit_entity(
    kind: str,
    eid: str,
    user: Annotated[User, Depends(current_user)],
) -> list[AuditEvent]:
    from .audit import events_for_entity
    return events_for_entity(kind, eid, tenant_id=user.tenant_id)


@app.get("/api/audit/trace/bom/{bom_item_id}", response_model=TraceabilityChain)
async def api_trace_bom(
    bom_item_id: str,
    user: Annotated[User, Depends(current_user)],
) -> TraceabilityChain:
    from .audit import trace_from_bom
    chain = trace_from_bom(bom_item_id, tenant_id=user.tenant_id)
    if not chain:
        raise HTTPException(status_code=404, detail="BOM item not found")
    return chain


@app.get("/api/audit/trace/pr/{pr_no}", response_model=TraceabilityChain)
async def api_trace_pr(
    pr_no: str,
    user: Annotated[User, Depends(current_user)],
) -> TraceabilityChain:
    from .audit import trace_from_pr
    chain = trace_from_pr(pr_no, tenant_id=user.tenant_id)
    if not chain:
        raise HTTPException(status_code=404, detail="PR not found or has no BOM link")
    return chain


@app.get("/api/audit/trace/po/{po_no}", response_model=TraceabilityChain)
async def api_trace_po(
    po_no: str,
    user: Annotated[User, Depends(current_user)],
) -> TraceabilityChain:
    from .audit import trace_from_po
    chain = trace_from_po(po_no, tenant_id=user.tenant_id)
    if not chain:
        raise HTTPException(status_code=404, detail="PO not found")
    return chain


@app.get("/api/audit/export.csv")
async def api_audit_export(
    user: Annotated[User, Depends(current_user)],
    actor: Optional[str] = None,
    action: Optional[str] = None,
    entity_kind: Optional[str] = None,
    project_id: Optional[str] = None,
    search: Optional[str] = None,
):
    """Stream the filtered audit log as CSV for download."""

    from .audit import query, export_csv
    page = query(
        actor=actor, action=action, entity_kind=entity_kind,
        project_id=project_id, search=search,
        tenant_id=user.tenant_id,
        limit=10_000, offset=0,
    )
    body = export_csv(page.events)
    filename = f"audit_log_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/awards", response_model=list[Award])
async def api_list_awards(
    user: Annotated[User, Depends(current_user)],
) -> list[Award]:
    return list_awards(tenant_id=user.tenant_id)


@app.get("/api/sourcing-pos", response_model=list[SourcingPO])
async def api_list_sourcing_pos(
    user: Annotated[User, Depends(current_user)],
) -> list[SourcingPO]:
    return list_pos(tenant_id=user.tenant_id)


@app.get("/api/sourcing-pos/{po_no}", response_model=SourcingPO)
async def api_get_sourcing_po(
    po_no: str,
    user: Annotated[User, Depends(current_user)],
) -> SourcingPO:
    po = get_po(po_no, tenant_id=user.tenant_id)
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    return po


@app.get("/api/sourcing-pos/{po_no}/timeline", response_model=SourcingTimeline)
async def api_get_sourcing_po_timeline(
    po_no: str,
    user: Annotated[User, Depends(current_user)],
) -> SourcingTimeline:
    timeline = build_timeline(po_no, tenant_id=user.tenant_id)
    if not timeline:
        raise HTTPException(status_code=404, detail="PO not found")
    return timeline


# --- M4: Vendor Intelligence + Expediting -----------------------------------


@app.get("/api/vendors/intel", response_model=list[VendorSummary])
async def api_list_vendor_intel(
    user: Annotated[User, Depends(current_user)],
) -> list[VendorSummary]:
    return list_vendor_summaries(tenant_id=user.tenant_id)


@app.post("/api/vendors", response_model=GatedVendorReply)
async def api_create_vendor(
    supplier: SupplierRecord,
    user: Annotated[User, Depends(require_perm("vendor", "create"))],
) -> GatedVendorReply:
    """Add a runtime supplier for the tenant. May require procurement-head
    approval before the vendor materialises in the master list."""
    from .approvals import gate_vendor
    from .audit import emit

    reply = gate_vendor(supplier, user)
    if reply.status == "applied":
        if reply.scorecard is None:
            raise HTTPException(status_code=500, detail="Vendor stored but scorecard could not be built")
        emit(
            action="created",
            entity_kind="vendor",
            entity_id=supplier.name,
            subject=supplier.name,
            summary=(
                f"Vendor {supplier.name} added · {supplier.category} · {supplier.country} · "
                f"composite {reply.scorecard.composite_score} grade {reply.scorecard.composite_grade}"
            ),
            actor=user.user_id,
            source="api",
            tenant_id=user.tenant_id,
            vendor=supplier.name,
            metadata={
                "category": supplier.category,
                "country": supplier.country,
                "lead_time_days": supplier.lead_time_days,
                "on_time_delivery_pct": supplier.on_time_delivery_pct,
                "quality_ppm": supplier.quality_ppm,
                "annual_spend_usd": supplier.annual_spend_usd,
                "approved_alternatives": supplier.approved_alternatives,
                "risk_flags": supplier.risk_flags,
            },
        )
    return reply


@app.delete("/api/vendors/{name}", status_code=204)
async def api_delete_vendor(
    name: str,
    user: Annotated[User, Depends(require_perm("vendor", "delete"))],
):
    """Remove a runtime supplier. Static (seeded) suppliers cannot be removed."""
    from .vendor_store import remove_supplier
    if not remove_supplier(user.tenant_id, name):
        raise HTTPException(status_code=404, detail="Runtime vendor not found (static seed cannot be deleted)")
    return None


@app.get("/api/vendors/concentration", response_model=list[CategoryConcentration])
async def api_vendor_concentration(
    user: Annotated[User, Depends(current_user)],
) -> list[CategoryConcentration]:
    return list_category_concentration(tenant_id=user.tenant_id)


@app.get("/api/vendors/intel/{name}", response_model=VendorScorecard)
async def api_vendor_scorecard(
    name: str,
    user: Annotated[User, Depends(current_user)],
) -> VendorScorecard:
    scorecard = get_vendor_scorecard(name, tenant_id=user.tenant_id)
    if not scorecard:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return scorecard


@app.get("/api/vendors/intel/{name}/briefing", response_model=VendorBriefing)
async def api_vendor_briefing(
    name: str,
    user: Annotated[User, Depends(current_user)],
) -> VendorBriefing:
    from .vendor_intel import build_vendor_briefing
    briefing = build_vendor_briefing(name, tenant_id=user.tenant_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return briefing


@app.get("/api/expediting/queue", response_model=ExpediteQueue)
async def api_expediting_queue(
    user: Annotated[User, Depends(current_user)],
) -> ExpediteQueue:
    return build_expedite_queue(tenant_id=user.tenant_id)


@app.get("/api/expediting/queue/{po_number}", response_model=ExpediteItem)
async def api_expediting_item(
    po_number: str,
    user: Annotated[User, Depends(current_user)],
) -> ExpediteItem:
    item = get_expedite_item(po_number, tenant_id=user.tenant_id)
    if not item:
        raise HTTPException(status_code=404, detail="PO not found in expedite queue")
    return item


@app.post(
    "/api/expediting/{po_number}/draft-followup",
    response_model=FollowupEmail,
)
async def api_draft_followup(
    po_number: str,
    request: DraftFollowupRequest,
    user: Annotated[User, Depends(require_perm("followup", "create"))],
) -> FollowupEmail:
    email = draft_followup_email(po_number, request, tenant_id=user.tenant_id)
    if not email:
        raise HTTPException(status_code=404, detail="PO not found")
    return email


@app.post(
    "/api/expediting/{po_number}/log-followup",
    response_model=ExpediteItem,
)
async def api_log_followup(
    po_number: str,
    request: LogFollowupRequest,
    user: Annotated[User, Depends(require_perm("followup", "create"))],
) -> ExpediteItem:
    item = log_followup_sent(
        po_number,
        request,
        actor=user.user_id,
        tenant_id=user.tenant_id,
    )
    if not item:
        raise HTTPException(status_code=404, detail="PO not found")
    return item


# --- M5: Logistics + Commercial + Simulations -------------------------------


@app.get("/api/logistics/shipments", response_model=LogisticsQueue)
async def api_logistics_queue(
    user: Annotated[User, Depends(current_user)],
) -> LogisticsQueue:
    return list_shipments(tenant_id=user.tenant_id)


@app.get("/api/logistics/shipments/{po_ref}", response_model=Shipment)
async def api_logistics_shipment(
    po_ref: str,
    user: Annotated[User, Depends(current_user)],
) -> Shipment:
    s = get_shipment(po_ref, tenant_id=user.tenant_id)
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return s


@app.post("/api/logistics/shipments/{po_ref}/events", response_model=ShipmentEvent)
async def api_logistics_add_event(
    po_ref: str,
    request: AddShipmentEventRequest,
    user: Annotated[User, Depends(require_perm("shipment_event", "create"))],
) -> ShipmentEvent:
    event = add_event(po_ref, request, tenant_id=user.tenant_id)
    if not event:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return event


@app.get("/api/logistics/shipments/{po_ref}/recommend-mode", response_model=ModeRecommendation)
async def api_logistics_recommend_mode(
    po_ref: str,
    user: Annotated[User, Depends(current_user)],
) -> ModeRecommendation:
    rec = recommend_mode(po_ref, tenant_id=user.tenant_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return rec


# --- Portfolio (tenant cockpit) ---------------------------------------------


@app.get("/api/portfolio/summary", response_model=PortfolioSummary)
async def api_portfolio_summary(
    user: Annotated[User, Depends(current_user)],
) -> PortfolioSummary:
    return build_portfolio_summary(tenant_id=user.tenant_id)


from ._cache import ttl_cache as _ttl_cache


@_ttl_cache(ttl_seconds=30.0)
def _build_search_index(tenant_id: str) -> SearchIndex:
    """Lightweight in-memory index for the Cmd+K palette.

    All searchable entities for the tenant in one shot — small enough to
    fuzzy-match client-side without a server round-trip per keystroke.
    Cached 30s per tenant; write paths bust it via invalidate_all().
    """
    from datetime import datetime, timezone
    from .vendor_intel import list_vendor_summaries

    items: list[SearchIndexItem] = []
    for p in list_projects(tenant_id=tenant_id):
        items.append(SearchIndexItem(
            kind="project", id=p.project_id, title=p.name,
            subtitle=f"{p.client} · {p.site}",
            href=f"/projects/{p.project_id}",
            project_id=p.project_id,
            tags=[p.sector],
        ))
        for b in get_bom(p.project_id, tenant_id=tenant_id):
            items.append(SearchIndexItem(
                kind="bom", id=b.bom_item_id,
                title=f"{b.code} · {b.description}",
                subtitle=f"{p.name} · {b.quantity} {b.uom}",
                href=f"/projects/{p.project_id}?bom={b.bom_item_id}",
                project_id=p.project_id,
                tags=[b.category or "", b.status],
            ))
    for v in list_vendor_summaries(tenant_id=tenant_id):
        items.append(SearchIndexItem(
            kind="vendor", id=v.vendor, title=v.vendor,
            subtitle=f"{v.category} · {v.country} · score {v.composite_score}",
            href=f"/vendors/{v.vendor}",
            tags=[v.category, v.country],
        ))
    for pr in list_prs(tenant_id=tenant_id):
        items.append(SearchIndexItem(
            kind="pr", id=pr.pr_no,
            title=f"{pr.pr_no} · {pr.code}",
            subtitle=f"{pr.description} · {pr.quantity} {pr.uom} · {pr.status}",
            href=f"/sourcing/prs/{pr.pr_no}",
            project_id=pr.project_id,
            tags=[pr.status, pr.strategy],
        ))
    for po in list_pos(tenant_id=tenant_id):
        items.append(SearchIndexItem(
            kind="po", id=po.po_no,
            title=f"{po.po_no} · {po.code}",
            subtitle=f"{po.vendor} · ${po.value_usd:,.0f} · {po.status}",
            href=f"/pos?po={po.po_no}",
            project_id=po.project_id,
            tags=[po.status, po.vendor],
        ))
    return SearchIndex(generated_at=datetime.now(timezone.utc), items=items)


@app.get("/api/search/index", response_model=SearchIndex)
async def api_search_index(
    user: Annotated[User, Depends(current_user)],
) -> SearchIndex:
    return _build_search_index(user.tenant_id)


@app.get("/api/commercial/summary", response_model=CommercialSummary)
async def api_commercial_summary(
    user: Annotated[User, Depends(current_user)],
) -> CommercialSummary:
    return build_commercial_summary(tenant_id=user.tenant_id)


@app.get(
    "/api/commercial/projects/{project_id}",
    response_model=list[CommercialLine],
)
async def api_commercial_project(
    project_id: str,
    user: Annotated[User, Depends(current_user)],
) -> list[CommercialLine]:
    return get_project_commercials(project_id, tenant_id=user.tenant_id)


@app.post("/api/risk/simulate", response_model=SimulationResult)
async def api_simulate(
    request: SimulationRequest,
    user: Annotated[User, Depends(current_user)],
) -> SimulationResult:
    try:
        return run_simulation(request, tenant_id=user.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- M6: AI Command Center --------------------------------------------------


@app.get("/api/weekly-plan", response_model=WeeklyPlan)
async def api_weekly_plan(
    user: Annotated[User, Depends(current_user)],
) -> WeeklyPlan:
    return build_weekly_plan(tenant_id=user.tenant_id)


@app.post("/api/chat", response_model=ChatReply)
async def api_chat(
    request: ChatRequest,
    user: Annotated[User, Depends(current_user)],
) -> ChatReply:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    from .agent_tools import reset_tool_user, set_tool_user

    token = set_tool_user(user)
    try:
        return agent_dispatch(request.message, request.history, page=request.page)
    finally:
        reset_tool_user(token)


@app.post("/api/chat/stream")
async def api_chat_stream(
    request: ChatRequest,
    user: Annotated[User, Depends(current_user)],
):
    """SSE version of /api/chat — emits live progress while the agent works.

    Frames:
      event: status  data: thinking
      event: tool    data: open_prs
      event: reply   data: {full ChatReply JSON}
      event: done    data: {}

    The agent loop runs in a worker thread; events flow through a queue so
    the client sees tool calls the moment they happen instead of staring at
    a spinner for the whole multi-turn LLM loop.
    """
    import asyncio
    import queue as _queue
    import threading

    from fastapi.responses import StreamingResponse

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    q: _queue.Queue = _queue.Queue()

    def on_event(kind: str, detail: str) -> None:
        q.put((kind, detail))

    def run() -> None:
        from .agent_tools import reset_tool_user, set_tool_user

        token = set_tool_user(user)
        try:
            reply = agent_dispatch(
                request.message, request.history, page=request.page, on_event=on_event
            )
            q.put(("reply", reply.model_dump_json()))
        except Exception as e:  # noqa: BLE001
            q.put(("error", str(e)))
        finally:
            reset_tool_user(token)
            q.put(("done", ""))

    threading.Thread(target=run, daemon=True).start()

    async def gen():
        loop = asyncio.get_event_loop()
        while True:
            kind, detail = await loop.run_in_executor(None, q.get)
            yield f"event: {kind}\ndata: {detail}\n\n"
            if kind == "done":
                break

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/ai/status")
async def api_ai_status(
    user: Annotated[User, Depends(current_user)],
) -> dict:
    """AI subsystem health — provider, model, call stats."""
    from .llm import XAI_BASE, XAI_MODEL, get_stats, is_enabled
    return {
        "enabled": is_enabled(),
        "provider": "xai" if is_enabled() else "deterministic-fallback",
        "model": XAI_MODEL if is_enabled() else None,
        "base_url": XAI_BASE if is_enabled() else None,
        "stats": get_stats(),
    }


@app.post("/api/ai/propose-vendor", response_model=GatedVendorReply)
async def api_propose_vendor(
    supplier: SupplierRecord,
    user: Annotated[User, Depends(require_perm("vendor", "create"))],
) -> GatedVendorReply:
    """AI/REST path to propose vendor onboarding through the approval gate."""
    from .ai_actions import propose_vendor_onboarding

    return propose_vendor_onboarding(supplier, user)


# --- M7-adjacent AI features ------------------------------------------------


@app.post("/api/risks/mitigations", response_model=RiskMitigationsReply)
async def api_risk_mitigations(
    risk: RiskRecord,
    user: Annotated[User, Depends(current_user)],
) -> RiskMitigationsReply:
    """Generate 3 concrete mitigations for a risk record.

    Send the risk record (as returned in AgentResponse.top_risks) in the body.
    Returns LLM-generated mitigations when XAI_API_KEY is set, otherwise
    falls back to deterministic templates.
    """

    from .analytics import generate_risk_mitigations
    return generate_risk_mitigations(risk)


@app.post("/api/projects/{project_id}/bom/autofill", response_model=BOMAutofillReply)
async def api_bom_autofill(
    project_id: str,
    user: Annotated[User, Depends(require_perm("bom", "create"))],
) -> BOMAutofillReply:
    """Propose category + supplier values for BOM rows missing them."""

    from .ai_actions import bom_autofill
    if not get_project(project_id, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return bom_autofill(project_id)


@app.post(
    "/api/projects/{project_id}/bom/{bom_item_id}/spec-request",
    response_model=SpecRequestReply,
)
async def api_spec_request(
    project_id: str,
    bom_item_id: str,
    user: Annotated[User, Depends(current_user)],
) -> SpecRequestReply:
    """Draft an engineering spec-request email for a missing-spec BOM item."""

    from .ai_actions import draft_spec_request
    if not get_project(project_id, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="Project not found")
    reply = draft_spec_request(project_id, bom_item_id)
    if not reply:
        raise HTTPException(status_code=404, detail="BOM item not found")
    return reply


@_ttl_cache(ttl_seconds=600.0)
def _cached_explain(kind: str, entity_id: str) -> ExplainReply:
    """Explain briefs are stable for minutes and each one may be an LLM call —
    cache 10 min per (kind, id). Write paths bust this via invalidate_all()."""
    from .ai_actions import explain_entity
    return explain_entity(ExplainRequest(kind=kind, id=entity_id))  # type: ignore[arg-type]


@app.post("/api/explain", response_model=ExplainReply)
async def api_explain(
    request: ExplainRequest,
    user: Annotated[User, Depends(current_user)],
) -> ExplainReply:
    """Generate a 'what should I know' brief for any kind of entity.

    Supported kinds: po, vendor, risk, project, rfq, pr.
    """

    return _cached_explain(request.kind, request.id)


# --- SAP CPI Integration (Phase 0 scaffold) ---------------------------------


@app.post("/api/prs/{pr_no}/submit-to-sap", response_model=SapSubmitReply)
async def api_submit_pr_to_sap(
    pr_no: str,
    user: Annotated[User, Depends(require_perm("pr", "create"))],
) -> SapSubmitReply:
    from datetime import datetime, timezone
    from .sourcing import submit_pr_to_sap
    pr = submit_pr_to_sap(pr_no, tenant_id=user.tenant_id)
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    return SapSubmitReply(
        ok=pr.sap_status == "synced",
        pr_no=pr.pr_no,
        sap_pr_no=pr.sap_pr_no,
        sap_status=pr.sap_status,
        sap_error=pr.sap_error,
        submitted_at=datetime.now(timezone.utc),
    )


@app.post("/api/sourcing-pos/{po_no}/submit-to-sap", response_model=SapSubmitReply)
async def api_submit_po_to_sap(
    po_no: str,
    user: Annotated[User, Depends(require_perm("po", "create"))],
) -> SapSubmitReply:
    from datetime import datetime, timezone
    from .sourcing import submit_po_to_sap
    po = submit_po_to_sap(po_no, tenant_id=user.tenant_id)
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    return SapSubmitReply(
        ok=po.sap_status == "synced",
        po_no=po.po_no,
        sap_po_no=po.sap_po_no,
        sap_status=po.sap_status,
        sap_error=po.sap_error,
        submitted_at=datetime.now(timezone.utc),
    )


@app.post("/api/integrations/sap/event", response_model=SapEventReply)
async def api_sap_event(event: SapEvent) -> SapEventReply:
    """Inbound webhook from CPI carrying SAP status changes."""

    from .integrations.sap_cpi import record_event_received
    from .sourcing import apply_sap_event
    record_event_received()
    accepted, matched, applied_to, note = apply_sap_event(event)
    return SapEventReply(
        accepted=accepted,
        matched_ct_ref=matched,
        applied_to=applied_to,
        note=note,
    )


@app.get("/api/integrations/sap/health", response_model=SapHealth)
async def api_sap_health() -> SapHealth:
    from .integrations.sap_cpi import health
    return health()


@app.post("/api/integrations/sap/resync", dependencies=[Depends(require_role("admin"))])
async def api_sap_resync() -> dict[str, Any]:  # noqa: ANN401
    """Manual reconciliation trigger — pulls current status for every synced
    PR/PO from SAP and updates local state. In Phase 0 mock mode this just
    walks the existing records and randomises their progression a bit so the
    flow is testable.
    """
    from .integrations.sap_cpi import get_pr_status, get_po_status
    from .sourcing import _prs, _pos  # type: ignore[attr-defined]

    pr_updated = 0
    po_updated = 0
    for pr in _prs.values():
        if pr.sap_pr_no:
            _ = get_pr_status(pr.sap_pr_no)
            pr_updated += 1
    for po in _pos.values():
        if po.sap_po_no:
            r = get_po_status(po.sap_po_no)
            # In mock mode, occasionally bump GR/IR so the demo feels alive
            if r.get("gr_qty"):
                po.sap_gr_qty = (po.sap_gr_qty or 0) + float(r["gr_qty"])
            if r.get("ir_value_usd"):
                po.sap_ir_value_usd = (po.sap_ir_value_usd or 0) + float(r["ir_value_usd"])
            po_updated += 1
    return {"prs_reconciled": pr_updated, "pos_reconciled": po_updated}
