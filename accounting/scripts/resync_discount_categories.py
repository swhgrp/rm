"""
Re-sync POS sales data to apply category-aware discount routing.

This script:
1. Re-syncs all pos_daily_sales_cache entries from Clover API
   (now produces "Category|DiscountName" keyed discount breakdowns)
2. Updates draft DSS entries' discount_breakdown from re-synced cache
3. For posted DSS entries, updates discount_breakdown AND fixes JE discount lines

Usage:
    docker compose exec accounting-app python scripts/resync_discount_categories.py [--dry-run] [--area-id N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
"""
import asyncio
import sys
import os
import argparse
from datetime import date, datetime
from decimal import Decimal

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from accounting.db.database import SessionLocal
from accounting.models.pos import POSConfiguration, POSDailySalesCache, POSCategoryGLMapping, POSDiscountGLMapping
from accounting.models.daily_sales_summary import DailySalesSummary
from accounting.models.journal_entry import JournalEntry, JournalEntryLine
from accounting.services.pos_sync_service import POSSyncService


def parse_args():
    parser = argparse.ArgumentParser(description="Re-sync POS discount data with category routing")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without making changes")
    parser.add_argument("--area-id", type=int, help="Only process specific area (default: all)")
    parser.add_argument("--start-date", type=str, help="Start date YYYY-MM-DD (default: earliest cached)")
    parser.add_argument("--end-date", type=str, help="End date YYYY-MM-DD (default: latest cached)")
    return parser.parse_args()


def fix_posted_je_discount_lines(db: Session, dss: DailySalesSummary, new_discount_breakdown: dict, dry_run: bool):
    """Fix journal entry discount lines for a posted DSS entry.

    For posted JEs, we preserve the EXISTING total discount amount to keep
    the JE balanced. We only redistribute across GL accounts based on the
    new category proportions from Clover.
    """
    if not dss.journal_entry_id:
        print(f"    WARNING: Posted DSS {dss.id} has no journal_entry_id, skipping JE fix")
        return

    je = db.query(JournalEntry).filter(JournalEntry.id == dss.journal_entry_id).first()
    if not je:
        print(f"    WARNING: JE {dss.journal_entry_id} not found for DSS {dss.id}")
        return

    discount_mappings = db.query(POSDiscountGLMapping).filter(
        POSDiscountGLMapping.area_id == dss.area_id,
        POSDiscountGLMapping.is_active == True
    ).all()
    override_map = {m.pos_discount_name: m.discount_account_id for m in discount_mappings if m.is_override}
    fallback_map = {m.pos_discount_name: m.discount_account_id for m in discount_mappings}

    category_mappings = db.query(POSCategoryGLMapping).filter(
        POSCategoryGLMapping.area_id == dss.area_id,
        POSCategoryGLMapping.is_active == True,
        POSCategoryGLMapping.discount_account_id.isnot(None)
    ).all()
    category_discount_map = {m.pos_category: m.discount_account_id for m in category_mappings}

    # Get all possible discount account IDs
    all_discount_account_ids = set()
    for m in discount_mappings:
        all_discount_account_ids.add(m.discount_account_id)
    for m in category_mappings:
        if m.discount_account_id:
            all_discount_account_ids.add(m.discount_account_id)

    # Find existing discount lines on the JE (debit lines to discount accounts)
    old_discount_lines = []
    for line in je.lines:
        if line.debit_amount > 0 and line.account_id in all_discount_account_ids:
            old_discount_lines.append(line)

    if not old_discount_lines and not new_discount_breakdown:
        return

    old_total = sum(l.debit_amount for l in old_discount_lines)

    # Calculate proportional allocation from new breakdown
    # Route each discount to the correct GL account based on category
    new_gl_proportions = {}  # {account_id: {"raw_amount": Decimal, "descriptions": []}}
    for discount_key, amount in new_discount_breakdown.items():
        discount_amount = abs(Decimal(str(amount)))
        if discount_amount <= 0:
            continue

        if "|" in discount_key:
            category, disc_name = discount_key.split("|", 1)
        else:
            category = None
            disc_name = discount_key

        account_id = override_map.get(disc_name)
        if not account_id and category:
            account_id = category_discount_map.get(category)
        if not account_id:
            account_id = fallback_map.get(disc_name)

        if not account_id:
            print(f"    WARNING: No discount account for '{discount_key}' - skipping")
            continue

        if account_id not in new_gl_proportions:
            new_gl_proportions[account_id] = {"raw_amount": Decimal("0.00"), "descriptions": []}
        new_gl_proportions[account_id]["raw_amount"] += discount_amount
        new_gl_proportions[account_id]["descriptions"].append(disc_name)

    new_raw_total = sum(info["raw_amount"] for info in new_gl_proportions.values())

    if new_raw_total <= 0:
        print(f"    WARNING: No valid discount routing found, skipping JE fix")
        return

    # Scale amounts proportionally to match old JE total (preserves JE balance)
    new_gl_lines = {}
    remaining = old_total
    sorted_accounts = sorted(new_gl_proportions.items(), key=lambda x: x[1]["raw_amount"], reverse=True)

    for i, (acct_id, info) in enumerate(sorted_accounts):
        if i == len(sorted_accounts) - 1:
            # Last account gets remainder to avoid rounding issues
            scaled_amount = remaining
        else:
            scaled_amount = (old_total * info["raw_amount"] / new_raw_total).quantize(Decimal("0.01"))
            remaining -= scaled_amount

        new_gl_lines[acct_id] = {"amount": scaled_amount, "descriptions": info["descriptions"]}

    if dry_run:
        print(f"    Would update JE {je.entry_number} (preserving total ${old_total}):")
        print(f"      Old lines ({len(old_discount_lines)}):")
        for line in old_discount_lines:
            print(f"        DR ${line.debit_amount} → account {line.account_id} ({line.description})")
        print(f"      New lines ({len(new_gl_lines)}):")
        for acct_id, info in new_gl_lines.items():
            names = list(dict.fromkeys(info["descriptions"]))
            desc = ", ".join(names[:3]) + (f" + {len(names)-3} more" if len(names) > 3 else "")
            print(f"        DR ${info['amount']} → account {acct_id} ({desc})")
        return

    # Delete old discount lines
    for line in old_discount_lines:
        db.delete(line)
    db.flush()

    # Get next line number
    max_line = max((l.line_number for l in je.lines if l not in old_discount_lines), default=0)
    line_number = max_line + 1

    # Create new discount lines
    for account_id, info in new_gl_lines.items():
        if info["amount"] <= 0:
            continue
        unique_names = list(dict.fromkeys(info["descriptions"]))
        if len(unique_names) <= 3:
            description = ", ".join(unique_names)
        else:
            description = f"{unique_names[0]} + {len(unique_names) - 1} more"

        new_line = JournalEntryLine(
            journal_entry_id=je.id,
            line_number=line_number,
            account_id=account_id,
            area_id=dss.area_id,
            description=description,
            debit_amount=info["amount"],
            credit_amount=Decimal("0.00")
        )
        db.add(new_line)
        line_number += 1

    # Verify JE still balances
    db.flush()
    db.refresh(je)
    total_debits = sum(l.debit_amount for l in je.lines)
    total_credits = sum(l.credit_amount for l in je.lines)
    if abs(total_debits - total_credits) > Decimal("0.02"):
        print(f"    ERROR: JE {je.entry_number} unbalanced after fix: DR=${total_debits}, CR=${total_credits}")
        db.rollback()
        return

    print(f"    Fixed JE {je.entry_number}: {len(old_discount_lines)} old lines → {len(new_gl_lines)} new lines (total ${old_total})")


async def resync_area(db: Session, config: POSConfiguration, start_date: date, end_date: date, dry_run: bool):
    """Re-sync all cache entries for an area from Clover."""
    print(f"\n{'='*60}")
    print(f"Processing area {config.area_id} ({config.provider})")
    print(f"Date range: {start_date} to {end_date}")
    print(f"{'='*60}")

    sync_service = POSSyncService(db)

    # Re-sync from Clover (this updates pos_daily_sales_cache with new category|discount keys)
    if not dry_run:
        print(f"  Re-syncing from Clover API...")
        try:
            result = await sync_service.sync_location(
                area_id=config.area_id,
                start_date=start_date,
                end_date=end_date,
                user_id=None  # Don't auto-create DSS
            )
            print(f"  Sync result: {result.get('synced', 0)} synced, {result.get('skipped', 0)} updated, {result.get('errors', [])} errors")
        except Exception as e:
            print(f"  ERROR syncing: {e}")
            return
    else:
        print(f"  [DRY RUN] Would re-sync from Clover API")

    # Now update DSS entries from the re-synced cache
    cache_entries = db.query(POSDailySalesCache).filter(
        POSDailySalesCache.area_id == config.area_id,
        POSDailySalesCache.sale_date >= start_date,
        POSDailySalesCache.sale_date <= end_date
    ).all()

    print(f"\n  Found {len(cache_entries)} cache entries")

    for cache in cache_entries:
        dss = db.query(DailySalesSummary).filter(
            DailySalesSummary.area_id == config.area_id,
            DailySalesSummary.business_date == cache.sale_date
        ).first()

        if not dss:
            continue

        old_discounts = dss.discount_breakdown or {}
        new_discounts = cache.discounts or {}

        # Check if anything changed
        if old_discounts == new_discounts:
            continue

        print(f"\n  {cache.sale_date} (DSS {dss.id}, status={dss.status}):")
        print(f"    Old: {old_discounts}")
        print(f"    New: {new_discounts}")

        if not dry_run:
            dss.discount_breakdown = new_discounts
            db.flush()

        # Fix posted JE lines if applicable
        if dss.status == 'posted':
            print(f"    Fixing posted JE...")
            fix_posted_je_discount_lines(db, dss, new_discounts, dry_run)

    if not dry_run:
        db.commit()
        print(f"\n  Changes committed for area {config.area_id}")


async def main():
    args = parse_args()

    db = SessionLocal()
    try:
        # Get POS configurations
        query = db.query(POSConfiguration).filter(POSConfiguration.is_active == True)
        if args.area_id:
            query = query.filter(POSConfiguration.area_id == args.area_id)
        configs = query.all()

        if not configs:
            print("No active POS configurations found")
            return

        print(f"Found {len(configs)} POS configuration(s)")
        if args.dry_run:
            print("*** DRY RUN MODE - No changes will be made ***")

        for config in configs:
            # Determine date range
            if args.start_date:
                start = date.fromisoformat(args.start_date)
            else:
                # Get earliest cache entry for this area
                earliest = db.query(POSDailySalesCache.sale_date).filter(
                    POSDailySalesCache.area_id == config.area_id
                ).order_by(POSDailySalesCache.sale_date.asc()).first()
                start = earliest[0] if earliest else date(2026, 1, 1)

            if args.end_date:
                end = date.fromisoformat(args.end_date)
            else:
                # Get latest cache entry for this area
                latest = db.query(POSDailySalesCache.sale_date).filter(
                    POSDailySalesCache.area_id == config.area_id
                ).order_by(POSDailySalesCache.sale_date.desc()).first()
                end = latest[0] if latest else date.today()

            await resync_area(db, config, start, end, args.dry_run)

    finally:
        db.close()

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
