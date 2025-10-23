"""
Restaurant Accounting System - Main Application
"""
from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from pathlib import Path

from accounting.core.config import settings
from accounting.db.database import get_db
from accounting.api.accounts import router as accounts_router
from accounting.api.journal_entries import router as journal_entries_router
from accounting.api.fiscal_periods import router as fiscal_periods_router
from accounting.api.reports import router as reports_router
from accounting.api.auth import router as auth_router, get_current_user, require_auth
from accounting.api.users import router as users_router
from accounting.api.roles import router as roles_router
from accounting.api.areas import router as areas_router
from accounting.api.vendor_bills import router as vendor_bills_router
from accounting.api.ap_reports import router as ap_reports_router
from accounting.api.daily_sales_summary import router as dss_router
from accounting.api.vendors import router as vendors_router
from accounting.api.customers import router as customers_router
from accounting.api.customer_invoices import router as customer_invoices_router
from accounting.api.bank_accounts import router as bank_accounts_router
from accounting.api.bank_reconciliation import router as bank_reconciliation_router
from accounting.api.bank_statements import router as bank_statements_router
from accounting.api.composite_matching import router as composite_matching_router
from accounting.api.banking_dashboard import router as banking_dashboard_router
from accounting.api.general_dashboard import router as general_dashboard_router
from accounting.api.payments import router as payments_router
from accounting.api.budgets import router as budgets_router
from accounting.models.user import User
# Import all models to ensure they are registered
import accounting.models  # noqa

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Restaurant Accounting System - Separate microservice for financial management",
    root_path="/accounting"
)

# Setup templates and static files
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/accounting/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(roles_router)
app.include_router(areas_router)
app.include_router(accounts_router)
app.include_router(journal_entries_router)
app.include_router(fiscal_periods_router)
app.include_router(reports_router)
app.include_router(vendors_router)
app.include_router(vendor_bills_router)
app.include_router(ap_reports_router)
app.include_router(customers_router)
app.include_router(customer_invoices_router)
app.include_router(dss_router)
app.include_router(bank_accounts_router, prefix="/api/bank-accounts", tags=["Banking"])
app.include_router(bank_reconciliation_router, prefix="/api/bank-reconciliation", tags=["Banking"])
app.include_router(bank_statements_router, prefix="/api/bank-statements", tags=["Banking"])
app.include_router(composite_matching_router, prefix="/api/bank-transactions", tags=["Banking - Composite Matching"])
app.include_router(banking_dashboard_router, prefix="/api/banking-dashboard", tags=["Banking - Dashboard"])
app.include_router(general_dashboard_router)
app.include_router(payments_router, prefix="/api/payments", tags=["Payments"])
app.include_router(budgets_router, prefix="/api/budgets", tags=["Budgets"])


# Custom exception handler for authentication redirects
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions - redirect 401 to Portal login for HTML requests"""
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        # Check if this is an HTML request (not API)
        accept = request.headers.get("accept", "")
        if "text/html" in accept or "/accounting/" in request.url.path:
            # Redirect to Portal login instead of local login
            return RedirectResponse(url="/portal/login?redirect=/accounting/", status_code=302)
    # For API requests or other errors, return JSON response
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# Health check endpoint
@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint with database connectivity test"""
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy" if settings.ACCOUNTING_ENABLED else "disabled",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db_status,
        "accounting_enabled": settings.ACCOUNTING_ENABLED,
        "auto_sync_enabled": settings.AUTO_SYNC_ENABLED
    }

# Login page
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Login page"""
    # Check if already logged in
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/accounting/", status_code=302)

    return templates.TemplateResponse("login.html", {"request": request})


# Root endpoint - Dashboard
@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Dashboard page (protected) - General Accounting Dashboard"""
    return templates.TemplateResponse("general_dashboard.html", {
        "request": request,
        "current_user": user
    })


# Frontend Pages (all protected)
@app.get("/accounts", response_class=HTMLResponse)
async def accounts_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Chart of Accounts page"""
    return templates.TemplateResponse("chart_of_accounts.html", {
        "request": request,
        "current_user": user
    })


@app.get("/accounts/{account_id}", response_class=HTMLResponse)
async def account_detail_page(
    request: Request,
    account_id: int,
    user: User = Depends(require_auth)
):
    """Account Detail page with transaction history"""
    return templates.TemplateResponse("account_detail.html", {
        "request": request,
        "current_user": user,
        "account_id": account_id
    })


@app.get("/journal-entries", response_class=HTMLResponse)
async def journal_entries_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Journal Entries page"""
    return templates.TemplateResponse("journal_entries.html", {
        "request": request,
        "current_user": user
    })


@app.get("/periods", response_class=HTMLResponse)
async def periods_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Fiscal Periods page"""
    return templates.TemplateResponse("fiscal_periods.html", {
        "request": request,
        "current_user": user
    })


@app.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """User Management page (admin only)"""
    from accounting.api.auth import require_admin
    # Check admin access
    try:
        require_admin(user)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to access user management"
        )

    return templates.TemplateResponse("users.html", {
        "request": request,
        "current_user": user
    })


@app.get("/roles", response_class=HTMLResponse)
async def roles_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Role Management page (admin only)"""
    from accounting.api.auth import require_admin
    # Check admin access
    try:
        require_admin(user)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to access role management"
        )

    return templates.TemplateResponse("roles.html", {
        "request": request,
        "current_user": user
    })


@app.get("/areas", response_class=HTMLResponse)
async def areas_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Area Management page (admin only)"""
    from accounting.api.auth import require_admin
    # Check admin access
    try:
        require_admin(user)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to access area management"
        )

    return templates.TemplateResponse("locations.html", {
        "request": request,
        "current_user": user
    })


@app.get("/locations", response_class=HTMLResponse)
async def locations_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Locations/Entities Management page (admin only) - alias for /areas"""
    from accounting.api.auth import require_admin
    # Check admin access
    try:
        require_admin(user)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to access location management"
        )

    return templates.TemplateResponse("locations.html", {
        "request": request,
        "current_user": user
    })


@app.get("/vendors", response_class=HTMLResponse)
async def vendors_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Vendors page"""
    return templates.TemplateResponse("vendors.html", {
        "request": request,
        "current_user": user
    })


@app.get("/customers", response_class=HTMLResponse)
async def customers_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Customers page"""
    return templates.TemplateResponse("customers.html", {
        "request": request,
        "current_user": user
    })


@app.get("/customer-invoices", response_class=HTMLResponse)
async def customer_invoices_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Customer Invoices page"""
    return templates.TemplateResponse("customer_invoices.html", {
        "request": request,
        "current_user": user
    })


@app.get("/vendor-bills", response_class=HTMLResponse)
async def vendor_bills_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Vendor Bills (Accounts Payable) page"""
    return templates.TemplateResponse("vendor_bills.html", {
        "request": request,
        "current_user": user
    })


@app.get("/vendor-bills/{bill_id}", response_class=HTMLResponse)
async def vendor_bill_detail_page(
    bill_id: int,
    request: Request,
    user: User = Depends(require_auth)
):
    """Vendor Bill Detail page"""
    return templates.TemplateResponse("vendor_bill_detail.html", {
        "request": request,
        "current_user": user,
        "bill_id": bill_id
    })


@app.get("/payments", response_class=HTMLResponse)
async def payments_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Create Payment page"""
    return templates.TemplateResponse("payments.html", {
        "request": request,
        "current_user": user
    })


@app.get("/payment-history", response_class=HTMLResponse)
async def payment_history_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Payment History page"""
    return templates.TemplateResponse("payment_history.html", {
        "request": request,
        "current_user": user
    })


@app.get("/check-batches", response_class=HTMLResponse)
async def check_batches_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Check Batches page"""
    return templates.TemplateResponse("check_batches.html", {
        "request": request,
        "current_user": user
    })


@app.get("/ach-batches", response_class=HTMLResponse)
async def ach_batches_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """ACH Batches page"""
    return templates.TemplateResponse("ach_batches.html", {
        "request": request,
        "current_user": user
    })


@app.get("/daily-sales", response_class=HTMLResponse)
async def daily_sales_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Daily Sales Summary page"""
    return templates.TemplateResponse("daily_sales.html", {
        "request": request,
        "current_user": user
    })


@app.get("/daily-sales/new", response_class=HTMLResponse)
async def daily_sales_new_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Create new Daily Sales Entry"""
    return templates.TemplateResponse("daily_sales_detail.html", {
        "request": request,
        "current_user": user,
        "dss_id": "new"
    })


@app.get("/daily-sales/{dss_id}", response_class=HTMLResponse)
async def daily_sales_detail_page(
    dss_id: int,
    request: Request,
    user: User = Depends(require_auth)
):
    """Daily Sales Entry Detail page"""
    return templates.TemplateResponse("daily_sales_detail.html", {
        "request": request,
        "current_user": user,
        "dss_id": dss_id
    })


@app.get("/budgets", response_class=HTMLResponse)
async def budgets_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Budget Management page"""
    return templates.TemplateResponse("budgets.html", {
        "request": request,
        "current_user": user
    })


@app.get("/budgets/{budget_id}/vs-actual", response_class=HTMLResponse)
async def budget_vs_actual_page(
    budget_id: int,
    request: Request,
    user: User = Depends(require_auth)
):
    """Budget vs Actual Report page"""
    return templates.TemplateResponse("budget_vs_actual.html", {
        "request": request,
        "current_user": user,
        "budget_id": budget_id
    })


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Reports page - Trial Balance, General Ledger, etc."""
    return templates.TemplateResponse("reports.html", {
        "request": request,
        "current_user": user
    })


@app.get("/cash-flow-statement", response_class=HTMLResponse)
async def cash_flow_statement_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Cash Flow Statement page"""
    return templates.TemplateResponse("cash_flow_statement.html", {
        "request": request,
        "current_user": user
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Settings page (admin only)"""
    from accounting.api.auth import require_admin
    # Check admin access
    try:
        require_admin(user)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to access settings"
        )

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "current_user": user
    })


@app.get("/bank-accounts", response_class=HTMLResponse)
async def bank_accounts_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Bank Accounts page"""
    return templates.TemplateResponse("bank_accounts.html", {
        "request": request,
        "current_user": user
    })


@app.get("/bank-accounts/{account_id}", response_class=HTMLResponse)
async def bank_account_detail_page(
    account_id: int,
    request: Request,
    user: User = Depends(require_auth)
):
    """Bank Account Detail page with transactions"""
    return templates.TemplateResponse("bank_account_detail.html", {
        "request": request,
        "current_user": user,
        "account_id": account_id
    })


@app.get("/banking-dashboard", response_class=HTMLResponse)
async def banking_dashboard_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Banking dashboard overview - Phase 1 comprehensive dashboard"""
    return templates.TemplateResponse("banking_dashboard_v2.html", {
        "request": request,
        "current_user": user
    })


@app.get("/bank-reconciliation", response_class=HTMLResponse)
async def bank_reconciliation_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Transaction-first bank reconciliation page"""
    return templates.TemplateResponse("bank_reconciliation.html", {
        "request": request,
        "current_user": user
    })


@app.get("/reconciliations", response_class=HTMLResponse)
async def reconciliations_page(
    request: Request,
    user: User = Depends(require_auth)
):
    """Bank Reconciliations list page"""
    return templates.TemplateResponse("reconciliations.html", {
        "request": request,
        "current_user": user
    })


@app.get("/reconciliations/{reconciliation_id}", response_class=HTMLResponse)
async def reconciliation_workspace_page(
    reconciliation_id: int,
    request: Request,
    user: User = Depends(require_auth)
):
    """Reconciliation workspace page"""
    return templates.TemplateResponse("reconciliation_workspace.html", {
        "request": request,
        "current_user": user,
        "reconciliation_id": reconciliation_id
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
