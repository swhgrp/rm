"""
Daily Automated Accounting Review

Runs all checks from REVIEW_SPEC.md (Sections 1-5E) against
Accounting, Hub, and Inventory databases. Stores findings in
daily_review_runs / daily_review_findings tables and emails
a summary report to admin@swhgrp.com.

Phase 1: Read-only audit + flagging. No auto-corrections.
"""

import logging
import os
import uuid
import json
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any

from sqlalchemy import create_engine, text, func, and_, or_
from sqlalchemy.orm import Session

from accounting.db.database import SessionLocal, Base
from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.vendor_bill import VendorBill, VendorBillLine, BillStatus
from accounting.models.daily_sales_summary import DailySalesSummary
from accounting.models.account import Account
from accounting.models.area import Area
from accounting.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REVIEW_WINDOW_HOURS = 48
REPORT_EMAIL = "admin@swhgrp.com"

BEVERAGE_VENDOR_PATTERNS = [
    "Southern Glazer%",
    "Southern Glazier%",
    "Southern Eagle%",
    "Gold Coast Beverage%",
    "Breakthru%",
    "Western Beverage%",
    "Eagle Brands%",
    "Republic National%",
    "J.J. Taylor%",
    "Double Eagle%",
]

DELIVERY_FEE_PATTERNS = [
    "DELIVERY", "FUEL SURCHARGE", "FREIGHT", "SHIPPING",
    "TRANSPORTATION", "HANDLING",
]

# ---------------------------------------------------------------------------
# Cross-DB engine helpers (lazy singletons)
# ---------------------------------------------------------------------------

_hub_engine = None
_inv_engine = None

HUB_DATABASE_URL = os.getenv(
    "HUB_DATABASE_URL",
    "postgresql://hub_user:hub_password@hub-db:5432/integration_hub_db"
)
INVENTORY_DATABASE_URL = os.getenv(
    "INVENTORY_DATABASE_URL",
    "postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db"
)


def get_hub_engine():
    global _hub_engine
    if _hub_engine is None:
        _hub_engine = create_engine(
            HUB_DATABASE_URL,
            pool_size=3, max_overflow=5,
            pool_pre_ping=True, pool_recycle=300,
        )
    return _hub_engine


def get_inv_engine():
    global _inv_engine
    if _inv_engine is None:
        _inv_engine = create_engine(
            INVENTORY_DATABASE_URL,
            pool_size=3, max_overflow=5,
            pool_pre_ping=True, pool_recycle=300,
        )
    return _inv_engine


# ---------------------------------------------------------------------------
# Finding helper
# ---------------------------------------------------------------------------

class Finding:
    """Lightweight container for a review finding."""

    def __init__(
        self,
        section: str,
        check_name: str,
        severity: str,
        title: str,
        detail: str = "",
        record_type: str = None,
        record_id: int = None,
        record_id_secondary: int = None,
        area_id: int = None,
        flagged_value: float = None,
        expected_value: float = None,
    ):
        self.section = section
        self.check_name = check_name
        self.severity = severity
        self.title = title
        self.detail = detail
        self.record_type = record_type
        self.record_id = record_id
        self.record_id_secondary = record_id_secondary
        self.area_id = area_id
        self.flagged_value = flagged_value
        self.expected_value = expected_value


def _run_section(name: str, fn, *args, db: Session = None) -> List[Finding]:
    """Run a check function, catching and logging errors.
    If db is provided, rollback on error to keep the session usable."""
    try:
        results = fn(*args)
        logger.info(f"Section [{name}]: {len(results)} finding(s)")
        return results
    except Exception:
        logger.exception(f"Section [{name}] failed")
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        return [Finding(
            section=name, check_name="infrastructure_error",
            severity="warning",
            title=f"Section {name} failed to run",
            detail=f"Check logs for traceback",
        )]


# ===================================================================
# Section 1 — Invoice Accuracy (Hub DB)
# ===================================================================

def check_invoice_accuracy(hub_engine, review_window: datetime) -> List[Finding]:
    findings: List[Finding] = []

    with hub_engine.connect() as conn:
        # --- Total mismatch ---
        rows = conn.execute(text("""
            SELECT i.id, i.vendor_name, i.invoice_number, i.total_amount,
                   i.tax_amount,
                   COALESCE(SUM(it.total_amount), 0) as items_total,
                   COUNT(it.id) as item_count
            FROM hub_invoices i
            LEFT JOIN hub_invoice_items it ON it.invoice_id = i.id
            WHERE i.created_at >= :window
              AND i.status NOT IN ('pending', 'parsing', 'parse_failed', 'statement')
              AND i.is_statement = false
            GROUP BY i.id, i.vendor_name, i.invoice_number, i.total_amount, i.tax_amount
            HAVING ABS(i.total_amount - COALESCE(SUM(it.total_amount), 0)) > 0.10
        """), {"window": review_window}).fetchall()

        for r in rows:
            inv_id, vendor, inv_num, total, tax, items_total, item_count = r
            diff = float(total) - float(items_total)
            findings.append(Finding(
                section="invoice_accuracy", check_name="total_mismatch",
                severity="critical" if abs(diff) > 5.0 else "warning",
                title=f"Invoice {inv_num} ({vendor}): items ${items_total} vs total ${total} (diff ${diff:.2f})",
                record_type="hub_invoice", record_id=inv_id,
                flagged_value=float(items_total), expected_value=float(total),
            ))

        # --- Unit price outlier (>40% from 90-day avg, >=3 samples) ---
        rows = conn.execute(text("""
            WITH avg_prices AS (
                SELECT it2.inventory_item_id,
                       AVG(it2.unit_price) as avg_price,
                       COUNT(*) as sample_count
                FROM hub_invoice_items it2
                JOIN hub_invoices i2 ON it2.invoice_id = i2.id
                WHERE it2.inventory_item_id IS NOT NULL
                  AND i2.created_at >= NOW() - INTERVAL '90 days'
                  AND it2.unit_price > 0
                GROUP BY it2.inventory_item_id
                HAVING COUNT(*) >= 3
            )
            SELECT it.id, it.invoice_id, i.vendor_name, i.invoice_number,
                   it.item_description, it.unit_price, ap.avg_price
            FROM hub_invoice_items it
            JOIN hub_invoices i ON it.invoice_id = i.id
            JOIN avg_prices ap ON it.inventory_item_id = ap.inventory_item_id
            WHERE i.created_at >= :window
              AND i.status NOT IN ('pending', 'parsing', 'parse_failed')
              AND ap.avg_price > 0
              AND ABS(it.unit_price - ap.avg_price) / ap.avg_price > 0.40
        """), {"window": review_window}).fetchall()

        for r in rows:
            item_id, inv_id, vendor, inv_num, desc, price, avg = r
            pct = ((float(price) - float(avg)) / float(avg)) * 100
            findings.append(Finding(
                section="invoice_accuracy", check_name="unit_price_outlier",
                severity="warning",
                title=f"Price outlier: {desc} on {inv_num} ({vendor}) — ${price} vs avg ${avg:.2f} ({pct:+.0f}%)",
                record_type="hub_invoice_item", record_id=item_id,
                record_id_secondary=inv_id,
                flagged_value=float(price), expected_value=float(avg),
            ))

        # --- Quantity implausible ---
        rows = conn.execute(text("""
            SELECT it.id, it.invoice_id, i.vendor_name, i.invoice_number,
                   it.item_description, it.quantity
            FROM hub_invoice_items it
            JOIN hub_invoices i ON it.invoice_id = i.id
            WHERE i.created_at >= :window
              AND i.status NOT IN ('pending', 'parsing', 'parse_failed')
              AND (it.quantity <= 0 OR it.quantity > 500)
        """), {"window": review_window}).fetchall()

        for r in rows:
            item_id, inv_id, vendor, inv_num, desc, qty = r
            findings.append(Finding(
                section="invoice_accuracy", check_name="qty_implausible",
                severity="warning",
                title=f"Implausible qty {qty} for '{desc}' on {inv_num} ({vendor})",
                record_type="hub_invoice_item", record_id=item_id,
                record_id_secondary=inv_id,
                flagged_value=float(qty),
            ))

    return findings


# ===================================================================
# Section 2 — GL Entry Verification (Accounting DB)
# ===================================================================

def check_gl_integrity(db: Session, review_window: datetime) -> List[Finding]:
    findings: List[Finding] = []

    # --- Unbalanced JEs (all types) ---
    rows = (
        db.query(
            JournalEntry.id,
            JournalEntry.entry_number,
            JournalEntry.reference_type,
            JournalEntry.description,
            func.sum(JournalEntryLine.debit_amount).label("debits"),
            func.sum(JournalEntryLine.credit_amount).label("credits"),
        )
        .join(JournalEntryLine)
        .filter(
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.created_at >= review_window,
        )
        .group_by(JournalEntry.id, JournalEntry.entry_number,
                   JournalEntry.reference_type, JournalEntry.description)
        .having(
            func.abs(func.sum(JournalEntryLine.debit_amount) -
                     func.sum(JournalEntryLine.credit_amount)) > 0.01
        )
        .all()
    )

    for je_id, entry_num, ref_type, desc, debits, credits in rows:
        diff = float(debits or 0) - float(credits or 0)
        findings.append(Finding(
            section="gl_integrity", check_name="unbalanced_je",
            severity="critical",
            title=f"Unbalanced JE {entry_num} ({ref_type or 'manual'}): DR ${debits} / CR ${credits} (diff ${diff:.2f})",
            detail=desc or "",
            record_type="journal_entry", record_id=je_id,
        ))

    # --- Corporate area_id=7 on vendor bill JEs ---
    rows = (
        db.query(
            JournalEntry.id, JournalEntry.entry_number,
            JournalEntryLine.id, JournalEntryLine.area_id,
        )
        .join(JournalEntryLine)
        .filter(
            JournalEntry.reference_type == "VENDOR_BILL",
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntryLine.area_id == 7,
            JournalEntry.created_at >= review_window,
        )
        .all()
    )

    for je_id, entry_num, line_id, area_id in rows:
        findings.append(Finding(
            section="gl_integrity", check_name="corporate_area_on_ap",
            severity="critical",
            title=f"JE {entry_num} has area_id=7 (Corporate) on vendor bill line — should be location 1-6",
            record_type="journal_entry_line", record_id=line_id,
            record_id_secondary=je_id, area_id=7,
        ))

    # --- Inactive account used ---
    rows = (
        db.query(
            JournalEntry.id, JournalEntry.entry_number,
            Account.account_number, Account.account_name,
        )
        .join(JournalEntryLine, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .join(Account, JournalEntryLine.account_id == Account.id)
        .filter(
            Account.is_active == False,
            JournalEntry.created_at >= review_window,
            JournalEntry.status == JournalEntryStatus.POSTED,
        )
        .distinct()
        .all()
    )

    for je_id, entry_num, acct_num, acct_name in rows:
        findings.append(Finding(
            section="gl_integrity", check_name="inactive_account_used",
            severity="warning",
            title=f"Inactive account {acct_num} ({acct_name}) used in JE {entry_num}",
            record_type="journal_entry", record_id=je_id,
        ))

    # --- Large manual entry (>$5000, non-system) ---
    system_ref_types = ("VENDOR_BILL", "SALE", "PAYMENT", "TRANSFER", "WASTE", "INVOICE")
    rows = (
        db.query(
            JournalEntry.id, JournalEntry.entry_number,
            JournalEntry.description,
            func.greatest(
                func.max(JournalEntryLine.debit_amount),
                func.max(JournalEntryLine.credit_amount)
            ).label("max_amount"),
        )
        .join(JournalEntryLine)
        .filter(
            JournalEntry.created_at >= review_window,
            JournalEntry.status == JournalEntryStatus.POSTED,
            or_(
                JournalEntry.reference_type == None,
                ~JournalEntry.reference_type.in_(system_ref_types),
            ),
        )
        .group_by(JournalEntry.id, JournalEntry.entry_number, JournalEntry.description)
        .having(
            func.greatest(
                func.max(JournalEntryLine.debit_amount),
                func.max(JournalEntryLine.credit_amount)
            ) > 5000
        )
        .all()
    )

    for je_id, entry_num, desc, max_amt in rows:
        findings.append(Finding(
            section="gl_integrity", check_name="large_manual_entry",
            severity="warning",
            title=f"Large manual JE {entry_num}: ${max_amt:,.2f} — {desc or 'no description'}",
            record_type="journal_entry", record_id=je_id,
            flagged_value=float(max_amt),
        ))

    # --- Open GL anomaly flags (summary count only — details in GL Review UI) ---
    try:
        from accounting.gl_review.models import GLAnomalyFlag, STATUS_OPEN
        open_count = (
            db.query(func.count(GLAnomalyFlag.id))
            .filter(GLAnomalyFlag.status == STATUS_OPEN)
            .scalar()
        )
        if open_count > 0:
            findings.append(Finding(
                section="gl_integrity", check_name="open_anomaly_flags_summary",
                severity="info",
                title=f"{open_count} open GL anomaly flag(s) from nightly sweep — see GL Review page for details",
            ))
    except Exception:
        logger.debug("GL anomaly flag table not available, skipping")

    return findings


# ===================================================================
# Section 3 — Inventory Cost Consistency (Hub + Inventory)
# ===================================================================

def check_inventory_costs(hub_engine, inv_engine, review_window: datetime) -> List[Finding]:
    findings: List[Finding] = []

    # Get recently sent invoices with mapped items from Hub
    with hub_engine.connect() as hub_conn:
        sent_items = hub_conn.execute(text("""
            SELECT DISTINCT it.inventory_item_id, i.location_id, i.id as invoice_id,
                   i.vendor_name, i.invoice_number, i.created_at
            FROM hub_invoices i
            JOIN hub_invoice_items it ON it.invoice_id = i.id
            WHERE i.status IN ('sent', 'ready')
              AND i.created_at >= :window
              AND it.inventory_item_id IS NOT NULL
              AND it.is_mapped = true
              AND i.location_id IS NOT NULL
        """), {"window": review_window}).fetchall()

    if not sent_items:
        return findings

    # Hub inventory_item_id points to hub_vendor_items, which has master_item_id
    # We need to map: hub_vendor_item_id → master_item_id for inventory lookup
    vi_ids = list({item[0] for item in sent_items})
    vi_to_master = {}
    with hub_engine.connect() as hub_conn2:
        for batch_start in range(0, len(vi_ids), 100):
            batch = vi_ids[batch_start:batch_start+100]
            rows = hub_conn2.execute(text("""
                SELECT id, inventory_master_item_id FROM hub_vendor_items
                WHERE id = ANY(:ids) AND inventory_master_item_id IS NOT NULL
            """), {"ids": batch}).fetchall()
            for r in rows:
                vi_to_master[r[0]] = r[1]

    # Check cost updates in Inventory DB
    with inv_engine.connect() as inv_conn:
        for item in sent_items:
            vi_id, loc_id, inv_id, vendor, inv_num, created_at = item
            master_id = vi_to_master.get(vi_id)
            if not master_id:
                continue

            cost_row = inv_conn.execute(text("""
                SELECT last_purchase_cost, last_updated
                FROM master_item_location_costs
                WHERE master_item_id = :mid AND location_id = :loc_id
            """), {"mid": master_id, "loc_id": loc_id}).fetchone()

            if cost_row and cost_row[1]:
                updated_at = cost_row[1]
                # Make both timezone-naive for comparison
                now = datetime.now()
                if hasattr(updated_at, 'tzinfo') and updated_at.tzinfo is not None:
                    updated_at = updated_at.replace(tzinfo=None)
                lag_hours = (now - updated_at).total_seconds() / 3600
                if lag_hours > 24:
                    findings.append(Finding(
                        section="inventory_costs", check_name="cost_not_updated",
                        severity="warning",
                        title=f"Cost not updated for master item {master_id} at location {loc_id} — last update {lag_hours:.0f}h ago",
                        detail=f"Invoice {inv_num} ({vendor}) processed but cost stale",
                        record_type="hub_invoice", record_id=inv_id,
                    ))

    return findings


# ===================================================================
# Section 4 — Duplicate Payment Check (Accounting DB)
# ===================================================================

def check_duplicate_payments(db: Session, review_window: datetime) -> List[Finding]:
    findings: List[Finding] = []

    # Duplicate vendor bills (same bill_number + vendor)
    from sqlalchemy import literal_column
    rows = db.execute(text("""
        SELECT bill_number, vendor_name, COUNT(*) as cnt,
               array_agg(id ORDER BY id) as bill_ids,
               array_agg(total_amount ORDER BY id) as totals
        FROM vendor_bills
        WHERE status != 'VOID'
        GROUP BY bill_number, vendor_name
        HAVING COUNT(*) > 1
    """)).fetchall()

    for r in rows:
        bill_num, vendor, cnt, bill_ids, totals = r
        findings.append(Finding(
            section="duplicate_payments", check_name="duplicate_vendor_bills",
            severity="critical",
            title=f"Duplicate bills: {vendor} #{bill_num} — {cnt} copies (IDs: {bill_ids})",
            record_type="vendor_bill", record_id=bill_ids[0],
        ))

    return findings


# ===================================================================
# Section 5A — Hub ↔ Accounting Sync Reconciliation
# ===================================================================

def check_hub_accounting_sync(db: Session, hub_engine, review_window: datetime) -> List[Finding]:
    findings: List[Finding] = []

    # --- Vendor bill lines vs bill total ---
    rows = db.execute(text("""
        SELECT vb.id, vb.bill_number, vb.vendor_name, vb.total_amount,
               COALESCE(SUM(vbl.amount), 0) as lines_total
        FROM vendor_bills vb
        LEFT JOIN vendor_bill_lines vbl ON vbl.bill_id = vb.id
        WHERE vb.status != 'VOID'
          AND vb.created_at >= :window
        GROUP BY vb.id, vb.bill_number, vb.vendor_name, vb.total_amount
        HAVING ABS(vb.total_amount - COALESCE(SUM(vbl.amount), 0)) > 0.10
    """), {"window": review_window}).fetchall()

    for r in rows:
        bill_id, bill_num, vendor, total, lines_total = r
        diff = float(total) - float(lines_total)
        findings.append(Finding(
            section="hub_accounting_sync", check_name="bill_lines_vs_total",
            severity="critical",
            title=f"Bill {bill_num} ({vendor}): lines ${lines_total} vs total ${total} (diff ${diff:.2f})",
            record_type="vendor_bill", record_id=bill_id,
            flagged_value=float(lines_total), expected_value=float(total),
        ))

    # --- Hub sent but no accounting bill ---
    with hub_engine.connect() as hub_conn:
        hub_sent = hub_conn.execute(text("""
            SELECT id, invoice_number, vendor_name, total_amount
            FROM hub_invoices
            WHERE sent_to_accounting = true
              AND created_at >= :window
        """), {"window": review_window}).fetchall()

    if hub_sent:
        hub_refs = {f"HUB-{r[0]}": r for r in hub_sent}
        if hub_refs:
            acct_bills = db.execute(text("""
                SELECT reference_number FROM vendor_bills
                WHERE reference_number = ANY(:refs) AND status != 'VOID'
            """), {"refs": list(hub_refs.keys())}).fetchall()
            found_refs = {r[0] for r in acct_bills}

            for ref, hub_row in hub_refs.items():
                if ref not in found_refs:
                    findings.append(Finding(
                        section="hub_accounting_sync", check_name="hub_sent_no_bill",
                        severity="critical",
                        title=f"Hub invoice {hub_row[1]} ({hub_row[2]}, ${hub_row[3]}) sent but no accounting bill found",
                        record_type="hub_invoice", record_id=hub_row[0],
                    ))

    # --- Total mismatch Hub vs Accounting ---
    with hub_engine.connect() as hub_conn:
        hub_invoices = hub_conn.execute(text("""
            SELECT id, total_amount FROM hub_invoices
            WHERE sent_to_accounting = true AND created_at >= :window
        """), {"window": review_window}).fetchall()

    hub_totals = {f"HUB-{r[0]}": float(r[1]) for r in hub_invoices}
    if hub_totals:
        acct_rows = db.execute(text("""
            SELECT reference_number, total_amount FROM vendor_bills
            WHERE reference_number = ANY(:refs) AND status != 'VOID'
        """), {"refs": list(hub_totals.keys())}).fetchall()

        for ref, acct_total in acct_rows:
            hub_total = hub_totals.get(ref)
            if hub_total is not None and abs(hub_total - float(acct_total)) > 0.10:
                findings.append(Finding(
                    section="hub_accounting_sync", check_name="total_mismatch_hub_acct",
                    severity="critical",
                    title=f"Total mismatch {ref}: Hub ${hub_total} vs Accounting ${acct_total}",
                    record_type="vendor_bill",
                    flagged_value=float(acct_total), expected_value=hub_total,
                ))

    return findings


# ===================================================================
# Section 5B — Invoice Pipeline Health (Hub DB)
# ===================================================================

def check_pipeline_health(hub_engine) -> List[Finding]:
    findings: List[Finding] = []

    with hub_engine.connect() as conn:
        # --- Stale ready ---
        rows = conn.execute(text("""
            SELECT id, vendor_name, invoice_number, total_amount, updated_at
            FROM hub_invoices
            WHERE status = 'ready' AND sent_to_accounting = false
              AND updated_at < NOW() - INTERVAL '24 hours'
        """)).fetchall()
        for r in rows:
            findings.append(Finding(
                section="pipeline_health", check_name="stale_ready",
                severity="warning",
                title=f"Stale ready invoice: {r[2]} ({r[1]}, ${r[3]}) — ready since {r[4]}",
                record_type="hub_invoice", record_id=r[0],
            ))

        # --- Missing location ---
        rows = conn.execute(text("""
            SELECT id, vendor_name, invoice_number, status, total_amount
            FROM hub_invoices
            WHERE status IN ('ready', 'sent', 'needs_review') AND location_id IS NULL
        """)).fetchall()
        for r in rows:
            findings.append(Finding(
                section="pipeline_health", check_name="missing_location",
                severity="critical",
                title=f"Missing location: {r[2]} ({r[1]}, ${r[4]}) — status: {r[3]}",
                record_type="hub_invoice", record_id=r[0],
            ))

        # --- Statement misclassification ---
        rows = conn.execute(text("""
            SELECT i.id, i.vendor_name, i.invoice_number, i.total_amount,
                   COUNT(it.id) as item_count
            FROM hub_invoices i
            JOIN hub_invoice_items it ON it.invoice_id = i.id
            WHERE i.is_statement = true AND i.total_amount != 0
            GROUP BY i.id, i.vendor_name, i.invoice_number, i.total_amount
            HAVING COUNT(it.id) > 0
        """)).fetchall()
        for r in rows:
            findings.append(Finding(
                section="pipeline_health", check_name="statement_misclassification",
                severity="warning",
                title=f"Statement with items: {r[2]} ({r[1]}, ${r[3]}) has {r[4]} items",
                record_type="hub_invoice", record_id=r[0],
            ))

        # --- Stuck needs_review ---
        rows = conn.execute(text("""
            SELECT id, vendor_name, invoice_number, updated_at
            FROM hub_invoices
            WHERE status = 'needs_review'
              AND updated_at < NOW() - INTERVAL '72 hours'
        """)).fetchall()
        for r in rows:
            findings.append(Finding(
                section="pipeline_health", check_name="stuck_needs_review",
                severity="warning",
                title=f"Stuck needs_review: {r[2]} ({r[1]}) since {r[3]}",
                record_type="hub_invoice", record_id=r[0],
            ))

        # --- Credit memo without lines ---
        rows = conn.execute(text("""
            SELECT i.id, i.vendor_name, i.invoice_number, i.total_amount
            FROM hub_invoices i
            LEFT JOIN hub_invoice_items it ON it.invoice_id = i.id
            WHERE i.total_amount < 0
              AND i.status != 'statement'
              AND i.is_statement = false
            GROUP BY i.id, i.vendor_name, i.invoice_number, i.total_amount
            HAVING COUNT(it.id) = 0
        """)).fetchall()
        for r in rows:
            findings.append(Finding(
                section="pipeline_health", check_name="credit_memo_no_lines",
                severity="warning",
                title=f"Credit memo without lines: {r[2]} ({r[1]}, ${r[3]})",
                record_type="hub_invoice", record_id=r[0],
            ))

    return findings


# ===================================================================
# Section 5C — Beverage Distributor Pricing (Hub DB)
# ===================================================================

def check_beverage_pricing(hub_engine, review_window: datetime) -> List[Finding]:
    findings: List[Finding] = []

    # Build ILIKE conditions for beverage vendors
    conditions = " OR ".join([f"i.vendor_name ILIKE '{p}'" for p in BEVERAGE_VENDOR_PATTERNS])

    with hub_engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT it.id, it.invoice_id, i.vendor_name, i.invoice_number,
                   it.item_description, it.quantity, it.unit_price, it.total_amount
            FROM hub_invoice_items it
            JOIN hub_invoices i ON it.invoice_id = i.id
            WHERE i.created_at >= :window
              AND i.status NOT IN ('pending', 'parsing', 'parse_failed')
              AND ({conditions})
              AND it.quantity > 0 AND it.unit_price > 0
              AND it.total_amount = ROUND(it.quantity * it.unit_price, 2)
              AND ABS(it.quantity * it.unit_price - it.total_amount) < 0.01
        """), {"window": review_window}).fetchall()

        # For each item where total = qty*price, check if raw_data has a different line_total
        for r in rows:
            item_id, inv_id, vendor, inv_num, desc, qty, price, total = r
            # Check raw_data for the invoice
            raw = conn.execute(text(
                "SELECT raw_data FROM hub_invoices WHERE id = :id"
            ), {"id": inv_id}).fetchone()

            if raw and raw[0]:
                try:
                    raw_data = json.loads(raw[0]) if isinstance(raw[0], str) else raw[0]
                    raw_items = raw_data.get("line_items", [])
                    # Try to find matching item by description
                    for ri in raw_items:
                        ri_desc = ri.get("item_description", ri.get("description", ""))
                        ri_total = ri.get("line_total", ri.get("total_amount"))
                        if ri_desc and desc and ri_desc.strip()[:20] == desc.strip()[:20]:
                            if ri_total and abs(float(ri_total) - float(total)) > 0.05:
                                findings.append(Finding(
                                    section="beverage_pricing", check_name="discount_not_captured",
                                    severity="warning",
                                    title=f"Beverage discount lost: {desc} on {inv_num} ({vendor}) — "
                                          f"total=${total} but raw line_total=${ri_total}",
                                    record_type="hub_invoice_item", record_id=item_id,
                                    record_id_secondary=inv_id,
                                    flagged_value=float(total), expected_value=float(ri_total),
                                ))
                            break
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

    return findings


# ===================================================================
# Section 5D — Linen Service Parse Quality (Hub DB)
# ===================================================================

def check_linen_parse_quality(hub_engine, review_window: datetime) -> List[Finding]:
    findings: List[Finding] = []

    with hub_engine.connect() as conn:
        # Price/total swap: unit_price ≈ total_amount and qty > 1
        rows = conn.execute(text("""
            SELECT it.id, it.invoice_id, i.invoice_number, i.vendor_name,
                   it.item_description, it.quantity, it.unit_price, it.total_amount
            FROM hub_invoice_items it
            JOIN hub_invoices i ON it.invoice_id = i.id
            WHERE i.vendor_name ILIKE '%Gold Coast Linen%'
              AND i.created_at >= :window
              AND it.quantity > 1
              AND ABS(it.unit_price - it.total_amount) < 0.01
        """), {"window": review_window}).fetchall()

        for r in rows:
            item_id, inv_id, inv_num, vendor, desc, qty, price, total = r
            findings.append(Finding(
                section="linen_parse_quality", check_name="price_total_swap",
                severity="critical",
                title=f"Linen price/total swap: {desc} on {inv_num} — qty={qty}, price=${price}, total=${total}",
                record_type="hub_invoice_item", record_id=item_id,
                record_id_secondary=inv_id,
                flagged_value=float(price), expected_value=float(total) / float(qty) if qty else None,
            ))

    return findings


# ===================================================================
# Section 5E — Delivery Fee Completeness (Hub DB)
# ===================================================================

def check_delivery_fee_completeness(hub_engine, review_window: datetime) -> List[Finding]:
    findings: List[Finding] = []

    delivery_regex = "|".join(DELIVERY_FEE_PATTERNS)

    with hub_engine.connect() as conn:
        # Find vendors with >=80% delivery frequency over 90 days
        vendors_with_delivery = conn.execute(text(f"""
            WITH vendor_invoices AS (
                SELECT i.vendor_id, i.id as invoice_id,
                       EXISTS(
                           SELECT 1 FROM hub_invoice_items it
                           WHERE it.invoice_id = i.id
                             AND (it.item_description ~* :pattern
                                  OR it.gl_cogs_account = '7140')
                       ) as has_delivery
                FROM hub_invoices i
                WHERE i.created_at >= NOW() - INTERVAL '90 days'
                  AND i.status NOT IN ('pending', 'parsing', 'parse_failed', 'statement')
                  AND i.vendor_id IS NOT NULL
            )
            SELECT vendor_id,
                   COUNT(*) as total_invoices,
                   SUM(CASE WHEN has_delivery THEN 1 ELSE 0 END)::float / COUNT(*) as delivery_pct
            FROM vendor_invoices
            GROUP BY vendor_id
            HAVING COUNT(*) >= 5
               AND SUM(CASE WHEN has_delivery THEN 1 ELSE 0 END)::float / COUNT(*) >= 0.80
        """), {"pattern": delivery_regex}).fetchall()

        if not vendors_with_delivery:
            return findings

        vendor_ids = [r[0] for r in vendors_with_delivery]

        # Check recent invoices from these vendors for missing delivery
        rows = conn.execute(text("""
            SELECT i.id, i.vendor_name, i.invoice_number, i.total_amount
            FROM hub_invoices i
            WHERE i.created_at >= :window
              AND i.vendor_id = ANY(:vendor_ids)
              AND i.total_amount > 100
              AND i.status NOT IN ('pending', 'parsing', 'parse_failed', 'statement')
              AND NOT EXISTS(
                  SELECT 1 FROM hub_invoice_items it
                  WHERE it.invoice_id = i.id
                    AND (it.item_description ~* :pattern
                         OR it.gl_cogs_account = '7140')
              )
        """), {"window": review_window, "vendor_ids": vendor_ids, "pattern": delivery_regex}).fetchall()

        for r in rows:
            findings.append(Finding(
                section="delivery_fee_completeness", check_name="missing_delivery_fee",
                severity="warning",
                title=f"Missing delivery fee: {r[2]} ({r[1]}, ${r[3]}) — vendor usually has delivery charges",
                record_type="hub_invoice", record_id=r[0],
            ))

    return findings


# ===================================================================
# Section 5F — PDF Verification & Auto-Fix (Hub API + Claude Vision)
# ===================================================================

HUB_INTERNAL_URL = os.getenv("HUB_INTERNAL_URL", "http://integration-hub:8000")


def check_pdf_verification(hub_engine, review_window: datetime) -> List[Finding]:
    """
    Find invoices with parsing issues, call Hub verify endpoint (Claude Vision)
    to auto-fix them, and report results.

    Flow:
    1. Query Hub DB for unsent invoices with total mismatches or needs_review
    2. Call Hub POST /api/invoices/{id}/verify for each candidate
    3. Claude reads the PDF, compares to DB, auto-corrects discrepancies
    4. Report corrections made and any remaining issues

    Targets:
    - Invoices where line_items_total doesn't match total_amount (parsing errors)
    - needs_review invoices (anomalies, low confidence)
    - Recently parsed unsent invoices
    """
    findings: List[Finding] = []
    candidate_ids = []

    with hub_engine.connect() as conn:
        # --- Total mismatch: line items don't add up to invoice total ---
        rows = conn.execute(text("""
            SELECT i.id, i.vendor_name, i.invoice_number, i.total_amount,
                   i.line_items_total, i.status, i.pdf_path,
                   ABS(COALESCE(i.line_items_total, 0) - COALESCE(i.total_amount, 0) + COALESCE(i.tax_amount, 0)) as diff
            FROM hub_invoices i
            WHERE i.status IN ('needs_review', 'mapping', 'ready')
              AND i.pdf_path IS NOT NULL
              AND COALESCE(i.sent_to_accounting, false) = false
              AND COALESCE(i.sent_to_inventory, false) = false
              AND i.is_statement = false
              AND ABS(COALESCE(i.line_items_total, 0) - COALESCE(i.total_amount, 0) + COALESCE(i.tax_amount, 0)) > 0.50
            ORDER BY diff DESC
            LIMIT 20
        """)).fetchall()

        for r in rows:
            candidate_ids.append((r[0], r[1], r[2], float(r[3] or 0)))

        # --- needs_review invoices ---
        rows = conn.execute(text("""
            SELECT i.id, i.vendor_name, i.invoice_number, i.total_amount
            FROM hub_invoices i
            WHERE i.status = 'needs_review'
              AND i.pdf_path IS NOT NULL
              AND i.created_at >= :window
            ORDER BY i.id DESC
            LIMIT 20
        """), {"window": review_window}).fetchall()

        seen_ids = {c[0] for c in candidate_ids}
        for r in rows:
            if r[0] not in seen_ids:
                candidate_ids.append((r[0], r[1], r[2], float(r[3] or 0)))

    if not candidate_ids:
        return findings

    logger.info(f"PDF verification: {len(candidate_ids)} candidates to verify via Claude Vision")

    # Call Hub verify endpoint for each candidate
    import urllib.request
    import urllib.error

    for inv_id, vendor, inv_num, total in candidate_ids:
        try:
            url = f"{HUB_INTERNAL_URL}/api/invoices/{inv_id}/verify"
            req = urllib.request.Request(
                url, method="POST",
                headers={"Content-Type": "application/json"},
                data=b"{}",
            )
            resp = urllib.request.urlopen(req, timeout=180)
            result = json.loads(resp.read().decode())

            if not result.get("success"):
                findings.append(Finding(
                    section="pdf_verification", check_name="verify_error",
                    severity="warning",
                    title=f"Verification failed: {inv_num} ({vendor}) — {result.get('error', 'unknown')}",
                    record_type="hub_invoice", record_id=inv_id,
                ))
                continue

            corrections = result.get("corrections_count", 0)
            verified = result.get("verification", {}).get("verified", False)
            remaining = len(result.get("verification", {}).get("remaining_issues", []))

            if corrections > 0 and verified:
                # Auto-fixed and re-verified — success
                correction_details = "; ".join(
                    f"{c['field']}: {c.get('old')}→{c.get('new')}"
                    for c in result.get("corrections", [])[:5]
                )
                findings.append(Finding(
                    section="pdf_verification", check_name="auto_fixed",
                    severity="info",
                    title=(
                        f"Auto-fixed: {inv_num} ({vendor}, ${total:.2f}) — "
                        f"{corrections} corrections, re-verified OK"
                    ),
                    detail=correction_details,
                    record_type="hub_invoice", record_id=inv_id,
                ))
            elif corrections > 0 and not verified:
                # Fixed some things but still has issues
                findings.append(Finding(
                    section="pdf_verification", check_name="partial_fix",
                    severity="warning",
                    title=(
                        f"Partially fixed: {inv_num} ({vendor}, ${total:.2f}) — "
                        f"{corrections} corrections but {remaining} issues remain"
                    ),
                    record_type="hub_invoice", record_id=inv_id,
                ))
            elif corrections == 0 and not result.get("needs_attention"):
                # Already correct
                findings.append(Finding(
                    section="pdf_verification", check_name="verified_ok",
                    severity="info",
                    title=f"Verified OK: {inv_num} ({vendor}, ${total:.2f}) — matches PDF",
                    record_type="hub_invoice", record_id=inv_id,
                ))
            else:
                # No corrections but still flagged
                findings.append(Finding(
                    section="pdf_verification", check_name="needs_manual_review",
                    severity="warning",
                    title=(
                        f"Needs manual review: {inv_num} ({vendor}, ${total:.2f}) — "
                        f"Claude couldn't resolve all discrepancies"
                    ),
                    record_type="hub_invoice", record_id=inv_id,
                ))

        except urllib.error.URLError as e:
            logger.error(f"Failed to call Hub verify for invoice {inv_id}: {e}")
            findings.append(Finding(
                section="pdf_verification", check_name="verify_error",
                severity="warning",
                title=f"Hub API unreachable for {inv_num} ({vendor}): {str(e)[:80]}",
                record_type="hub_invoice", record_id=inv_id,
            ))
        except Exception as e:
            logger.error(f"Verification error for invoice {inv_id}: {e}")
            findings.append(Finding(
                section="pdf_verification", check_name="verify_error",
                severity="warning",
                title=f"Verification error: {inv_num} ({vendor}) — {str(e)[:80]}",
                record_type="hub_invoice", record_id=inv_id,
            ))

    logger.info(
        f"PDF verification complete: {len(candidate_ids)} invoices checked, "
        f"{sum(1 for f in findings if f.check_name == 'auto_fixed')} auto-fixed"
    )

    return findings


# ===================================================================
# Report generation + email
# ===================================================================

def generate_report_html(findings: List[Finding], run_id: str, errors: List[str]) -> str:
    """Generate HTML email report from findings."""

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    ts_str = now.strftime("%Y-%m-%d %H:%M:%S ET")

    critical = [f for f in findings if f.severity == "critical"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]

    # Group by section
    sections: Dict[str, List[Finding]] = {}
    for f in findings:
        sections.setdefault(f.section, []).append(f)

    # Summary table rows
    section_labels = {
        "invoice_accuracy": "Invoice Accuracy (Hub)",
        "gl_integrity": "GL Entries",
        "inventory_costs": "Inventory Costs",
        "duplicate_payments": "Payments / Duplicates",
        "hub_accounting_sync": "Hub ↔ Accounting Sync",
        "pipeline_health": "Invoice Pipeline Health",
        "beverage_pricing": "Beverage Distributor Pricing",
        "linen_parse_quality": "Linen Service Parse Quality",
        "delivery_fee_completeness": "Delivery Fee Completeness",
        "pdf_verification": "PDF Verification Candidates",
    }

    summary_rows = ""
    for key, label in section_labels.items():
        sec_findings = sections.get(key, [])
        total = len(sec_findings)
        crit = sum(1 for f in sec_findings if f.severity == "critical")
        warn = sum(1 for f in sec_findings if f.severity == "warning")
        color = "#dc3545" if crit > 0 else "#ffc107" if warn > 0 else "#28a745"
        summary_rows += f"""
            <tr>
                <td style="padding:6px 12px;border-bottom:1px solid #eee">{label}</td>
                <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:center">{total}</td>
                <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:center;color:#dc3545;font-weight:bold">{crit if crit else '-'}</td>
                <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:center;color:#b8860b">{warn if warn else '-'}</td>
            </tr>"""

    # Critical issues list
    critical_html = ""
    if critical:
        for f in critical:
            critical_html += f"""
                <div style="background:#fff5f5;border-left:4px solid #dc3545;padding:10px 14px;margin:8px 0;border-radius:4px">
                    <strong style="color:#dc3545">[{f.section}] {f.check_name}</strong><br>
                    {f.title}
                    {"<br><em style='color:#666'>" + f.detail + "</em>" if f.detail else ""}
                    {f"<br><small>Record: {f.record_type} #{f.record_id}</small>" if f.record_id else ""}
                </div>"""
    else:
        critical_html = "<p style='color:#28a745'>No critical issues found.</p>"

    # Warnings list
    warnings_html = ""
    if warnings:
        for f in warnings:
            warnings_html += f"""
                <div style="background:#fff8e1;border-left:4px solid #ffc107;padding:8px 12px;margin:6px 0;border-radius:4px">
                    <strong>[{f.section}] {f.check_name}</strong><br>
                    {f.title}
                    {f"<br><small>Record: {f.record_type} #{f.record_id}</small>" if f.record_id else ""}
                </div>"""
    else:
        warnings_html = "<p style='color:#28a745'>No warnings.</p>"

    # Infrastructure errors
    errors_html = ""
    if errors:
        for e in errors:
            errors_html += f"<li style='color:#dc3545'>{e}</li>"
        errors_html = f"<ul>{errors_html}</ul>"
    else:
        errors_html = "<p>None</p>"

    # Passed checks
    all_checks = set(section_labels.keys())
    failed_sections = set(sections.keys())
    passed = all_checks - failed_sections
    passed_html = ", ".join(sorted(section_labels.get(s, s) for s in passed)) if passed else "None — all sections had findings"

    html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto;color:#333">
        <div style="background:#2c3e50;color:white;padding:20px;border-radius:8px 8px 0 0">
            <h1 style="margin:0;font-size:22px">SW Hospitality Group — Daily Accounting Review</h1>
            <p style="margin:5px 0 0;opacity:0.8">{ts_str} &middot; Run ID: {run_id[:8]}</p>
        </div>

        <div style="padding:20px;background:#f9f9f9">
            <div style="background:{"#fff5f5" if critical else "#f0fff0"};border:1px solid {"#dc3545" if critical else "#28a745"};border-radius:6px;padding:16px;margin-bottom:20px;text-align:center">
                <span style="font-size:32px;font-weight:bold;color:{"#dc3545" if critical else "#28a745"}">{len(critical)}</span>
                <span style="font-size:16px;color:#666"> critical</span>
                &nbsp;&nbsp;
                <span style="font-size:32px;font-weight:bold;color:#b8860b">{len(warnings)}</span>
                <span style="font-size:16px;color:#666"> warnings</span>
                &nbsp;&nbsp;
                <span style="font-size:32px;font-weight:bold;color:#666">{len(infos)}</span>
                <span style="font-size:16px;color:#666"> info</span>
            </div>

            <h2 style="border-bottom:2px solid #2c3e50;padding-bottom:6px">Summary</h2>
            <table style="width:100%;border-collapse:collapse;background:white;border-radius:4px">
                <tr style="background:#2c3e50;color:white">
                    <th style="padding:8px 12px;text-align:left">Category</th>
                    <th style="padding:8px 12px;text-align:center">Issues</th>
                    <th style="padding:8px 12px;text-align:center">Critical</th>
                    <th style="padding:8px 12px;text-align:center">Warnings</th>
                </tr>
                {summary_rows}
            </table>

            <h2 style="color:#dc3545;border-bottom:2px solid #dc3545;padding-bottom:6px;margin-top:24px">
                Critical Issues ({len(critical)})
            </h2>
            {critical_html}

            <h2 style="color:#b8860b;border-bottom:2px solid #ffc107;padding-bottom:6px;margin-top:24px">
                Warnings ({len(warnings)})
            </h2>
            {warnings_html}

            <h2 style="border-bottom:2px solid #28a745;padding-bottom:6px;margin-top:24px;color:#28a745">
                Passed Checks
            </h2>
            <p>{passed_html}</p>

            <h2 style="border-bottom:2px solid #999;padding-bottom:6px;margin-top:24px">
                Infrastructure Issues
            </h2>
            {errors_html}
        </div>

        <div style="background:#2c3e50;color:#aaa;padding:12px 20px;border-radius:0 0 8px 8px;font-size:12px">
            Generated by Daily Accounting Review &middot; Review window: {REVIEW_WINDOW_HOURS}h &middot;
            Findings stored in daily_review_findings table
        </div>
    </body>
    </html>
    """
    return html


def send_report_email(db: Session, html_body: str, findings: List[Finding]):
    """Send the daily review report via the accounting email service."""
    try:
        from accounting.services.email_service import EmailService
        email_svc = EmailService(db)

        critical_count = sum(1 for f in findings if f.severity == "critical")
        warning_count = sum(1 for f in findings if f.severity == "warning")

        if critical_count > 0:
            subject_prefix = f"🔴 {critical_count} CRITICAL"
        elif warning_count > 0:
            subject_prefix = f"🟡 {warning_count} warnings"
        else:
            subject_prefix = "✅ All clear"

        subject = f"Daily Accounting Review — {subject_prefix} — {date.today().isoformat()}"

        success = email_svc.send_email(
            to_email=REPORT_EMAIL,
            subject=subject,
            html_body=html_body,
        )

        if success:
            logger.info(f"Daily review report emailed to {REPORT_EMAIL}")
        else:
            logger.error(f"Failed to email daily review report to {REPORT_EMAIL}")

    except Exception:
        logger.exception(f"Error sending daily review email to {REPORT_EMAIL}")


# ===================================================================
# Persistence — store findings in accounting DB
# ===================================================================

def persist_findings(db: Session, run_id: str, findings: List[Finding], errors: List[str]):
    """Store run metadata and findings in the database."""

    started_at = datetime.now(timezone.utc)

    # Insert run record
    db.execute(text("""
        INSERT INTO daily_review_runs
            (run_id, started_at, completed_at, review_window_hours,
             total_findings, critical_count, warning_count, info_count, error_log, status)
        VALUES (:run_id, :started, :completed, :window,
                :total, :critical, :warning, :info, :errors, 'completed')
    """), {
        "run_id": run_id,
        "started": started_at,
        "completed": datetime.now(timezone.utc),
        "window": REVIEW_WINDOW_HOURS,
        "total": len(findings),
        "critical": sum(1 for f in findings if f.severity == "critical"),
        "warning": sum(1 for f in findings if f.severity == "warning"),
        "info": sum(1 for f in findings if f.severity == "info"),
        "errors": "\n".join(errors) if errors else None,
    })

    # Insert findings
    for f in findings:
        db.execute(text("""
            INSERT INTO daily_review_findings
                (run_id, section, check_name, severity, title, detail,
                 record_type, record_id, record_id_secondary, area_id,
                 flagged_value, expected_value)
            VALUES (:run_id, :section, :check_name, :severity, :title, :detail,
                    :record_type, :record_id, :record_id_secondary, :area_id,
                    :flagged_value, :expected_value)
        """), {
            "run_id": run_id,
            "section": f.section,
            "check_name": f.check_name,
            "severity": f.severity,
            "title": f.title,
            "detail": f.detail or "",
            "record_type": f.record_type,
            "record_id": f.record_id,
            "record_id_secondary": f.record_id_secondary,
            "area_id": f.area_id,
            "flagged_value": f.flagged_value,
            "expected_value": f.expected_value,
        })

    db.commit()
    logger.info(f"Persisted {len(findings)} findings for run {run_id}")


# ===================================================================
# Main orchestrator
# ===================================================================

def _daily_review_sync():
    """Synchronous daily review — runs in thread pool."""

    run_id = str(uuid.uuid4())
    logger.info(f"Starting daily accounting review (run_id={run_id})...")

    db: Session = SessionLocal()
    findings: List[Finding] = []
    errors: List[str] = []

    # Get cross-DB engines
    hub_engine = None
    inv_engine = None
    try:
        hub_engine = get_hub_engine()
    except Exception as e:
        errors.append(f"Hub DB connection failed: {e}")
        logger.error(f"Hub DB connection failed: {e}")
    try:
        inv_engine = get_inv_engine()
    except Exception as e:
        errors.append(f"Inventory DB connection failed: {e}")
        logger.error(f"Inventory DB connection failed: {e}")

    review_window = datetime.now() - timedelta(hours=REVIEW_WINDOW_HOURS)

    try:
        # Section 1 — Invoice Accuracy (Hub)
        if hub_engine:
            findings.extend(_run_section("invoice_accuracy", check_invoice_accuracy, hub_engine, review_window))

        # Section 2 — GL Integrity (Accounting)
        findings.extend(_run_section("gl_integrity", check_gl_integrity, db, review_window, db=db))

        # Section 3 — Inventory Costs (Hub + Inventory)
        if hub_engine and inv_engine:
            findings.extend(_run_section("inventory_costs", check_inventory_costs, hub_engine, inv_engine, review_window))

        # Section 4 — Duplicate Payments (Accounting)
        findings.extend(_run_section("duplicate_payments", check_duplicate_payments, db, review_window, db=db))

        # Section 5A — Hub ↔ Accounting Sync
        if hub_engine:
            findings.extend(_run_section("hub_accounting_sync", check_hub_accounting_sync, db, hub_engine, review_window, db=db))

        # Section 5B — Pipeline Health (Hub)
        if hub_engine:
            findings.extend(_run_section("pipeline_health", check_pipeline_health, hub_engine))

        # Section 5C — Beverage Pricing (Hub)
        if hub_engine:
            findings.extend(_run_section("beverage_pricing", check_beverage_pricing, hub_engine, review_window))

        # Section 5D — Linen Parse Quality (Hub)
        if hub_engine:
            findings.extend(_run_section("linen_parse_quality", check_linen_parse_quality, hub_engine, review_window))

        # Section 5E — Delivery Fee Completeness (Hub)
        if hub_engine:
            findings.extend(_run_section("delivery_fee_completeness", check_delivery_fee_completeness, hub_engine, review_window))

        # Section 5F — PDF Verification & Auto-Fix (Hub API + Claude Vision)
        if hub_engine:
            findings.extend(_run_section("pdf_verification", check_pdf_verification, hub_engine, review_window))

        # Persist findings to DB
        persist_findings(db, run_id, findings, errors)

        # Generate and email report
        report_html = generate_report_html(findings, run_id, errors)
        send_report_email(db, report_html, findings)

        critical = sum(1 for f in findings if f.severity == "critical")
        warning = sum(1 for f in findings if f.severity == "warning")
        logger.info(
            f"Daily review completed (run_id={run_id}): "
            f"{len(findings)} findings ({critical} critical, {warning} warnings)"
        )

    except Exception:
        logger.exception(f"Daily review failed (run_id={run_id})")
    finally:
        db.close()


async def daily_review_task():
    """Async wrapper for the scheduler — runs in thread pool."""
    import asyncio
    await asyncio.to_thread(_daily_review_sync)
