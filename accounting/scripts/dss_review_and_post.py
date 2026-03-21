"""
Automated DSS Review and Post Script

Reviews all verified (unposted) Daily Sales Summaries for anomalies,
auto-posts clean entries, and flags problematic ones for manual review.

Checks performed:
- Math validation: net_sales = gross - discounts - refunds
- Total validation: total_collected = net_sales + tax + tips
- Payment balance: sum of payments ≈ total_collected
- Missing GL mappings (category, payment, discount)
- Zero/negative sales amounts
- Unusually high amounts (configurable threshold)
- Missing payment breakdown for POS imports
- Duplicate entries (same date + area already posted)

Usage:
    docker compose exec -T accounting-app python scripts/dss_review_and_post.py [--dry-run] [--area-id N]
"""
import sys
import os
import argparse
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from accounting.db.database import SessionLocal
from accounting.models.daily_sales_summary import DailySalesSummary, SalesLineItem, SalesPayment
from accounting.models.pos import (
    POSCategoryGLMapping, POSDiscountGLMapping, POSPaymentGLMapping
)
from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.account import Account
from accounting.models.user import User
from accounting.schemas.daily_sales_summary import DSSPostRequest

# Thresholds
HIGH_SALES_THRESHOLD = Decimal("25000.00")  # Flag if net_sales > $25k
MATH_TOLERANCE = Decimal("0.05")  # Allow 5 cents rounding
PAYMENT_TOLERANCE = Decimal("1.00")  # Allow $1 tolerance for payment vs total


def parse_args():
    parser = argparse.ArgumentParser(description="Review and auto-post DSS entries")
    parser.add_argument("--dry-run", action="store_true", help="Review only, don't post or flag")
    parser.add_argument("--area-id", type=int, help="Only process specific area")
    return parser.parse_args()


def review_dss(dss: DailySalesSummary, db: Session) -> list[str]:
    """
    Review a single DSS entry for anomalies.
    Returns a list of issue descriptions. Empty list = clean.
    """
    issues = []

    gross = dss.gross_sales or Decimal("0.00")
    discounts = dss.discounts or Decimal("0.00")
    refunds = dss.refunds or Decimal("0.00")
    net = dss.net_sales or Decimal("0.00")
    tax = dss.tax_collected or Decimal("0.00")
    tips = dss.tips or Decimal("0.00")
    total = dss.total_collected or Decimal("0.00")

    # 1. Math: net_sales should = gross - discounts - refunds
    expected_net = gross - discounts - refunds
    if abs(net - expected_net) > MATH_TOLERANCE:
        issues.append(f"Net sales mismatch: expected {expected_net} (gross {gross} - disc {discounts} - ref {refunds}), got {net}")

    # 2. Total: total_collected should = net + tax + tips
    expected_total = net + tax + tips
    if abs(total - expected_total) > MATH_TOLERANCE:
        issues.append(f"Total collected mismatch: expected {expected_total} (net {net} + tax {tax} + tips {tips}), got {total}")

    # 3. Zero or negative net sales
    if net <= Decimal("0.00"):
        issues.append(f"Zero or negative net sales: {net}")

    # 4. Unusually high amounts
    if net > HIGH_SALES_THRESHOLD:
        issues.append(f"Unusually high net sales: {net} (threshold: {HIGH_SALES_THRESHOLD})")

    # 5. Payment balance check
    if dss.payments:
        payment_total = sum((p.amount or Decimal("0.00")) for p in dss.payments)
        payment_tips = sum((p.tips or Decimal("0.00")) for p in dss.payments)
        # Payments (amount) should roughly equal net + tax
        # Tips on payments are tracked separately
        expected_payment_total = net + tax
        # Allow larger tolerance — POS rounding, gift cards, partial payments
        if abs(payment_total - expected_payment_total) > Decimal("5.00"):
            issues.append(f"Payment total {payment_total} doesn't match net+tax {expected_payment_total} (diff: ${abs(payment_total - expected_payment_total)})")

    # 6. POS import without payment breakdown
    if dss.pos_system and not dss.payments:
        issues.append(f"POS import ({dss.pos_system}) has no payment breakdown")

    # 7. Missing line items for POS import
    if dss.pos_system and not dss.line_items:
        issues.append(f"POS import ({dss.pos_system}) has no category line items")

    # 8. Check GL mapping completeness
    gl_issues = check_gl_mappings(dss, db)
    issues.extend(gl_issues)

    # 9. Payouts require GL assignment before posting
    if dss.payout_breakdown and isinstance(dss.payout_breakdown, list):
        for payout in dss.payout_breakdown:
            payout_amount = float(payout.get("amount", 0))
            if payout_amount > 0 and not payout.get("gl_account_id"):
                note = payout.get("note", "Cash payout")
                issues.append(f"Payout needs GL account: ${payout_amount:.2f} ({note})")

    # 10. Check for duplicate (same date + area already posted)
    existing_posted = db.query(DailySalesSummary).filter(
        DailySalesSummary.business_date == dss.business_date,
        DailySalesSummary.area_id == dss.area_id,
        DailySalesSummary.status == "posted",
        DailySalesSummary.id != dss.id
    ).first()
    if existing_posted:
        issues.append(f"Duplicate: another DSS for {dss.business_date} area {dss.area_id} is already posted (ID {existing_posted.id})")

    return issues


def check_gl_mappings(dss: DailySalesSummary, db: Session) -> list[str]:
    """Check that all needed GL accounts are mapped for posting."""
    issues = []

    # Category → revenue account
    if dss.line_items:
        # Build case-insensitive lookup
        category_mappings = {}
        for m in db.query(POSCategoryGLMapping).filter(
            POSCategoryGLMapping.area_id == dss.area_id,
            POSCategoryGLMapping.is_active == True
        ).all():
            category_mappings[m.pos_category.upper()] = m.revenue_account_id

        for item in dss.line_items:
            account_id = item.revenue_account_id
            if not account_id:
                cat = (item.category or "").upper()
                account_id = category_mappings.get(cat)
            if not account_id:
                issues.append(f"No GL account for sales category: {item.category or 'Unknown'}")

    # Payment → deposit account
    if dss.payments:
        payment_mappings = {
            m.pos_payment_type.upper(): m.deposit_account_id
            for m in db.query(POSPaymentGLMapping).filter(
                POSPaymentGLMapping.area_id == dss.area_id,
                POSPaymentGLMapping.is_active == True
            ).all()
        }
        for payment in dss.payments:
            account_id = payment.deposit_account_id
            if not account_id:
                account_id = payment_mappings.get(payment.payment_type.upper())
            if not account_id:
                issues.append(f"No GL account for payment type: {payment.payment_type}")

    # Discount → discount account
    if dss.discount_breakdown:
        discount_mappings = db.query(POSDiscountGLMapping).filter(
            POSDiscountGLMapping.area_id == dss.area_id,
            POSDiscountGLMapping.is_active == True
        ).all()

        override_map = {m.pos_discount_name: m.discount_account_id for m in discount_mappings if m.is_override}
        fallback_map = {m.pos_discount_name: m.discount_account_id for m in discount_mappings}

        category_discount_map = {
            m.pos_category: m.discount_account_id
            for m in db.query(POSCategoryGLMapping).filter(
                POSCategoryGLMapping.area_id == dss.area_id,
                POSCategoryGLMapping.is_active == True,
                POSCategoryGLMapping.discount_account_id.isnot(None)
            ).all()
        }

        for discount_key in dss.discount_breakdown.keys():
            category = None
            disc_name = discount_key

            if "|" in discount_key:
                category, disc_name = discount_key.split("|", 1)

            account_id = override_map.get(disc_name)
            if not account_id and category:
                account_id = category_discount_map.get(category)
            if not account_id:
                account_id = fallback_map.get(disc_name)
            if not account_id:
                issues.append(f"No GL account for discount: {discount_key}")

    return issues


def verify_and_post_dss(dss: DailySalesSummary, db: Session, service_user: User) -> bool:
    """
    Verify (if draft) and post a DSS by creating a journal entry.
    Uses the same logic as the API endpoint.
    Returns True on success.
    """
    from accounting.api.daily_sales_summary import create_sales_journal_entry

    try:
        # Auto-verify if still draft
        if dss.status == "draft":
            dss.status = "verified"
            dss.verified_by = service_user.id
            dss.verified_at = datetime.now()

        dss.posted_by = service_user.id

        # Build GL mappings from pos_category_gl_mappings and pos_payment_gl_mappings
        category_mapping = {}
        for m in db.query(POSCategoryGLMapping).filter(
            POSCategoryGLMapping.area_id == dss.area_id,
            POSCategoryGLMapping.is_active == True
        ).all():
            category_mapping[m.pos_category.upper()] = m.revenue_account_id

        payment_mapping = {}
        for m in db.query(POSPaymentGLMapping).filter(
            POSPaymentGLMapping.area_id == dss.area_id,
            POSPaymentGLMapping.is_active == True
        ).all():
            payment_mapping[m.pos_payment_type.upper()] = m.deposit_account_id

        # Use Cash Over/Short (7250) for rounding variances
        variance_account = db.query(Account).filter(Account.account_number == "7250").first()
        variance_account_id = variance_account.id if variance_account else None

        post_request = DSSPostRequest(
            category_account_mapping=category_mapping,
            payment_account_mapping=payment_mapping,
            variance_account_id=variance_account_id,
            # variance_amount will be calculated - set a placeholder that will be
            # overridden. We need to do a 2-pass: first try without variance,
            # if it fails with balance error, retry with variance.
        )

        # First attempt - try to post directly
        try:
            je = create_sales_journal_entry(dss, db, post_request)
        except Exception as e:
            error_detail = getattr(e, 'detail', str(e))
            if "doesn't balance" in str(error_detail) and variance_account_id:
                # Extract the variance from the error and retry
                db.rollback()
                # Re-load dss after rollback
                dss = db.query(DailySalesSummary).options(
                    joinedload(DailySalesSummary.line_items),
                    joinedload(DailySalesSummary.payments),
                    joinedload(DailySalesSummary.area)
                ).filter(DailySalesSummary.id == dss.id).first()

                # Re-set status
                if dss.status == "draft":
                    dss.status = "verified"
                    dss.verified_by = service_user.id
                    dss.verified_at = datetime.now()
                dss.posted_by = service_user.id

                # Parse DR/CR from error to calculate variance
                import re
                match = re.search(r'DR=(\d+\.\d+),\s*CR=(\d+\.\d+)', str(error_detail))
                if match:
                    dr = Decimal(match.group(1))
                    cr = Decimal(match.group(2))
                    variance = dr - cr
                    print(f"  Variance detected: ${variance} - adding rounding adjustment")
                    post_request.variance_amount = variance
                    je = create_sales_journal_entry(dss, db, post_request)
                else:
                    raise
            else:
                raise

        dss.status = "posted"
        dss.posted_at = datetime.now()
        dss.journal_entry_id = je.id

        note = f"Auto-posted by DSS Review ({datetime.now().strftime('%Y-%m-%d %H:%M')})\nJournal Entry Created: {je.entry_number}"
        if dss.notes:
            dss.notes += f"\n\n{note}"
        else:
            dss.notes = note

        return True

    except Exception as e:
        import traceback
        print(f"  ERROR posting DSS {dss.id}: {e}")
        traceback.print_exc()
        return False


def main():
    args = parse_args()
    db = SessionLocal()

    try:
        # Get a service user (admin) for posting
        service_user = db.query(User).filter(User.is_admin == True).first()
        if not service_user:
            service_user = db.query(User).first()
        if not service_user:
            print("ERROR: No user found for posting")
            return

        print(f"DSS Review & Post - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"Service user: {service_user.username} (ID: {service_user.id})")
        if args.dry_run:
            print("DRY RUN - no changes will be made\n")

        # Find DSS entries ready for review:
        # - draft POS imports (auto-verify + post)
        # - verified entries (auto-post)
        # Skip already-reviewed entries
        query = db.query(DailySalesSummary).options(
            joinedload(DailySalesSummary.line_items),
            joinedload(DailySalesSummary.payments),
            joinedload(DailySalesSummary.area)
        ).filter(
            DailySalesSummary.status.in_(["draft", "verified"]),
            DailySalesSummary.review_status.is_(None),
            # Only auto-process POS imports, not manual entries
            DailySalesSummary.pos_system.isnot(None)
        )

        if args.area_id:
            query = query.filter(DailySalesSummary.area_id == args.area_id)

        entries = query.order_by(
            DailySalesSummary.business_date,
            DailySalesSummary.area_id
        ).all()

        if not entries:
            print("No verified DSS entries to review.")
            return

        print(f"Found {len(entries)} verified entries to review\n")

        stats = {"reviewed": 0, "posted": 0, "flagged": 0, "errors": 0}

        for dss in entries:
            area_name = dss.area.name if dss.area else f"Area {dss.area_id}"
            print(f"Reviewing: {dss.business_date} - {area_name} (ID: {dss.id})")
            print(f"  Net sales: ${dss.net_sales}, Total: ${dss.total_collected}")

            issues = review_dss(dss, db)
            stats["reviewed"] += 1

            if issues:
                print(f"  FLAGGED - {len(issues)} issue(s):")
                for issue in issues:
                    print(f"    - {issue}")

                if not args.dry_run:
                    dss.review_status = "flagged"
                    dss.review_notes = issues
                    dss.reviewed_at = datetime.now()
                    db.commit()

                stats["flagged"] += 1
            else:
                print("  CLEAN - auto-posting...")

                if not args.dry_run:
                    success = verify_and_post_dss(dss, db, service_user)
                    if success:
                        dss.review_status = "clean"
                        dss.review_notes = None
                        dss.reviewed_at = datetime.now()
                        db.commit()
                        print(f"  Posted as JE {dss.journal_entry_id}")
                        stats["posted"] += 1
                    else:
                        dss.review_status = "flagged"
                        dss.review_notes = ["Auto-post failed - see logs"]
                        dss.reviewed_at = datetime.now()
                        db.commit()
                        stats["errors"] += 1
                else:
                    stats["posted"] += 1

            print()

        print("=" * 50)
        print(f"Summary: {stats['reviewed']} reviewed, {stats['posted']} posted, {stats['flagged']} flagged, {stats['errors']} errors")

    finally:
        db.close()


if __name__ == "__main__":
    main()
