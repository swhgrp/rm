"""
FastAPI router for GL Anomaly Review system.

Mounted at /api/gl-review. All endpoints require Portal SSO auth.
"""
import logging
import math
import threading
import uuid
from datetime import datetime, timezone, date, timedelta
from collections import Counter

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func as sqlfunc, desc, case
from sqlalchemy.orm import Session

from accounting.db.database import get_db, SessionLocal
from accounting.api.auth import require_auth, require_admin
from accounting.models.user import User
from accounting.models.area import Area
from accounting.models.account import Account
from accounting.gl_review.models import (
    GLAnomalyFlag, GLAccountBaseline,
    STATUS_OPEN, STATUS_SUPERSEDED,
    SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO,
)
from accounting.gl_review.schemas import (
    GLReviewRunRequest, GLReviewRunResponse,
    GLFlagResponse, GLFlagReviewRequest, GLFlagBulkReviewRequest,
    GLBaselineResponse, GLReviewSummaryResponse, PaginatedFlagsResponse,
)
from accounting.gl_review.rules_engine import run_rules_engine
from accounting.gl_review.ai_analyzer import analyze_flags_with_ai
from accounting.gl_review.baselines import compute_baselines

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gl-review", tags=["GL Review"])

# In-memory run status tracker (run_id -> status dict)
_run_status: dict[str, dict] = {}


# --- Background task runner ---

def _run_detection_background(run_id: str, area_id: int, area_name: str, date_from: date, date_to: date, use_ai: bool):
    """Background task that runs rules engine + optional AI analysis and persists flags."""
    _run_status[run_id] = {"status": "running", "area_id": area_id, "step": "rules_engine"}
    db: Session = SessionLocal()
    try:
        logger.info(f"GL review run {run_id}: starting for area_id={area_id} ({date_from} to {date_to})")
        start_time = datetime.now(timezone.utc)

        # Run rules engine
        flags = run_rules_engine(db, area_id, date_from, date_to)
        logger.info(f"GL review run {run_id}: rules engine found {len(flags)} flags")

        # Run AI analysis on warning/critical flags only (info flags don't need it)
        if use_ai and flags:
            ai_flags = [f for f in flags if f.get("severity") != SEVERITY_INFO]
            if ai_flags:
                _run_status[run_id]["step"] = "ai_analysis"
                period_label = f"{date_from} to {date_to}"
                # ai_flags contains refs to same dicts in flags, so in-place edits propagate
                analyze_flags_with_ai(ai_flags, area_id, area_name, period_label)

        # Persist flags
        _run_status[run_id]["step"] = "saving"
        for flag_dict in flags:
            flag = GLAnomalyFlag(
                area_id=area_id,
                journal_entry_id=flag_dict.get('journal_entry_id'),
                journal_entry_line_id=flag_dict.get('journal_entry_line_id'),
                account_id=flag_dict.get('account_id'),
                flag_type=flag_dict['flag_type'],
                severity=flag_dict['severity'],
                title=flag_dict['title'],
                detail=flag_dict.get('detail'),
                flagged_value=flag_dict.get('flagged_value'),
                expected_range_low=flag_dict.get('expected_range_low'),
                expected_range_high=flag_dict.get('expected_range_high'),
                period_date=flag_dict.get('period_date'),
                status=STATUS_OPEN,
                ai_reasoning=flag_dict.get('ai_reasoning'),
                ai_confidence=flag_dict.get('ai_confidence'),
                run_id=run_id,
            )
            db.add(flag)

        db.commit()

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(f"GL review run {run_id}: completed in {elapsed:.1f}s, {len(flags)} flags persisted")
        _run_status[run_id] = {"status": "completed", "area_id": area_id, "total_flags": len(flags)}

    except Exception:
        db.rollback()
        logger.exception(f"GL review run {run_id}: failed")
        _run_status[run_id] = {"status": "failed", "area_id": area_id, "total_flags": 0}
    finally:
        db.close()


# --- Endpoints ---

@router.post("/run", status_code=202)
def trigger_review_run(
    body: GLReviewRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Trigger a GL anomaly detection run. Returns immediately with run_id."""
    # Validate area exists
    area = db.query(Area).filter(Area.id == body.area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail=f"Area {body.area_id} not found")

    run_id = str(uuid.uuid4())

    # Supersede all open flags for this area with overlapping period
    existing = (
        db.query(GLAnomalyFlag)
        .filter(
            GLAnomalyFlag.area_id == body.area_id,
            GLAnomalyFlag.status == STATUS_OPEN,
            GLAnomalyFlag.period_date >= body.date_from,
            GLAnomalyFlag.period_date <= body.date_to,
        )
        .all()
    )
    for flag in existing:
        flag.status = STATUS_SUPERSEDED
    if existing:
        db.commit()
        logger.info(f"Superseded {len(existing)} existing flags for area_id={body.area_id}")

    # Launch detection in a real background thread (not BackgroundTasks which
    # blocks the worker thread for sync functions like the Anthropic API call)
    thread = threading.Thread(
        target=_run_detection_background,
        args=(run_id, body.area_id, area.name, body.date_from, body.date_to, body.use_ai),
        daemon=True,
    )
    thread.start()

    return GLReviewRunResponse(
        run_id=run_id,
        area_id=body.area_id,
        total_flags=0,
        by_severity={},
        by_flag_type={},
    )


@router.get("/runs/{run_id}")
def get_run_summary(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Get summary of a detection run. Returns status while in progress."""
    run_info = _run_status.get(run_id)

    # If still running, return 202 with progress info (not 404)
    if run_info and run_info["status"] == "running":
        return GLReviewRunResponse(
            run_id=run_id,
            area_id=run_info["area_id"],
            status="running",
            step=run_info.get("step", ""),
            total_flags=0,
            by_severity={},
            by_flag_type={},
        )

    # If failed, report it
    if run_info and run_info["status"] == "failed":
        _run_status.pop(run_id, None)
        raise HTTPException(status_code=500, detail="Detection run failed — check server logs")

    # Completed — load from DB
    flags = db.query(GLAnomalyFlag).filter(GLAnomalyFlag.run_id == run_id).all()
    if not flags and not run_info:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    _run_status.pop(run_id, None)  # Clean up

    area_id = flags[0].area_id if flags else run_info["area_id"]
    severity_counts = Counter(f.severity for f in flags)
    type_counts = Counter(f.flag_type for f in flags)

    return GLReviewRunResponse(
        run_id=run_id,
        area_id=area_id,
        status="completed",
        total_flags=len(flags),
        by_severity=dict(severity_counts),
        by_flag_type=dict(type_counts),
    )


@router.get("/flags", response_model=PaginatedFlagsResponse)
def list_flags(
    area_id: int = Query(..., description="Area ID to filter by"),
    status: str = Query(None, description="Filter by status"),
    severity: str = Query(None, description="Filter by severity"),
    flag_type: str = Query(None, description="Filter by flag type"),
    period_from: date = Query(None, description="Period date from"),
    period_to: date = Query(None, description="Period date to"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """List flags for an area with pagination and filters."""
    query = db.query(GLAnomalyFlag).filter(GLAnomalyFlag.area_id == area_id)

    # Exclude superseded by default
    if status:
        query = query.filter(GLAnomalyFlag.status == status)
    else:
        query = query.filter(GLAnomalyFlag.status != STATUS_SUPERSEDED)

    if severity:
        query = query.filter(GLAnomalyFlag.severity == severity)
    if flag_type:
        query = query.filter(GLAnomalyFlag.flag_type == flag_type)
    if period_from:
        query = query.filter(GLAnomalyFlag.period_date >= period_from)
    if period_to:
        query = query.filter(GLAnomalyFlag.period_date <= period_to)

    # Order: critical first, then warning, then info; newest first within each
    severity_order = case(
        (GLAnomalyFlag.severity == SEVERITY_CRITICAL, 0),
        (GLAnomalyFlag.severity == SEVERITY_WARNING, 1),
        (GLAnomalyFlag.severity == SEVERITY_INFO, 2),
        else_=3,
    )
    query = query.order_by(severity_order, desc(GLAnomalyFlag.created_at))

    total = query.count()
    pages = math.ceil(total / per_page) if total > 0 else 1
    items = query.offset((page - 1) * per_page).limit(per_page).all()

    return PaginatedFlagsResponse(
        items=[GLFlagResponse.model_validate(f) for f in items],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/flags/{flag_id}", response_model=GLFlagResponse)
def get_flag_detail(
    flag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Get a single flag by ID."""
    flag = db.query(GLAnomalyFlag).filter(GLAnomalyFlag.id == flag_id).first()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    return GLFlagResponse.model_validate(flag)


@router.patch("/flags/{flag_id}/review", response_model=GLFlagResponse)
def review_flag(
    flag_id: int,
    body: GLFlagReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Review/dismiss/escalate a flag."""
    flag = db.query(GLAnomalyFlag).filter(GLAnomalyFlag.id == flag_id).first()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")

    flag.status = body.status
    flag.review_note = body.review_note
    flag.reviewed_by = user.id
    flag.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(flag)

    return GLFlagResponse.model_validate(flag)


@router.post("/flags/bulk-review")
def bulk_review_flags(
    body: GLFlagBulkReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Bulk update status for multiple flags."""
    now = datetime.now(timezone.utc)
    updated = (
        db.query(GLAnomalyFlag)
        .filter(GLAnomalyFlag.id.in_(body.flag_ids))
        .update(
            {
                GLAnomalyFlag.status: body.status,
                GLAnomalyFlag.review_note: body.review_note,
                GLAnomalyFlag.reviewed_by: user.id,
                GLAnomalyFlag.reviewed_at: now,
            },
            synchronize_session='fetch',
        )
    )
    db.commit()
    return {"updated": updated}


@router.get("/baselines/{area_id}", response_model=list[GLBaselineResponse])
def get_baselines(
    area_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Get baseline stats for all accounts for an area."""
    baselines = (
        db.query(GLAccountBaseline)
        .filter(GLAccountBaseline.area_id == area_id)
        .order_by(GLAccountBaseline.account_code)
        .all()
    )
    return [GLBaselineResponse.model_validate(b) for b in baselines]


@router.post("/baselines/{area_id}/rebuild")
def rebuild_baselines(
    area_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Rebuild baselines for an area. Requires admin."""
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail=f"Area {area_id} not found")

    count = compute_baselines(db, area_id)
    return {"area_id": area_id, "accounts_processed": count}


@router.get("/summary/{area_id}", response_model=GLReviewSummaryResponse)
def get_review_summary(
    area_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Dashboard summary: open flags, trends, top accounts."""
    # Open flags by severity
    open_counts = (
        db.query(GLAnomalyFlag.severity, sqlfunc.count())
        .filter(
            GLAnomalyFlag.area_id == area_id,
            GLAnomalyFlag.status == STATUS_OPEN,
        )
        .group_by(GLAnomalyFlag.severity)
        .all()
    )
    open_flags = {sev: cnt for sev, cnt in open_counts}

    # Last run date
    last_flag = (
        db.query(GLAnomalyFlag.created_at)
        .filter(GLAnomalyFlag.area_id == area_id)
        .order_by(desc(GLAnomalyFlag.created_at))
        .first()
    )
    last_run_date = last_flag[0] if last_flag else None

    # Top 5 recurring flag types (all time, non-superseded)
    top_types = (
        db.query(GLAnomalyFlag.flag_type, sqlfunc.count().label('cnt'))
        .filter(
            GLAnomalyFlag.area_id == area_id,
            GLAnomalyFlag.status != STATUS_SUPERSEDED,
        )
        .group_by(GLAnomalyFlag.flag_type)
        .order_by(desc('cnt'))
        .limit(5)
        .all()
    )
    top_flag_types = [{"flag_type": ft, "count": cnt} for ft, cnt in top_types]

    # Top 5 flagged accounts
    top_accounts_q = (
        db.query(
            GLAnomalyFlag.account_id,
            Account.account_name,
            sqlfunc.count().label('cnt'),
        )
        .outerjoin(Account, GLAnomalyFlag.account_id == Account.id)
        .filter(
            GLAnomalyFlag.area_id == area_id,
            GLAnomalyFlag.status != STATUS_SUPERSEDED,
            GLAnomalyFlag.account_id.isnot(None),
        )
        .group_by(GLAnomalyFlag.account_id, Account.account_name)
        .order_by(desc('cnt'))
        .limit(5)
        .all()
    )
    top_flagged_accounts = [
        {"account_id": aid, "account_name": aname or f"Account #{aid}", "count": cnt}
        for aid, aname, cnt in top_accounts_q
    ]

    # Trend: this month vs last month
    today = date.today()
    this_month_start = date(today.year, today.month, 1)
    if today.month == 1:
        last_month_start = date(today.year - 1, 12, 1)
    else:
        last_month_start = date(today.year, today.month - 1, 1)
    last_month_end = this_month_start - timedelta(days=1)

    this_month_count = (
        db.query(sqlfunc.count())
        .select_from(GLAnomalyFlag)
        .filter(
            GLAnomalyFlag.area_id == area_id,
            GLAnomalyFlag.status != STATUS_SUPERSEDED,
            GLAnomalyFlag.created_at >= this_month_start,
        )
        .scalar() or 0
    )

    last_month_count = (
        db.query(sqlfunc.count())
        .select_from(GLAnomalyFlag)
        .filter(
            GLAnomalyFlag.area_id == area_id,
            GLAnomalyFlag.status != STATUS_SUPERSEDED,
            GLAnomalyFlag.created_at >= last_month_start,
            GLAnomalyFlag.created_at < this_month_start,
        )
        .scalar() or 0
    )

    return GLReviewSummaryResponse(
        area_id=area_id,
        open_flags=open_flags,
        last_run_date=last_run_date,
        top_flag_types=top_flag_types,
        top_flagged_accounts=top_flagged_accounts,
        this_month_count=this_month_count,
        last_month_count=last_month_count,
    )
