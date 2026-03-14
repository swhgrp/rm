"""
GL Anomaly Rules Engine — deterministic checks against posted journal entries.

All functions are synchronous (accounting service uses sync SQLAlchemy).
Each check returns a list of raw flag dicts ready for persistence.
"""
import logging
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
from collections import defaultdict

from sqlalchemy import func as sqlfunc, and_, literal_column
from sqlalchemy.orm import Session

from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.account import Account, AccountType
from accounting.gl_review.models import (
    GLAccountBaseline,
    UNBALANCED_ENTRY, DUPLICATE_ENTRY, WRONG_NORMAL_BALANCE,
    MISSING_DESCRIPTION, ROUND_NUMBER_ANOMALY, OUT_OF_HOURS_POSTING,
    STATISTICAL_OUTLIER, NEGATIVE_BALANCE, FOOD_COST_SPIKE,
    SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL,
)

logger = logging.getLogger(__name__)

ZERO = Decimal('0')
PENNY = Decimal('0.01')
THOUSAND = Decimal('1000')


def run_rules_engine(db: Session, area_id: int, date_from: date, date_to: date) -> list[dict]:
    """
    Run all deterministic checks for the given area and date range.
    Returns a list of raw flag dicts (not yet persisted).
    """
    checks = [
        ("check_unbalanced_entries", check_unbalanced_entries),
        ("check_duplicate_entries", check_duplicate_entries),
        ("check_wrong_normal_balance", check_wrong_normal_balance),
        ("check_missing_descriptions", check_missing_descriptions),
        ("check_round_numbers", check_round_numbers),
        ("check_out_of_hours", check_out_of_hours),
        ("check_statistical_outliers", check_statistical_outliers),
        ("check_negative_balances", check_negative_balances),
        ("check_food_cost_spike", check_food_cost_spike),
    ]

    all_flags = []
    for name, check_fn in checks:
        try:
            flags = check_fn(db, area_id, date_from, date_to)
            all_flags.extend(flags)
            if flags:
                logger.info(f"{name}: found {len(flags)} flag(s) for area_id={area_id}")
        except Exception:
            logger.exception(f"{name} failed for area_id={area_id}, skipping")

    return all_flags


def _get_posted_entry_ids_for_area(db: Session, area_id: int, date_from: date, date_to: date) -> list[int]:
    """Get IDs of posted journal entries that have at least one line for this area in the date range."""
    rows = (
        db.query(JournalEntry.id)
        .join(JournalEntryLine, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .filter(
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
            JournalEntryLine.area_id == area_id,
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Check 1: Unbalanced entries
# ---------------------------------------------------------------------------
def check_unbalanced_entries(db: Session, area_id: int, date_from: date, date_to: date) -> list[dict]:
    """Flag journal entries where total debits != total credits."""
    entry_ids = _get_posted_entry_ids_for_area(db, area_id, date_from, date_to)
    if not entry_ids:
        return []

    # Sum debits and credits per entry (all lines, not just this area's)
    rows = (
        db.query(
            JournalEntryLine.journal_entry_id,
            sqlfunc.sum(JournalEntryLine.debit_amount).label('total_debits'),
            sqlfunc.sum(JournalEntryLine.credit_amount).label('total_credits'),
        )
        .filter(JournalEntryLine.journal_entry_id.in_(entry_ids))
        .group_by(JournalEntryLine.journal_entry_id)
        .all()
    )

    flags = []
    for row in rows:
        diff = abs(Decimal(str(row.total_debits or 0)) - Decimal(str(row.total_credits or 0)))
        if diff > PENNY:
            flags.append({
                'flag_type': UNBALANCED_ENTRY,
                'severity': SEVERITY_CRITICAL,
                'title': f"Unbalanced journal entry (off by ${diff:,.2f})",
                'detail': f"Entry debits={row.total_debits}, credits={row.total_credits}, difference={diff}",
                'flagged_value': diff,
                'journal_entry_id': row.journal_entry_id,
                'journal_entry_line_id': None,
                'account_id': None,
                'period_date': date_from,
                'expected_range_low': None,
                'expected_range_high': None,
            })
    return flags


# ---------------------------------------------------------------------------
# Check 2: Duplicate entries
# ---------------------------------------------------------------------------
def check_duplicate_entries(db: Session, area_id: int, date_from: date, date_to: date) -> list[dict]:
    """Flag lines with identical (account, debit, credit, area, date) posted more than once."""
    # Find duplicates
    subq = (
        db.query(
            JournalEntryLine.account_id,
            JournalEntryLine.debit_amount,
            JournalEntryLine.credit_amount,
            JournalEntry.entry_date,
            sqlfunc.count().label('cnt'),
            sqlfunc.array_agg(JournalEntryLine.id).label('line_ids'),
            sqlfunc.array_agg(JournalEntryLine.journal_entry_id).label('entry_ids'),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .filter(
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
            JournalEntryLine.area_id == area_id,
        )
        .group_by(
            JournalEntryLine.account_id,
            JournalEntryLine.debit_amount,
            JournalEntryLine.credit_amount,
            JournalEntry.entry_date,
        )
        .having(sqlfunc.count() > 1)
        .all()
    )

    # Check for recurring pattern: if this combo appears >3 times in last 90 days, skip
    lookback_start = date_from - timedelta(days=90)

    flags = []
    for row in subq:
        debit = Decimal(str(row.debit_amount or 0))
        credit = Decimal(str(row.credit_amount or 0))
        amount = debit if debit > ZERO else credit

        # Skip zero-amount lines
        if amount == ZERO:
            continue

        # Check if this is a known recurring pattern
        recurring_count = (
            db.query(sqlfunc.count())
            .select_from(JournalEntryLine)
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .filter(
                JournalEntry.status == JournalEntryStatus.POSTED,
                JournalEntry.entry_date >= lookback_start,
                JournalEntryLine.account_id == row.account_id,
                JournalEntryLine.debit_amount == row.debit_amount,
                JournalEntryLine.credit_amount == row.credit_amount,
                JournalEntryLine.area_id == area_id,
            )
            .scalar()
        )
        if recurring_count > 3:
            continue

        account = db.query(Account).filter(Account.id == row.account_id).first()
        account_name = account.account_name if account else f"Account #{row.account_id}"

        flags.append({
            'flag_type': DUPLICATE_ENTRY,
            'severity': SEVERITY_WARNING,
            'title': f"Duplicate posting: ${amount:,.2f} to {account_name} on {row.entry_date}",
            'detail': f"Found {row.cnt} identical lines (account={row.account_id}, amount=${amount:,.2f}) on {row.entry_date}. Entry IDs: {list(set(row.entry_ids))}",
            'flagged_value': amount,
            'journal_entry_id': row.entry_ids[0] if row.entry_ids else None,
            'journal_entry_line_id': row.line_ids[0] if row.line_ids else None,
            'account_id': row.account_id,
            'period_date': row.entry_date,
            'expected_range_low': None,
            'expected_range_high': None,
        })
    return flags


# ---------------------------------------------------------------------------
# Check 3: Wrong normal balance direction
# ---------------------------------------------------------------------------
def check_wrong_normal_balance(db: Session, area_id: int, date_from: date, date_to: date) -> list[dict]:
    """Flag lines that go against the account's normal balance direction."""
    # Revenue/COGS with debits, Expense with credits
    lines = (
        db.query(JournalEntryLine, Account, JournalEntry.entry_date)
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .join(Account, JournalEntryLine.account_id == Account.id)
        .filter(
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
            JournalEntryLine.area_id == area_id,
        )
        .all()
    )

    flags = []
    for line, account, entry_date in lines:
        debit = Decimal(str(line.debit_amount or 0))
        credit = Decimal(str(line.credit_amount or 0))
        flagged = False
        amount = ZERO

        if account.account_type in (AccountType.REVENUE, AccountType.COGS) and debit > ZERO:
            flagged = True
            amount = debit
            direction = "debit"
        elif account.account_type == AccountType.EXPENSE and credit > ZERO:
            flagged = True
            amount = credit
            direction = "credit"

        if flagged:
            flags.append({
                'flag_type': WRONG_NORMAL_BALANCE,
                'severity': SEVERITY_INFO,
                'title': f"Unusual {direction} of ${amount:,.2f} to {account.account_type.value} account {account.account_name}",
                'detail': f"Account {account.account_number} ({account.account_name}) is a {account.account_type.value} account. A {direction} of ${amount:,.2f} goes against normal balance direction.",
                'flagged_value': amount,
                'journal_entry_id': line.journal_entry_id,
                'journal_entry_line_id': line.id,
                'account_id': account.id,
                'period_date': entry_date,
                'expected_range_low': None,
                'expected_range_high': None,
            })
    return flags


# ---------------------------------------------------------------------------
# Check 4: Missing descriptions
# ---------------------------------------------------------------------------
def check_missing_descriptions(db: Session, area_id: int, date_from: date, date_to: date) -> list[dict]:
    """Flag posted journal entries with no description."""
    entry_ids = _get_posted_entry_ids_for_area(db, area_id, date_from, date_to)
    if not entry_ids:
        return []

    entries = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.id.in_(entry_ids),
            (JournalEntry.description == None) | (JournalEntry.description == ''),
        )
        .all()
    )

    flags = []
    for entry in entries:
        flags.append({
            'flag_type': MISSING_DESCRIPTION,
            'severity': SEVERITY_INFO,
            'title': f"Journal entry {entry.entry_number} has no description",
            'detail': f"Entry #{entry.entry_number} dated {entry.entry_date} has no memo/description.",
            'flagged_value': None,
            'journal_entry_id': entry.id,
            'journal_entry_line_id': None,
            'account_id': None,
            'period_date': entry.entry_date,
            'expected_range_low': None,
            'expected_range_high': None,
        })
    return flags


# ---------------------------------------------------------------------------
# Check 5: Round number anomaly
# ---------------------------------------------------------------------------
def check_round_numbers(db: Session, area_id: int, date_from: date, date_to: date) -> list[dict]:
    """Flag suspiciously round amounts in accounts where that's uncommon."""
    # Only check accounts that have baselines
    baselines = (
        db.query(GLAccountBaseline)
        .filter(GLAccountBaseline.area_id == area_id)
        .all()
    )
    baseline_account_ids = {b.account_id for b in baselines}
    if not baseline_account_ids:
        return []

    lines = (
        db.query(JournalEntryLine, Account.account_name, Account.account_number, JournalEntry.entry_date)
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .join(Account, JournalEntryLine.account_id == Account.id)
        .filter(
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
            JournalEntryLine.area_id == area_id,
            JournalEntryLine.account_id.in_(baseline_account_ids),
        )
        .all()
    )

    flags = []
    for line, account_name, account_number, entry_date in lines:
        debit = Decimal(str(line.debit_amount or 0))
        credit = Decimal(str(line.credit_amount or 0))
        amount = debit if debit > ZERO else credit

        if amount <= THOUSAND:
            continue
        if amount % THOUSAND != ZERO:
            continue

        flags.append({
            'flag_type': ROUND_NUMBER_ANOMALY,
            'severity': SEVERITY_INFO,
            'title': f"Round amount ${amount:,.2f} posted to {account_name}",
            'detail': f"Account {account_number} ({account_name}) received a round ${amount:,.2f} posting. Round amounts in this account may indicate an estimate or placeholder entry.",
            'flagged_value': amount,
            'journal_entry_id': line.journal_entry_id,
            'journal_entry_line_id': line.id,
            'account_id': line.account_id,
            'period_date': entry_date,
            'expected_range_low': None,
            'expected_range_high': None,
        })
    return flags


# ---------------------------------------------------------------------------
# Check 6: Out-of-hours posting
# ---------------------------------------------------------------------------
def check_out_of_hours(db: Session, area_id: int, date_from: date, date_to: date) -> list[dict]:
    """Flag entries created outside 6 AM – 11 PM Eastern Time."""
    entry_ids = _get_posted_entry_ids_for_area(db, area_id, date_from, date_to)
    if not entry_ids:
        return []

    entries = (
        db.query(JournalEntry)
        .filter(JournalEntry.id.in_(entry_ids))
        .all()
    )

    flags = []
    for entry in entries:
        if entry.created_at is None:
            continue

        # DB/server runs in America/New_York (TZ=America/New_York in docker-compose)
        # created_at timestamps are in Eastern Time
        hour = entry.created_at.hour
        if hour < 6 or hour >= 23:
            flags.append({
                'flag_type': OUT_OF_HOURS_POSTING,
                'severity': SEVERITY_INFO,
                'title': f"After-hours posting: entry {entry.entry_number} at {entry.created_at.strftime('%I:%M %p')}",
                'detail': f"Entry #{entry.entry_number} was created at {entry.created_at.strftime('%Y-%m-%d %I:%M %p ET')} — outside normal business hours (6 AM – 11 PM).",
                'flagged_value': None,
                'journal_entry_id': entry.id,
                'journal_entry_line_id': None,
                'account_id': None,
                'period_date': entry.entry_date,
                'expected_range_low': None,
                'expected_range_high': None,
            })
    return flags


# ---------------------------------------------------------------------------
# Check 7: Statistical outliers
# ---------------------------------------------------------------------------
def check_statistical_outliers(db: Session, area_id: int, date_from: date, date_to: date) -> list[dict]:
    """Flag accounts where current period activity exceeds 2.5 stddev from historical mean."""
    baselines = (
        db.query(GLAccountBaseline)
        .filter(GLAccountBaseline.area_id == area_id)
        .all()
    )
    if not baselines:
        return []

    # Calculate number of days in the range for pro-rating
    range_days = (date_to - date_from).days + 1
    month_ratio = Decimal(str(range_days)) / Decimal('30')

    # Get current period activity per account
    activity_rows = (
        db.query(
            JournalEntryLine.account_id,
            sqlfunc.sum(JournalEntryLine.debit_amount + JournalEntryLine.credit_amount).label('activity'),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .filter(
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
            JournalEntryLine.area_id == area_id,
        )
        .group_by(JournalEntryLine.account_id)
        .all()
    )

    activity_map = {row.account_id: Decimal(str(row.activity or 0)) for row in activity_rows}

    flags = []
    for baseline in baselines:
        activity = activity_map.get(baseline.account_id)
        if activity is None:
            continue

        avg = Decimal(str(baseline.avg_monthly_activity or 0))
        stddev = Decimal(str(baseline.stddev_monthly_activity or 0))

        if stddev <= ZERO:
            continue

        # Pro-rate the baseline to the date range
        expected_avg = avg * month_ratio
        expected_stddev = stddev * month_ratio
        upper_bound = expected_avg + (Decimal('2.5') * expected_stddev)

        if activity > upper_bound:
            account = db.query(Account).filter(Account.id == baseline.account_id).first()
            account_name = account.account_name if account else f"Account #{baseline.account_id}"

            flags.append({
                'flag_type': STATISTICAL_OUTLIER,
                'severity': SEVERITY_WARNING,
                'title': f"Unusual activity on {account_name}: ${activity:,.2f} vs expected ${expected_avg:,.2f}",
                'detail': f"Account {baseline.account_code} ({account_name}) has ${activity:,.2f} in activity for this period. Historical average (pro-rated) is ${expected_avg:,.2f} with stddev ${expected_stddev:,.2f}. This exceeds 2.5 standard deviations.",
                'flagged_value': activity,
                'journal_entry_id': None,
                'journal_entry_line_id': None,
                'account_id': baseline.account_id,
                'period_date': date_from,
                'expected_range_low': expected_avg - (Decimal('2.5') * expected_stddev),
                'expected_range_high': upper_bound,
            })
    return flags


# ---------------------------------------------------------------------------
# Check 8: Negative balances
# ---------------------------------------------------------------------------
def check_negative_balances(db: Session, area_id: int, date_from: date, date_to: date) -> list[dict]:
    """Flag accounts with balance in the wrong direction for their type."""
    # Compute running net balance (debits - credits) for all accounts with activity in this area
    rows = (
        db.query(
            JournalEntryLine.account_id,
            Account.account_number,
            Account.account_name,
            Account.account_type,
            sqlfunc.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount).label('net_balance'),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .join(Account, JournalEntryLine.account_id == Account.id)
        .filter(
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntryLine.area_id == area_id,
            # All time up to date_to for running balance
            JournalEntry.entry_date <= date_to,
        )
        .group_by(
            JournalEntryLine.account_id,
            Account.account_number,
            Account.account_name,
            Account.account_type,
        )
        .all()
    )

    flags = []
    for row in rows:
        net = Decimal(str(row.net_balance or 0))
        wrong_direction = False

        # Debit-normal accounts (ASSET, EXPENSE, COGS): net should be >= 0
        if row.account_type in (AccountType.ASSET, AccountType.EXPENSE, AccountType.COGS):
            if net < ZERO:
                wrong_direction = True
        # Credit-normal accounts (LIABILITY, EQUITY, REVENUE): net should be <= 0 (credits > debits)
        elif row.account_type in (AccountType.LIABILITY, AccountType.EQUITY, AccountType.REVENUE):
            if net > ZERO:
                wrong_direction = True

        if wrong_direction:
            # Cash accounts get critical severity
            is_cash = row.account_type == AccountType.ASSET and str(row.account_number).startswith('10')
            severity = SEVERITY_CRITICAL if is_cash else SEVERITY_WARNING

            flags.append({
                'flag_type': NEGATIVE_BALANCE,
                'severity': severity,
                'title': f"Wrong-direction balance on {row.account_name}: ${abs(net):,.2f}",
                'detail': f"Account {row.account_number} ({row.account_name}, type={row.account_type.value}) has a net balance of ${net:,.2f} as of {date_to}. This is the wrong direction for a {row.account_type.value} account.",
                'flagged_value': net,
                'journal_entry_id': None,
                'journal_entry_line_id': None,
                'account_id': row.account_id,
                'period_date': date_to,
                'expected_range_low': None,
                'expected_range_high': None,
            })
    return flags


# ---------------------------------------------------------------------------
# Check 9: Food cost spike
# ---------------------------------------------------------------------------
def check_food_cost_spike(db: Session, area_id: int, date_from: date, date_to: date) -> list[dict]:
    """Flag if food cost % increased > 3 percentage points vs prior period."""

    def _get_cogs_and_revenue(db: Session, area_id: int, start: date, end: date):
        """Sum COGS and Revenue for the area in the date range."""
        rows = (
            db.query(
                Account.account_type,
                sqlfunc.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount).label('net'),
            )
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .join(Account, JournalEntryLine.account_id == Account.id)
            .filter(
                JournalEntry.status == JournalEntryStatus.POSTED,
                JournalEntry.entry_date >= start,
                JournalEntry.entry_date <= end,
                JournalEntryLine.area_id == area_id,
                Account.account_type.in_([AccountType.COGS, AccountType.REVENUE]),
            )
            .group_by(Account.account_type)
            .all()
        )
        cogs = ZERO
        revenue = ZERO
        for row in rows:
            net = Decimal(str(row.net or 0))
            if row.account_type == AccountType.COGS:
                cogs = abs(net)  # COGS is debit-normal, so net is positive
            elif row.account_type == AccountType.REVENUE:
                revenue = abs(net)  # Revenue is credit-normal, so net is negative; abs it
        return cogs, revenue

    # Current period
    cogs_current, revenue_current = _get_cogs_and_revenue(db, area_id, date_from, date_to)
    if revenue_current <= ZERO:
        return []

    # Prior period (same length, shifted back)
    range_days = (date_to - date_from).days + 1
    prior_to = date_from - timedelta(days=1)
    prior_from = prior_to - timedelta(days=range_days - 1)

    cogs_prior, revenue_prior = _get_cogs_and_revenue(db, area_id, prior_from, prior_to)
    if revenue_prior <= ZERO:
        return []

    current_pct = (cogs_current / revenue_current) * Decimal('100')
    prior_pct = (cogs_prior / revenue_prior) * Decimal('100')
    increase = current_pct - prior_pct

    if increase <= Decimal('3'):
        return []

    severity = SEVERITY_CRITICAL if increase > Decimal('5') else SEVERITY_WARNING

    return [{
        'flag_type': FOOD_COST_SPIKE,
        'severity': severity,
        'title': f"Food cost spike: {current_pct:.1f}% (was {prior_pct:.1f}%, +{increase:.1f}pp)",
        'detail': (
            f"Food cost percentage increased from {prior_pct:.1f}% ({prior_from} to {prior_to}) "
            f"to {current_pct:.1f}% ({date_from} to {date_to}) — a {increase:.1f} percentage point increase. "
            f"Current: COGS=${cogs_current:,.2f}, Revenue=${revenue_current:,.2f}. "
            f"Prior: COGS=${cogs_prior:,.2f}, Revenue=${revenue_prior:,.2f}."
        ),
        'flagged_value': current_pct,
        'journal_entry_id': None,
        'journal_entry_line_id': None,
        'account_id': None,
        'period_date': date_from,
        'expected_range_low': prior_pct,
        'expected_range_high': prior_pct + Decimal('3'),
    }]
