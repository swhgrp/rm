"""
Compute and store statistical baselines for GL accounts.

Baselines power the statistical outlier and round number anomaly checks.
Rebuilt monthly via scheduler (1st of month at 4 AM).
"""
import logging
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func as sqlfunc, extract
from sqlalchemy.orm import Session

from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.account import Account
from accounting.gl_review.models import GLAccountBaseline

logger = logging.getLogger(__name__)


def compute_baselines(db: Session, area_id: int, lookback_months: int = 12) -> int:
    """
    Compute statistical baselines for all GL accounts with activity for this area.

    Looks at the last `lookback_months` of posted journal entry data, grouped by
    account and calendar month. Upserts results into gl_account_baselines.

    Returns the number of accounts processed.
    """
    # Calculate the lookback start date
    today = date.today()
    lookback_start = date(
        today.year - (lookback_months // 12),
        today.month - (lookback_months % 12) if today.month > (lookback_months % 12) else today.month - (lookback_months % 12) + 12,
        1
    )
    # Simpler: just subtract months
    year = today.year
    month = today.month - lookback_months
    while month <= 0:
        month += 12
        year -= 1
    lookback_start = date(year, month, 1)

    logger.info(f"Computing baselines for area_id={area_id}, lookback from {lookback_start}")

    # Query all posted line activity grouped by account and month
    rows = (
        db.query(
            JournalEntryLine.account_id,
            Account.account_number,
            sqlfunc.date_trunc('month', JournalEntry.entry_date).label('month'),
            sqlfunc.sum(JournalEntryLine.debit_amount + JournalEntryLine.credit_amount).label('activity'),
            sqlfunc.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount).label('net_balance'),
            extract('dow', JournalEntry.entry_date).label('day_of_week'),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .join(Account, JournalEntryLine.account_id == Account.id)
        .filter(
            JournalEntryLine.area_id == area_id,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= lookback_start,
        )
        .group_by(
            JournalEntryLine.account_id,
            Account.account_number,
            sqlfunc.date_trunc('month', JournalEntry.entry_date),
            extract('dow', JournalEntry.entry_date),
        )
        .all()
    )

    # Aggregate by account
    # Structure: account_id -> { account_code, monthly_activity: {month: Decimal}, monthly_balance: {month: Decimal}, posting_days: {dow: set(months)} }
    account_data = defaultdict(lambda: {
        'account_code': None,
        'monthly_activity': defaultdict(Decimal),
        'monthly_balance': defaultdict(Decimal),
        'posting_days': defaultdict(set),
    })

    for row in rows:
        acct = account_data[row.account_id]
        acct['account_code'] = row.account_number
        month_key = str(row.month)
        acct['monthly_activity'][month_key] += Decimal(str(row.activity or 0))
        acct['monthly_balance'][month_key] += Decimal(str(row.net_balance or 0))
        acct['posting_days'][int(row.day_of_week)].add(month_key)

    accounts_processed = 0

    for account_id, data in account_data.items():
        activities = list(data['monthly_activity'].values())
        balances = list(data['monthly_balance'].values())
        num_months = len(activities)

        if num_months < 2:
            # Need at least 2 months for meaningful stddev
            avg_activity = activities[0] if activities else Decimal('0')
            avg_balance = balances[0] if balances else Decimal('0')
            stddev_activity = Decimal('0')
            stddev_balance = Decimal('0')
        else:
            avg_activity = Decimal(str(statistics.mean([float(a) for a in activities])))
            stddev_activity = Decimal(str(statistics.stdev([float(a) for a in activities])))
            avg_balance = Decimal(str(statistics.mean([float(b) for b in balances])))
            stddev_balance = Decimal(str(statistics.stdev([float(b) for b in balances])))

        min_obs = min(activities) if activities else Decimal('0')
        max_obs = max(activities) if activities else Decimal('0')

        # Typical posting days: days of week with postings in >50% of months
        total_months = len(data['monthly_activity'])
        typical_days = []
        if total_months > 0:
            for dow in range(7):
                months_with_dow = len(data['posting_days'].get(dow, set()))
                if months_with_dow / total_months > 0.5:
                    typical_days.append(dow)

        # Upsert baseline
        existing = db.query(GLAccountBaseline).filter(
            GLAccountBaseline.area_id == area_id,
            GLAccountBaseline.account_id == account_id,
        ).first()

        if existing:
            existing.account_code = data['account_code']
            existing.months_of_data = num_months
            existing.avg_monthly_balance = avg_balance
            existing.stddev_monthly_balance = stddev_balance
            existing.avg_monthly_activity = avg_activity
            existing.stddev_monthly_activity = stddev_activity
            existing.min_observed = min_obs
            existing.max_observed = max_obs
            existing.typical_posting_days = typical_days
            existing.last_computed_at = datetime.now(timezone.utc)
        else:
            baseline = GLAccountBaseline(
                area_id=area_id,
                account_id=account_id,
                account_code=data['account_code'],
                months_of_data=num_months,
                avg_monthly_balance=avg_balance,
                stddev_monthly_balance=stddev_balance,
                avg_monthly_activity=avg_activity,
                stddev_monthly_activity=stddev_activity,
                min_observed=min_obs,
                max_observed=max_obs,
                typical_posting_days=typical_days,
                last_computed_at=datetime.now(timezone.utc),
            )
            db.add(baseline)

        accounts_processed += 1

    db.commit()
    logger.info(f"Baselines computed for area_id={area_id}: {accounts_processed} accounts processed")
    return accounts_processed
