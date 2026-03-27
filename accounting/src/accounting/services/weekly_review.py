"""
Weekly Forensic Accounting Review

Runs every Sunday at 6 AM.  Deep-dive audit across Accounting, Hub, and
Inventory databases.  Covers transaction flow integrity, vendor forensics,
GL analysis (Benford's Law), inventory cost checks, cross-system integrity,
and tax-related classification review.

Uses the same Finding model and persistence tables as daily_review.py.
"""

import logging
import math
import os
import uuid
import json
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import List, Dict, Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from accounting.db.database import SessionLocal
from accounting.models.journal_entry import JournalEntry, JournalEntryLine
from accounting.models.vendor_bill import VendorBill, VendorBillLine
from accounting.models.account import Account
from accounting.models.area import Area

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPORT_EMAIL = "admin@swhgrp.com"
WEEKLY_WINDOW_DAYS = 7

# Benford's Law expected first-digit distribution
BENFORD_EXPECTED = {
    1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097,
    5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046,
}

# GL account ranges for tax classification checks
ASSET_RANGE = (1000, 1999)
EXPENSE_RANGE = (6000, 6999)
COGS_RANGE = (5000, 5999)
FIXED_ASSET_RANGE = (1500, 1999)
REPAIRS_MAINTENANCE_ACCOUNTS = (6400, 6499)

# Capital expenditure threshold (IRS de minimis safe harbor)
CAPEX_THRESHOLD = 2500.00

# Round-number tolerance for fraud detection
ROUND_NUMBER_PCT_THRESHOLD = 0.25  # Flag if >25% of invoices are round numbers

# ---------------------------------------------------------------------------
# Cross-DB engine helpers (shared with daily_review)
# ---------------------------------------------------------------------------

_hub_engine = None
_inv_engine = None

HUB_DATABASE_URL = os.getenv(
    "HUB_DATABASE_URL",
    "postgresql://hub_user:hub_password@hub-db:5432/integration_hub_db"
)

INVENTORY_DATABASE_URL = os.getenv(
    "INVENTORY_DATABASE_URL",
    "postgresql://inventory_user:inventory_password@inventory-db:5432/inventory_db"
)

MAINTENANCE_DATABASE_URL = os.getenv(
    "MAINTENANCE_DATABASE_URL",
    "postgresql://maintenance_user:maintenance_password@maintenance-postgres:5432/maintenance_db"
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


def get_maint_engine():
    return create_engine(
        MAINTENANCE_DATABASE_URL,
        pool_size=2, max_overflow=3,
        pool_pre_ping=True, pool_recycle=300,
    )


# ---------------------------------------------------------------------------
# Finding (same class as daily_review — could be extracted to shared module)
# ---------------------------------------------------------------------------

class Finding:
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


def _run_section(name: str, fn, *args, **kwargs) -> List[Finding]:
    """Run a check function with error handling."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.exception(f"Weekly review section '{name}' failed")
        return [Finding(
            section=name, check_name="section_error",
            severity="critical",
            title=f"Section '{name}' failed with error — see logs",
        )]


# ===================================================================
# Section 1 — End-to-End Transaction Flow Audit
# ===================================================================

def check_transaction_flow(db: Session, hub_engine, review_start: date) -> List[Finding]:
    """
    Trace invoices from Hub → Accounting bill → JE to verify amounts survive intact.
    """
    findings: List[Finding] = []

    # Get Hub sent invoices from the past week
    with hub_engine.connect() as hub_conn:
        hub_invoices = hub_conn.execute(text("""
            SELECT id, invoice_number, vendor_name, total_amount, location_id,
                   sent_to_accounting, accounting_sync_time
            FROM hub_invoices
            WHERE sent_to_accounting = true
              AND accounting_sync_time >= :start
        """), {"start": review_start}).fetchall()

    if not hub_invoices:
        return findings

    # Get accounting bills for comparison
    acct_bills = db.query(VendorBill).filter(
        VendorBill.created_at >= review_start
    ).all()
    acct_bills_by_number = {}
    for bill in acct_bills:
        key = (bill.bill_number or "").lstrip("0")
        acct_bills_by_number[key] = bill

    for hub_inv in hub_invoices:
        inv_id, inv_num, vendor, hub_total, loc_id, _, _ = hub_inv
        hub_total = float(hub_total or 0)
        stripped_num = (inv_num or "").lstrip("0")

        # Check 1: Does accounting have a matching bill?
        bill = acct_bills_by_number.get(stripped_num)
        if not bill:
            findings.append(Finding(
                section="transaction_flow", check_name="missing_acct_bill",
                severity="critical",
                title=f"Hub invoice #{inv_num} ({vendor}, ${hub_total:.2f}) sent but no Accounting bill found",
                record_type="hub_invoice", record_id=inv_id,
                flagged_value=hub_total,
            ))
            continue

        # Check 2: Do totals match?
        bill_total = float(bill.total_amount or 0)
        if abs(hub_total - bill_total) > 0.10:
            findings.append(Finding(
                section="transaction_flow", check_name="total_mismatch_hub_acct",
                severity="critical",
                title=(
                    f"Total mismatch: #{inv_num} ({vendor}) — "
                    f"Hub ${hub_total:.2f} vs Accounting ${bill_total:.2f} (diff ${abs(hub_total - bill_total):.2f})"
                ),
                record_type="vendor_bill", record_id=bill.id,
                flagged_value=hub_total, expected_value=bill_total,
            ))

        # Check 3: Does the bill have a JE?
        if not bill.journal_entry_id:
            findings.append(Finding(
                section="transaction_flow", check_name="bill_no_je",
                severity="warning",
                title=f"Bill #{inv_num} ({vendor}, ${bill_total:.2f}) has no journal entry",
                record_type="vendor_bill", record_id=bill.id,
            ))
            continue

        # Check 4: Does the JE balance?
        je = db.query(JournalEntry).filter(JournalEntry.id == bill.journal_entry_id).first()
        if je:
            lines = db.query(JournalEntryLine).filter(
                JournalEntryLine.journal_entry_id == je.id
            ).all()
            total_debit = sum(float(l.debit_amount or 0) for l in lines)
            total_credit = sum(float(l.credit_amount or 0) for l in lines)
            if abs(total_debit - total_credit) > 0.01:
                findings.append(Finding(
                    section="transaction_flow", check_name="je_unbalanced",
                    severity="critical",
                    title=(
                        f"Unbalanced JE for #{inv_num}: "
                        f"debits ${total_debit:.2f} vs credits ${total_credit:.2f}"
                    ),
                    record_type="journal_entry", record_id=je.id,
                ))

            # Check 5: Does JE total match bill total?
            if abs(total_debit - bill_total) > 0.10:
                findings.append(Finding(
                    section="transaction_flow", check_name="je_total_vs_bill",
                    severity="warning",
                    title=(
                        f"JE amount differs from bill: #{inv_num} — "
                        f"JE debits ${total_debit:.2f} vs bill ${bill_total:.2f}"
                    ),
                    record_type="journal_entry", record_id=je.id,
                    flagged_value=total_debit, expected_value=bill_total,
                ))

            # Check 6: Do bill line GL accounts match JE line GL accounts?
            bill_lines = db.query(VendorBillLine).filter(
                VendorBillLine.bill_id == bill.id
            ).all()
            bill_gl_ids = {bl.account_id for bl in bill_lines if bl.account_id}
            je_gl_ids = {jl.account_id for jl in lines if jl.account_id}
            # Bill GL accounts should be a subset of JE GL accounts
            missing_gl = bill_gl_ids - je_gl_ids
            if missing_gl:
                findings.append(Finding(
                    section="transaction_flow", check_name="gl_account_mismatch",
                    severity="warning",
                    title=(
                        f"GL mismatch: #{inv_num} — bill has accounts "
                        f"{missing_gl} not in JE"
                    ),
                    record_type="vendor_bill", record_id=bill.id,
                ))

    return findings


# ===================================================================
# Section 2 — Vendor Forensics
# ===================================================================

def check_vendor_forensics(hub_engine, review_start: date) -> List[Finding]:
    """
    Vendor-level anomaly detection: price creep, invoice gaps,
    round numbers, unusual activity patterns.
    """
    findings: List[Finding] = []

    with hub_engine.connect() as conn:
        # --- Price creep: same item steadily increasing over 4+ invoices ---
        rows = conn.execute(text("""
            WITH item_prices AS (
                SELECT it.item_code, it.item_description,
                       i.vendor_name, i.vendor_id,
                       it.unit_price, i.invoice_date,
                       ROW_NUMBER() OVER (
                           PARTITION BY i.vendor_id, it.item_code
                           ORDER BY i.invoice_date
                       ) as rn
                FROM hub_invoice_items it
                JOIN hub_invoices i ON it.invoice_id = i.id
                WHERE i.invoice_date >= NOW() - INTERVAL '90 days'
                  AND it.item_code IS NOT NULL
                  AND it.unit_price > 0
                  AND i.status NOT IN ('statement', 'pending', 'parse_failed')
            ),
            price_trends AS (
                SELECT vendor_name, item_code, item_description,
                       COUNT(*) as invoice_count,
                       MIN(unit_price) as min_price,
                       MAX(unit_price) as max_price,
                       ARRAY_AGG(unit_price ORDER BY rn) as prices
                FROM item_prices
                GROUP BY vendor_name, vendor_id, item_code, item_description
                HAVING COUNT(*) >= 4
            )
            SELECT vendor_name, item_code, item_description,
                   invoice_count, min_price, max_price, prices
            FROM price_trends
            WHERE max_price > min_price * 1.15
            ORDER BY (max_price - min_price) / NULLIF(min_price, 0) DESC
            LIMIT 20
        """)).fetchall()

        for r in rows:
            vendor, code, desc, count, min_p, max_p, prices = r
            pct_increase = ((float(max_p) - float(min_p)) / float(min_p) * 100) if float(min_p) > 0 else 0
            findings.append(Finding(
                section="vendor_forensics", check_name="price_creep",
                severity="warning",
                title=(
                    f"Price creep: {vendor} item {code} ({desc[:30]}) — "
                    f"${float(min_p):.2f} → ${float(max_p):.2f} (+{pct_increase:.0f}%) over {count} invoices"
                ),
                flagged_value=float(max_p), expected_value=float(min_p),
            ))

        # --- Invoice number gap analysis ---
        rows = conn.execute(text("""
            WITH numbered AS (
                SELECT vendor_name, invoice_number,
                       CASE WHEN invoice_number ~ '^\d+$'
                            THEN invoice_number::bigint
                            ELSE NULL END as num_value,
                       invoice_date
                FROM hub_invoices
                WHERE invoice_date >= :start
                  AND status NOT IN ('statement')
                  AND invoice_number IS NOT NULL
                ORDER BY vendor_name, num_value
            ),
            gaps AS (
                SELECT vendor_name, num_value,
                       LEAD(num_value) OVER (PARTITION BY vendor_name ORDER BY num_value) as next_num
                FROM numbered
                WHERE num_value IS NOT NULL
            )
            SELECT vendor_name, num_value, next_num,
                   (next_num - num_value - 1) as gap_size
            FROM gaps
            WHERE next_num IS NOT NULL
              AND next_num - num_value BETWEEN 2 AND 10
        """), {"start": review_start}).fetchall()

        for r in rows:
            vendor, from_num, to_num, gap = r
            findings.append(Finding(
                section="vendor_forensics", check_name="invoice_number_gap",
                severity="info",
                title=(
                    f"Invoice gap: {vendor} — #{from_num} to #{to_num} "
                    f"({gap} missing number{'s' if gap > 1 else ''})"
                ),
            ))

        # --- Round-number invoices (fraud indicator) ---
        rows = conn.execute(text("""
            WITH recent AS (
                SELECT vendor_name, COUNT(*) as total,
                       SUM(CASE WHEN total_amount = ROUND(total_amount, 0)
                                 AND total_amount >= 100
                            THEN 1 ELSE 0 END) as round_count
                FROM hub_invoices
                WHERE invoice_date >= :start
                  AND status NOT IN ('statement', 'pending')
                  AND total_amount > 0
                GROUP BY vendor_name
                HAVING COUNT(*) >= 3
            )
            SELECT vendor_name, total, round_count,
                   round_count::float / total as round_pct
            FROM recent
            WHERE round_count::float / total > :threshold
        """), {"start": review_start, "threshold": ROUND_NUMBER_PCT_THRESHOLD}).fetchall()

        for r in rows:
            vendor, total, round_ct, pct = r
            findings.append(Finding(
                section="vendor_forensics", check_name="round_number_invoices",
                severity="info",
                title=(
                    f"Round-number pattern: {vendor} — {round_ct}/{total} invoices "
                    f"({float(pct)*100:.0f}%) are round dollar amounts"
                ),
            ))

        # --- Vendor activity anomalies: sudden spike or drop ---
        rows = conn.execute(text("""
            WITH weekly_activity AS (
                SELECT vendor_name,
                       DATE_TRUNC('week', invoice_date) as week,
                       COUNT(*) as invoice_count,
                       SUM(total_amount) as week_total
                FROM hub_invoices
                WHERE invoice_date >= NOW() - INTERVAL '8 weeks'
                  AND status NOT IN ('statement', 'pending')
                GROUP BY vendor_name, DATE_TRUNC('week', invoice_date)
            ),
            vendor_stats AS (
                SELECT vendor_name,
                       AVG(week_total) as avg_weekly,
                       STDDEV(week_total) as stddev_weekly,
                       MAX(CASE WHEN week >= DATE_TRUNC('week', NOW() - INTERVAL '1 week')
                                THEN week_total END) as last_week
                FROM weekly_activity
                GROUP BY vendor_name
                HAVING COUNT(*) >= 4 AND STDDEV(week_total) > 0
            )
            SELECT vendor_name, avg_weekly, stddev_weekly, last_week
            FROM vendor_stats
            WHERE last_week IS NOT NULL
              AND ABS(last_week - avg_weekly) > 2 * stddev_weekly
              AND avg_weekly > 200
        """)).fetchall()

        for r in rows:
            vendor, avg, stddev, last = r
            direction = "spike" if float(last) > float(avg) else "drop"
            findings.append(Finding(
                section="vendor_forensics", check_name=f"activity_{direction}",
                severity="warning",
                title=(
                    f"Vendor activity {direction}: {vendor} — "
                    f"last week ${float(last):,.0f} vs avg ${float(avg):,.0f}/week (±${float(stddev):,.0f})"
                ),
                flagged_value=float(last), expected_value=float(avg),
            ))

    return findings


# ===================================================================
# Section 3 — GL Forensic Analysis
# ===================================================================

def check_gl_forensics(db: Session, review_start: date) -> List[Finding]:
    """
    GL-level forensic checks: Benford's Law, manual JE scrutiny,
    dormant account activation, period-boundary clustering.
    """
    findings: List[Finding] = []

    # --- Benford's Law on JE line amounts (last 90 days for statistical significance) ---
    ninety_days_ago = date.today() - timedelta(days=90)
    lines = db.query(JournalEntryLine).join(JournalEntry).filter(
        JournalEntry.entry_date >= ninety_days_ago,
        JournalEntry.status == 'POSTED',
    ).all()

    digit_counts = Counter()
    total_amounts = 0
    for line in lines:
        for amt in [float(line.debit_amount or 0), float(line.credit_amount or 0)]:
            if amt >= 1:
                first_digit = int(str(abs(amt)).lstrip('0').replace('.', '')[0])
                if 1 <= first_digit <= 9:
                    digit_counts[first_digit] += 1
                    total_amounts += 1

    if total_amounts >= 200:  # Need enough data for Benford to be meaningful
        # Chi-squared test
        chi_squared = 0
        benford_detail = []
        for digit in range(1, 10):
            observed = digit_counts.get(digit, 0) / total_amounts
            expected = BENFORD_EXPECTED[digit]
            chi_squared += ((observed - expected) ** 2) / expected
            deviation = abs(observed - expected) * 100
            if deviation > 3.0:  # Flag digits deviating by >3%
                benford_detail.append(
                    f"digit {digit}: {observed*100:.1f}% (expected {expected*100:.1f}%)"
                )

        # Chi-squared critical value for 8 df at 0.05 = 15.51
        if chi_squared > 15.51:
            findings.append(Finding(
                section="gl_forensics", check_name="benford_violation",
                severity="warning",
                title=(
                    f"Benford's Law anomaly (χ²={chi_squared:.1f}, n={total_amounts}) — "
                    f"first-digit distribution deviates from expected pattern"
                ),
                detail="; ".join(benford_detail) if benford_detail else "",
                flagged_value=chi_squared, expected_value=15.51,
            ))

    # --- Manual journal entries (higher fraud risk) ---
    manual_jes = db.query(JournalEntry).filter(
        JournalEntry.entry_date >= review_start,
        JournalEntry.status == 'POSTED',
        JournalEntry.reference_type.is_(None),  # No reference = manual entry
    ).all()

    for je in manual_jes:
        je_lines = db.query(JournalEntryLine).filter(
            JournalEntryLine.journal_entry_id == je.id
        ).all()
        total_debit = sum(float(l.debit_amount or 0) for l in je_lines)

        if total_debit >= 1000:  # Only flag material manual entries
            findings.append(Finding(
                section="gl_forensics", check_name="manual_je",
                severity="info",
                title=(
                    f"Manual JE #{je.entry_number} — ${total_debit:,.2f} "
                    f"on {je.entry_date} by user {je.created_by}: {(je.description or '')[:60]}"
                ),
                record_type="journal_entry", record_id=je.id,
                flagged_value=total_debit,
            ))

    # --- Weekend/holiday entries ---
    weekend_jes = db.query(JournalEntry).filter(
        JournalEntry.entry_date >= review_start,
        JournalEntry.status == 'POSTED',
    ).all()

    for je in weekend_jes:
        if je.entry_date and je.entry_date.weekday() in (5, 6):  # Saturday, Sunday
            je_lines = db.query(JournalEntryLine).filter(
                JournalEntryLine.journal_entry_id == je.id
            ).all()
            total_debit = sum(float(l.debit_amount or 0) for l in je_lines)
            if total_debit >= 500 and je.reference_type not in ('SALE',):
                day_name = "Saturday" if je.entry_date.weekday() == 5 else "Sunday"
                findings.append(Finding(
                    section="gl_forensics", check_name="weekend_entry",
                    severity="info",
                    title=(
                        f"Weekend entry: JE #{je.entry_number} on {day_name} {je.entry_date} — "
                        f"${total_debit:,.2f} ({je.reference_type or 'manual'})"
                    ),
                    record_type="journal_entry", record_id=je.id,
                ))

    # --- Dormant account activation ---
    # Accounts with no activity for 60+ days that suddenly have entries this week
    active_this_week = db.execute(text("""
        SELECT DISTINCT jl.account_id
        FROM journal_entry_lines jl
        JOIN journal_entries je ON jl.journal_entry_id = je.id
        WHERE je.entry_date >= :start AND je.status = 'POSTED'
    """), {"start": review_start}).fetchall()
    active_ids = [r[0] for r in active_this_week]

    if active_ids:
        for acct_id in active_ids:
            # Check if this account had any activity in the 60 days BEFORE this week
            prior = db.execute(text("""
                SELECT COUNT(*)
                FROM journal_entry_lines jl
                JOIN journal_entries je ON jl.journal_entry_id = je.id
                WHERE jl.account_id = :acct_id
                  AND je.entry_date >= :prior_start
                  AND je.entry_date < :start
                  AND je.status = 'POSTED'
            """), {
                "acct_id": acct_id,
                "prior_start": review_start - timedelta(days=60),
                "start": review_start,
            }).scalar()

            if prior == 0:
                account = db.query(Account).filter(Account.id == acct_id).first()
                if account:
                    # Get this week's total for the account
                    week_total = db.execute(text("""
                        SELECT COALESCE(SUM(jl.debit_amount), 0) + COALESCE(SUM(jl.credit_amount), 0)
                        FROM journal_entry_lines jl
                        JOIN journal_entries je ON jl.journal_entry_id = je.id
                        WHERE jl.account_id = :acct_id
                          AND je.entry_date >= :start
                          AND je.status = 'POSTED'
                    """), {"acct_id": acct_id, "start": review_start}).scalar()

                    if float(week_total or 0) >= 100:
                        findings.append(Finding(
                            section="gl_forensics", check_name="dormant_activation",
                            severity="warning",
                            title=(
                                f"Dormant account activated: {account.account_number} "
                                f"{account.account_name} — no activity for 60+ days, "
                                f"${float(week_total):,.2f} this week"
                            ),
                            record_type="account", record_id=acct_id,
                            flagged_value=float(week_total or 0),
                        ))

    # --- Reversing entries without matching originals ---
    reversed_jes = db.query(JournalEntry).filter(
        JournalEntry.entry_date >= review_start,
        JournalEntry.status == 'REVERSED',
    ).all()

    for je in reversed_jes:
        findings.append(Finding(
            section="gl_forensics", check_name="reversed_entry",
            severity="info",
            title=(
                f"Reversed JE #{je.entry_number} on {je.entry_date} — "
                f"{(je.description or '')[:60]}"
            ),
            record_type="journal_entry", record_id=je.id,
        ))

    return findings


# ===================================================================
# Section 4 — Inventory Cost Integrity
# ===================================================================

def check_inventory_cost_integrity(hub_engine, inv_engine, review_start: date) -> List[Finding]:
    """
    Verify invoice cost updates actually landed in Inventory.
    Check for cost divergence and stale pricing.
    """
    findings: List[Finding] = []

    # Get recently sent invoices with mapped items
    with hub_engine.connect() as hub_conn:
        sent_items = hub_conn.execute(text("""
            SELECT it.inventory_item_id, it.unit_price, it.item_description,
                   i.location_id, i.vendor_name, i.invoice_number, i.invoice_date
            FROM hub_invoice_items it
            JOIN hub_invoices i ON it.invoice_id = i.id
            WHERE i.sent_to_inventory = true
              AND i.invoice_date >= :start
              AND it.inventory_item_id IS NOT NULL
              AND it.is_mapped = true
        """), {"start": review_start}).fetchall()

    if not sent_items:
        return findings

    # Build lookup: vendor_item_id -> master_item_id
    vi_ids = list({item[0] for item in sent_items})
    vi_to_master = {}
    vi_to_factor = {}

    with hub_engine.connect() as hub_conn:
        for batch_start in range(0, len(vi_ids), 100):
            batch = vi_ids[batch_start:batch_start + 100]
            rows = hub_conn.execute(text("""
                SELECT id, inventory_master_item_id, pack_to_primary_factor
                FROM hub_vendor_items
                WHERE id = ANY(:ids)
            """), {"ids": batch}).fetchall()
            for r in rows:
                if r[1]:
                    vi_to_master[r[0]] = r[1]
                    vi_to_factor[r[0]] = float(r[2] or 1)

    # Check location costs in Inventory
    with inv_engine.connect() as inv_conn:
        for item in sent_items:
            vi_id, hub_price, desc, loc_id, vendor, inv_num, inv_date = item
            master_id = vi_to_master.get(vi_id)
            if not master_id or not loc_id:
                continue

            factor = vi_to_factor.get(vi_id, 1)
            expected_cost = float(hub_price or 0) / factor if factor > 0 else 0

            # Look up current location cost
            loc_cost_row = inv_conn.execute(text("""
                SELECT unit_cost, updated_at
                FROM master_item_location_costs
                WHERE master_item_id = :master_id AND store_id = :store_id
            """), {"master_id": master_id, "store_id": loc_id}).fetchone()

            if loc_cost_row:
                actual_cost = float(loc_cost_row[0] or 0)
                if expected_cost > 0 and actual_cost > 0:
                    pct_diff = abs(actual_cost - expected_cost) / expected_cost * 100
                    if pct_diff > 25:  # More than 25% off
                        findings.append(Finding(
                            section="inventory_costs", check_name="cost_divergence",
                            severity="warning",
                            title=(
                                f"Cost divergence: {desc[:35]} ({vendor}) — "
                                f"expected ${expected_cost:.4f}/unit from #{inv_num}, "
                                f"Inventory has ${actual_cost:.4f} ({pct_diff:.0f}% off)"
                            ),
                            flagged_value=actual_cost, expected_value=expected_cost,
                        ))

    # --- Cross-location price consistency ---
    with hub_engine.connect() as hub_conn:
        rows = hub_conn.execute(text("""
            WITH item_loc_prices AS (
                SELECT it.inventory_item_id, i.location_id, i.vendor_name,
                       vi.vendor_product_name,
                       AVG(it.unit_price) as avg_price
                FROM hub_invoice_items it
                JOIN hub_invoices i ON it.invoice_id = i.id
                JOIN hub_vendor_items vi ON vi.id = it.inventory_item_id
                WHERE i.invoice_date >= NOW() - INTERVAL '30 days'
                  AND it.inventory_item_id IS NOT NULL
                  AND it.unit_price > 0
                GROUP BY it.inventory_item_id, i.location_id, i.vendor_name, vi.vendor_product_name
            )
            SELECT a.inventory_item_id, a.vendor_name, a.vendor_product_name,
                   a.location_id as loc_a, b.location_id as loc_b,
                   a.avg_price as price_a, b.avg_price as price_b
            FROM item_loc_prices a
            JOIN item_loc_prices b ON a.inventory_item_id = b.inventory_item_id
              AND a.location_id < b.location_id
            WHERE a.avg_price > 0 AND b.avg_price > 0
              AND ABS(a.avg_price - b.avg_price) / LEAST(a.avg_price, b.avg_price) > 0.20
              AND LEAST(a.avg_price, b.avg_price) > 5
            ORDER BY ABS(a.avg_price - b.avg_price) DESC
            LIMIT 15
        """)).fetchall()

        for r in rows:
            findings.append(Finding(
                section="inventory_costs", check_name="cross_location_price",
                severity="info",
                title=(
                    f"Price varies across locations: {r[2][:30]} ({r[1]}) — "
                    f"loc {r[3]}: ${float(r[5]):.2f} vs loc {r[4]}: ${float(r[6]):.2f}"
                ),
                flagged_value=float(r[5]), expected_value=float(r[6]),
            ))

    return findings


# ===================================================================
# Section 5 — Cross-System Data Integrity
# ===================================================================

def check_cross_system_integrity(db: Session, hub_engine, inv_engine) -> List[Finding]:
    """
    Check for orphaned records, status inconsistencies, and
    data integrity across Hub, Accounting, and Inventory.
    """
    findings: List[Finding] = []

    # --- Orphaned JE lines: account_id pointing to inactive accounts ---
    rows = db.execute(text("""
        SELECT jl.id, jl.journal_entry_id, a.account_number, a.account_name,
               jl.debit_amount, jl.credit_amount
        FROM journal_entry_lines jl
        JOIN accounts a ON jl.account_id = a.id
        JOIN journal_entries je ON jl.journal_entry_id = je.id
        WHERE a.is_active = false
          AND je.status = 'POSTED'
          AND je.entry_date >= NOW() - INTERVAL '30 days'
        LIMIT 20
    """)).fetchall()

    for r in rows:
        amt = float(r[4] or 0) + float(r[5] or 0)
        findings.append(Finding(
            section="data_integrity", check_name="inactive_account_posted",
            severity="warning",
            title=(
                f"Posted JE uses inactive account: {r[2]} {r[3]} — "
                f"JE #{r[1]}, ${amt:.2f}"
            ),
            record_type="journal_entry", record_id=r[1],
        ))

    # --- Invalid location references ---
    rows = db.execute(text("""
        SELECT jl.journal_entry_id, jl.area_id, je.entry_number, je.entry_date,
               jl.debit_amount, jl.credit_amount
        FROM journal_entry_lines jl
        JOIN journal_entries je ON jl.journal_entry_id = je.id
        LEFT JOIN areas a ON jl.area_id = a.id
        WHERE jl.area_id IS NOT NULL
          AND a.id IS NULL
          AND je.status = 'POSTED'
          AND je.entry_date >= NOW() - INTERVAL '30 days'
        LIMIT 10
    """)).fetchall()

    for r in rows:
        findings.append(Finding(
            section="data_integrity", check_name="invalid_area_ref",
            severity="critical",
            title=f"JE #{r[2]} references non-existent area_id {r[1]}",
            record_type="journal_entry", record_id=r[0],
        ))

    # --- Hub vendor items: active in Hub but master item missing in Inventory ---
    with hub_engine.connect() as hub_conn:
        hub_vi = hub_conn.execute(text("""
            SELECT id, vendor_product_name, vendor_sku, inventory_master_item_id
            FROM hub_vendor_items
            WHERE status = 'active'
              AND inventory_master_item_id IS NOT NULL
            LIMIT 500
        """)).fetchall()

    if hub_vi and inv_engine:
        master_ids = list({r[3] for r in hub_vi if r[3]})
        with inv_engine.connect() as inv_conn:
            existing = inv_conn.execute(text("""
                SELECT id FROM master_items WHERE id = ANY(:ids)
            """), {"ids": master_ids}).fetchall()
            existing_ids = {r[0] for r in existing}

        for vi in hub_vi:
            if vi[3] and vi[3] not in existing_ids:
                findings.append(Finding(
                    section="data_integrity", check_name="orphaned_master_ref",
                    severity="warning",
                    title=(
                        f"Hub vendor item '{vi[1][:35]}' (SKU: {vi[2]}) → "
                        f"master_item_id {vi[3]} not found in Inventory"
                    ),
                    record_type="hub_vendor_item", record_id=vi[0],
                ))

    return findings


# ===================================================================
# Section 6 — AP / Cash Flow Reconciliation
# ===================================================================

def check_ap_reconciliation(db: Session, review_start: date) -> List[Finding]:
    """
    AP aging, undeposited funds, and cash over/short analysis.
    """
    findings: List[Finding] = []

    # --- Undeposited funds aging ---
    undeposited = db.execute(text("""
        SELECT a.id, a.account_number, a.account_name,
               COALESCE(SUM(jl.debit_amount), 0) - COALESCE(SUM(jl.credit_amount), 0) as balance
        FROM accounts a
        JOIN journal_entry_lines jl ON jl.account_id = a.id
        JOIN journal_entries je ON jl.journal_entry_id = je.id
        WHERE a.account_name ILIKE '%undeposited%'
          AND je.status = 'POSTED'
        GROUP BY a.id, a.account_number, a.account_name
        HAVING ABS(COALESCE(SUM(jl.debit_amount), 0) - COALESCE(SUM(jl.credit_amount), 0)) > 100
    """)).fetchall()

    for r in undeposited:
        balance = float(r[3])
        if abs(balance) > 500:
            findings.append(Finding(
                section="ap_reconciliation", check_name="undeposited_balance",
                severity="warning" if abs(balance) > 2000 else "info",
                title=(
                    f"Undeposited funds balance: {r[1]} {r[2]} — "
                    f"${balance:,.2f} outstanding"
                ),
                record_type="account", record_id=r[0],
                flagged_value=balance,
            ))

    # --- Cash over/short trending ---
    cash_variances = db.execute(text("""
        SELECT dss.business_date, dss.area_id, a.name as location,
               dss.cash_variance
        FROM daily_sales_summaries dss
        LEFT JOIN areas a ON dss.area_id = a.id
        WHERE dss.business_date >= :start
          AND dss.cash_variance IS NOT NULL
          AND ABS(dss.cash_variance) > 5
        ORDER BY ABS(dss.cash_variance) DESC
        LIMIT 15
    """), {"start": review_start}).fetchall()

    for r in cash_variances:
        direction = "over" if float(r[3]) > 0 else "short"
        findings.append(Finding(
            section="ap_reconciliation", check_name=f"cash_{direction}",
            severity="warning" if abs(float(r[3])) > 25 else "info",
            title=(
                f"Cash {direction}: {r[2] or f'Area {r[1]}'} on {r[0]} — "
                f"${abs(float(r[3])):.2f} {direction}"
            ),
            area_id=r[1],
            flagged_value=float(r[3]),
        ))

    # --- Overdue AP bills ---
    overdue = db.execute(text("""
        SELECT vb.id, vb.vendor_name, vb.bill_number, vb.total_amount,
               vb.due_date, (CURRENT_DATE - vb.due_date) as days_overdue
        FROM vendor_bills vb
        WHERE vb.status IN ('pending_approval', 'approved')
          AND vb.due_date < CURRENT_DATE
        ORDER BY (CURRENT_DATE - vb.due_date) DESC
        LIMIT 15
    """)).fetchall()

    for r in overdue:
        days = int(r[5])
        findings.append(Finding(
            section="ap_reconciliation", check_name="overdue_ap",
            severity="warning" if days > 30 else "info",
            title=(
                f"Overdue AP: {r[1]} #{r[2]} — ${float(r[3]):,.2f} "
                f"due {r[4]}, {days} days overdue"
            ),
            record_type="vendor_bill", record_id=r[0],
            flagged_value=float(days),
        ))

    return findings


# ===================================================================
# Section 7 — Tax Optimization & Compliance
# ===================================================================

def check_tax_classification(db: Session, hub_engine, review_start: date) -> List[Finding]:
    """
    Tax-related classification checks:
    - Capital vs expense misclassification
    - Repair vs capital improvement
    - GL account tax classification review
    """
    findings: List[Finding] = []

    # --- Capital vs Expense: large purchases booked to expense accounts ---
    rows = db.execute(text("""
        SELECT jl.id, jl.journal_entry_id, je.entry_number, je.entry_date,
               a.account_number, a.account_name, a.account_type,
               jl.debit_amount, je.description, jl.description as line_desc
        FROM journal_entry_lines jl
        JOIN journal_entries je ON jl.journal_entry_id = je.id
        JOIN accounts a ON jl.account_id = a.id
        WHERE je.entry_date >= :start
          AND je.status = 'POSTED'
          AND jl.debit_amount >= :threshold
          AND a.account_type IN ('EXPENSE', 'COGS')
          AND a.account_number::int BETWEEN 6000 AND 6999
        ORDER BY jl.debit_amount DESC
        LIMIT 20
    """), {"start": review_start, "threshold": CAPEX_THRESHOLD}).fetchall()

    for r in rows:
        amt = float(r[7])
        line_desc = r[9] or r[8] or ""
        findings.append(Finding(
            section="tax_classification", check_name="capex_vs_expense",
            severity="warning",
            title=(
                f"Potential capital expense: ${amt:,.2f} booked to {r[4]} {r[5]} — "
                f"JE #{r[2]} on {r[3]}: {line_desc[:50]}"
            ),
            detail=(
                "Purchases ≥$2,500 may qualify for Section 179 expensing or "
                "should be capitalized as fixed assets for depreciation."
            ),
            record_type="journal_entry", record_id=r[1],
            flagged_value=amt, expected_value=CAPEX_THRESHOLD,
        ))

    # --- Repair vs Capital Improvement (from vendor bills) ---
    repair_bills = db.execute(text("""
        SELECT vb.id, vb.vendor_name, vb.bill_number, vb.total_amount,
               vb.bill_date, vbl.description, a.account_number, a.account_name
        FROM vendor_bills vb
        JOIN vendor_bill_lines vbl ON vbl.bill_id = vb.id
        JOIN accounts a ON vbl.account_id = a.id
        WHERE vb.bill_date >= :start
          AND vb.status NOT IN ('void')
          AND a.account_number::int BETWEEN :repair_start AND :repair_end
          AND vbl.amount >= :threshold
        ORDER BY vbl.amount DESC
        LIMIT 15
    """), {
        "start": review_start,
        "repair_start": REPAIRS_MAINTENANCE_ACCOUNTS[0],
        "repair_end": REPAIRS_MAINTENANCE_ACCOUNTS[1],
        "threshold": CAPEX_THRESHOLD,
    }).fetchall()

    for r in repair_bills:
        amt = float(r[3])
        desc = r[5] or ""
        # Check for capital improvement keywords
        cap_keywords = ['install', 'replace', 'upgrade', 'remodel', 'renovation',
                        'new', 'addition', 'improvement', 'build', 'construct']
        is_likely_capital = any(kw in desc.lower() for kw in cap_keywords)

        findings.append(Finding(
            section="tax_classification", check_name="repair_vs_improvement",
            severity="warning" if is_likely_capital else "info",
            title=(
                f"{'Likely capital improvement' if is_likely_capital else 'Large repair'}: "
                f"{r[1]} #{r[2]} — ${amt:,.2f} to {r[6]} {r[7]}: {desc[:50]}"
            ),
            detail=(
                "Capital improvements (extend useful life, add value) should be capitalized. "
                "Repairs (restore to working condition) are immediately deductible."
                + (" Description contains capital improvement keywords." if is_likely_capital else "")
            ),
            record_type="vendor_bill", record_id=r[0],
            flagged_value=amt,
        ))

    # --- GL Account Tax Classification Review ---
    # Flag entries in accounts that commonly have tax implications

    # Employee meals — verify they're in the right account
    rows = db.execute(text("""
        SELECT jl.journal_entry_id, je.entry_number, je.entry_date,
               a.account_number, a.account_name,
               jl.debit_amount, je.description
        FROM journal_entry_lines jl
        JOIN journal_entries je ON jl.journal_entry_id = je.id
        JOIN accounts a ON jl.account_id = a.id
        WHERE je.entry_date >= :start
          AND je.status = 'POSTED'
          AND (
              a.account_name ILIKE '%employee meal%'
              OR a.account_name ILIKE '%staff meal%'
              OR a.account_name ILIKE '%crew meal%'
          )
          AND jl.debit_amount > 0
    """), {"start": review_start}).fetchall()

    if rows:
        total_emp_meals = sum(float(r[5] or 0) for r in rows)
        findings.append(Finding(
            section="tax_classification", check_name="employee_meals_tracking",
            severity="info",
            title=(
                f"Employee meals this week: ${total_emp_meals:,.2f} across {len(rows)} entries — "
                f"confirm all qualify as de minimis fringe benefit (on-premises, for employer convenience)"
            ),
            detail=(
                "Employee meals provided on-premises for employer convenience are "
                "100% deductible and excluded from employee income. "
                "Meals provided for employee convenience (not just as a perk) "
                "must be on business premises during or near work shifts."
            ),
            flagged_value=total_emp_meals,
        ))

    # Entertainment/marketing — flag for proper categorization
    rows = db.execute(text("""
        SELECT a.account_number, a.account_name,
               SUM(jl.debit_amount) as total
        FROM journal_entry_lines jl
        JOIN journal_entries je ON jl.journal_entry_id = je.id
        JOIN accounts a ON jl.account_id = a.id
        WHERE je.entry_date >= :start
          AND je.status = 'POSTED'
          AND (
              a.account_name ILIKE '%entertain%'
              OR a.account_name ILIKE '%marketing%'
              OR a.account_name ILIKE '%advertising%'
              OR a.account_name ILIKE '%promotion%'
          )
          AND jl.debit_amount > 0
        GROUP BY a.account_number, a.account_name
        HAVING SUM(jl.debit_amount) > 100
    """), {"start": review_start}).fetchall()

    for r in rows:
        total = float(r[2])
        is_entertainment = 'entertain' in (r[1] or '').lower()
        findings.append(Finding(
            section="tax_classification", check_name="entertainment_marketing",
            severity="info" if not is_entertainment else "warning",
            title=(
                f"{'Entertainment' if is_entertainment else 'Marketing/Advertising'} expense: "
                f"{r[0]} {r[1]} — ${total:,.2f} this week"
            ),
            detail=(
                "Entertainment expenses are NOT deductible (post-2017 tax law). "
                "Business meals remain 50% deductible if directly related to business. "
                "Advertising is 100% deductible."
                if is_entertainment else
                "Advertising and marketing expenses are 100% deductible. "
                "Ensure no entertainment expenses are miscategorized here."
            ),
            flagged_value=total,
        ))

    # --- Supplies that might be inventory (tax timing difference) ---
    # Large supply purchases that should be tracked as inventory
    with hub_engine.connect() as hub_conn:
        rows = hub_conn.execute(text("""
            SELECT it.item_description, it.gl_cogs_account, it.total_amount,
                   i.vendor_name, i.invoice_number
            FROM hub_invoice_items it
            JOIN hub_invoices i ON it.invoice_id = i.id
            WHERE i.invoice_date >= :start
              AND it.total_amount >= 500
              AND it.inventory_item_id IS NULL
              AND it.is_mapped = true
              AND it.gl_cogs_account IS NOT NULL
            ORDER BY it.total_amount DESC
            LIMIT 10
        """), {"start": review_start}).fetchall()

    for r in rows:
        findings.append(Finding(
            section="tax_classification", check_name="large_expense_review",
            severity="info",
            title=(
                f"Large non-inventory expense: {(r[0] or '')[:35]} — "
                f"${float(r[2]):,.2f} from {r[3]} #{r[4]}, GL {r[1]}"
            ),
            detail=(
                "Large expense items may need review: could they be capitalized, "
                "split across periods, or tracked as inventory?"
            ),
        ))

    return findings


# ===================================================================
# Report generation
# ===================================================================

def generate_weekly_report_html(findings: List[Finding], run_id: str, errors: List[str]) -> str:
    """Generate HTML email report for the weekly forensic review."""

    now = datetime.now()
    week_end = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    ts_str = now.strftime("%Y-%m-%d %H:%M:%S ET")

    critical = [f for f in findings if f.severity == "critical"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]

    sections: Dict[str, List[Finding]] = {}
    for f in findings:
        sections.setdefault(f.section, []).append(f)

    section_labels = {
        "transaction_flow": "End-to-End Transaction Flow",
        "vendor_forensics": "Vendor Forensics",
        "gl_forensics": "GL Forensic Analysis",
        "inventory_costs": "Inventory Cost Integrity",
        "data_integrity": "Cross-System Data Integrity",
        "ap_reconciliation": "AP / Cash Flow",
        "tax_classification": "Tax Optimization & Compliance",
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
                <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:center;color:#666">{total - crit - warn if total - crit - warn else '-'}</td>
                <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:center"><span style="color:{color};font-size:18px">●</span></td>
            </tr>"""

    # Build detail sections
    detail_html = ""
    for key, label in section_labels.items():
        sec_findings = sections.get(key, [])
        if not sec_findings:
            continue

        detail_html += f'<h3 style="margin:20px 0 10px;color:#333;border-bottom:2px solid #455A64;padding-bottom:5px">{label}</h3>'

        for f in sec_findings:
            icon = "🔴" if f.severity == "critical" else "🟡" if f.severity == "warning" else "ℹ️"
            bg = "#fff5f5" if f.severity == "critical" else "#fffde7" if f.severity == "warning" else "#f8f9fa"
            detail_html += f"""
                <div style="margin:6px 0;padding:8px 12px;background:{bg};border-left:3px solid {'#dc3545' if f.severity=='critical' else '#ffc107' if f.severity=='warning' else '#6c757d'};border-radius:3px">
                    <div>{icon} <strong>{f.title}</strong></div>
                    {'<div style="margin-top:4px;color:#666;font-size:13px">' + f.detail + '</div>' if f.detail else ''}
                </div>"""

    error_section = ""
    if errors:
        error_section = '<h3 style="color:#dc3545">Errors During Review</h3><ul>'
        for e in errors:
            error_section += f'<li style="color:#dc3545">{e}</li>'
        error_section += '</ul>'

    html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto;color:#333">
        <div style="background:#455A64;color:white;padding:20px;border-radius:6px 6px 0 0">
            <h1 style="margin:0;font-size:22px">📊 Weekly Forensic Accounting Review</h1>
            <p style="margin:5px 0 0;opacity:0.9">Week of {week_start} to {week_end} | Generated {ts_str}</p>
            <p style="margin:5px 0 0;opacity:0.9">Run ID: {run_id}</p>
        </div>

        <div style="padding:20px;border:1px solid #ddd;border-top:none">
            <h2 style="margin-top:0">Summary</h2>
            <p>
                <strong style="color:#dc3545">{len(critical)} Critical</strong> &nbsp;|&nbsp;
                <strong style="color:#b8860b">{len(warnings)} Warnings</strong> &nbsp;|&nbsp;
                <strong style="color:#666">{len(infos)} Info</strong> &nbsp;|&nbsp;
                Total: {len(findings)} findings
            </p>

            <table style="width:100%;border-collapse:collapse;margin:15px 0">
                <thead>
                    <tr style="background:#f5f5f5">
                        <th style="padding:8px 12px;text-align:left;border-bottom:2px solid #ddd">Section</th>
                        <th style="padding:8px 12px;text-align:center;border-bottom:2px solid #ddd">Total</th>
                        <th style="padding:8px 12px;text-align:center;border-bottom:2px solid #ddd">Critical</th>
                        <th style="padding:8px 12px;text-align:center;border-bottom:2px solid #ddd">Warning</th>
                        <th style="padding:8px 12px;text-align:center;border-bottom:2px solid #ddd">Info</th>
                        <th style="padding:8px 12px;text-align:center;border-bottom:2px solid #ddd">Status</th>
                    </tr>
                </thead>
                <tbody>{summary_rows}</tbody>
            </table>

            {detail_html}
            {error_section}

            <hr style="margin:20px 0;border:none;border-top:1px solid #ddd">
            <p style="color:#999;font-size:12px">
                SW Hospitality Group — Weekly Forensic Accounting Review<br>
                This is an automated report. Review findings and take action as needed.
            </p>
        </div>
    </body>
    </html>"""

    return html


# ===================================================================
# Persistence (reuses daily_review tables with run_type prefix)
# ===================================================================

def persist_findings(db: Session, run_id: str, findings: List[Finding], errors: List[str]):
    """Store weekly review findings in the daily_review tables."""
    try:
        db.execute(text("""
            INSERT INTO daily_review_runs
                (run_id, started_at, completed_at, review_window_hours,
                 total_findings, critical_count, warning_count, info_count, error_log, status)
            VALUES (:run_id, :started, :completed, :window,
                    :total, :critical, :warning, :info, :errors, 'completed')
        """), {
            "run_id": run_id,
            "started": datetime.now(timezone.utc),
            "completed": datetime.now(timezone.utc),
            "window": WEEKLY_WINDOW_DAYS * 24,
            "total": len(findings),
            "critical": sum(1 for f in findings if f.severity == "critical"),
            "warning": sum(1 for f in findings if f.severity == "warning"),
            "info": sum(1 for f in findings if f.severity == "info"),
            "errors": "\n".join(errors) if errors else None,
        })

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
    except Exception:
        logger.exception("Failed to persist weekly review findings")
        db.rollback()


def send_report_email(db: Session, html_body: str, findings: List[Finding]):
    """Send the weekly review report email."""
    try:
        from accounting.services.email_service import EmailService
        email_svc = EmailService(db)

        critical_count = sum(1 for f in findings if f.severity == "critical")
        warning_count = sum(1 for f in findings if f.severity == "warning")

        if critical_count > 0:
            prefix = f"🔴 {critical_count} CRITICAL"
        elif warning_count > 0:
            prefix = f"🟡 {warning_count} warnings"
        else:
            prefix = "✅ All clear"

        week_of = (date.today() - timedelta(days=7)).isoformat()
        subject = f"Weekly Forensic Review — {prefix} — week of {week_of}"

        success = email_svc.send_email(
            to_email=REPORT_EMAIL,
            subject=subject,
            html_body=html_body,
        )

        if success:
            logger.info(f"Weekly review report emailed to {REPORT_EMAIL}")
        else:
            logger.error(f"Failed to email weekly review report")

    except Exception:
        logger.exception("Error sending weekly review email")


# ===================================================================
# Main entry point
# ===================================================================

def _weekly_review_sync():
    """Synchronous weekly review — runs all sections."""
    run_id = f"weekly-{uuid.uuid4().hex[:12]}"
    logger.info(f"Starting weekly forensic review (run_id={run_id})")

    db = SessionLocal()
    findings: List[Finding] = []
    errors: List[str] = []

    review_start = date.today() - timedelta(days=WEEKLY_WINDOW_DAYS)

    hub_engine = None
    inv_engine = None
    try:
        hub_engine = get_hub_engine()
    except Exception as e:
        errors.append(f"Hub DB connection failed: {e}")
    try:
        inv_engine = get_inv_engine()
    except Exception as e:
        errors.append(f"Inventory DB connection failed: {e}")

    try:
        # Section 1 — End-to-End Transaction Flow
        if hub_engine:
            findings.extend(_run_section(
                "transaction_flow", check_transaction_flow, db, hub_engine, review_start
            ))

        # Section 2 — Vendor Forensics
        if hub_engine:
            findings.extend(_run_section(
                "vendor_forensics", check_vendor_forensics, hub_engine, review_start
            ))

        # Section 3 — GL Forensic Analysis
        findings.extend(_run_section(
            "gl_forensics", check_gl_forensics, db, review_start
        ))

        # Section 4 — Inventory Cost Integrity
        if hub_engine and inv_engine:
            findings.extend(_run_section(
                "inventory_costs", check_inventory_cost_integrity,
                hub_engine, inv_engine, review_start
            ))

        # Section 5 — Cross-System Data Integrity
        if hub_engine and inv_engine:
            findings.extend(_run_section(
                "data_integrity", check_cross_system_integrity,
                db, hub_engine, inv_engine
            ))

        # Section 6 — AP / Cash Flow Reconciliation
        findings.extend(_run_section(
            "ap_reconciliation", check_ap_reconciliation, db, review_start
        ))

        # Section 7 — Tax Optimization & Compliance
        if hub_engine:
            findings.extend(_run_section(
                "tax_classification", check_tax_classification,
                db, hub_engine, review_start
            ))

        # Persist
        persist_findings(db, run_id, findings, errors)

        # Generate and email report
        report_html = generate_weekly_report_html(findings, run_id, errors)
        send_report_email(db, report_html, findings)

        critical = sum(1 for f in findings if f.severity == "critical")
        warning = sum(1 for f in findings if f.severity == "warning")
        logger.info(
            f"Weekly review completed (run_id={run_id}): "
            f"{len(findings)} findings ({critical} critical, {warning} warnings)"
        )

    except Exception:
        logger.exception(f"Weekly review failed (run_id={run_id})")
    finally:
        db.close()


async def weekly_review_task():
    """Async wrapper for the scheduler — runs in thread pool."""
    import asyncio
    await asyncio.to_thread(_weekly_review_sync)
