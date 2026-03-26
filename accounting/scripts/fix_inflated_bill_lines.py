"""
Fix inflated vendor bill lines and their journal entries.

The Hub's old accounting sender sent invoice.total_amount for every GL line
instead of the per-account grouped amounts. This script:
1. Gets correct per-GL-account amounts from Hub database
2. Deletes wrong bill lines and JE lines
3. Creates correct ones

Also handles credit memos with no lines.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from decimal import Decimal
from sqlalchemy import create_engine, text
from datetime import datetime

# Connect to both databases
ACCOUNTING_DB_URL = os.getenv("DATABASE_URL", "postgresql://accounting_user:Acc0unt1ng_Pr0d_2024!@accounting-db:5432/accounting_db")
HUB_DB_URL = os.getenv("HUB_DATABASE_URL", "postgresql://hub_user:hub_password@hub-db:5432/integration_hub_db")

acct_engine = create_engine(ACCOUNTING_DB_URL)
hub_engine = create_engine(HUB_DB_URL)

AP_ACCOUNT_ID = 17  # 2100 Accounts Payable


def get_hub_invoice_gl_lines(hub_id):
    """Get correct per-GL-account amounts from Hub."""
    with hub_engine.connect() as conn:
        # Get invoice details
        inv = conn.execute(text("""
            SELECT id, invoice_number, vendor_name, total_amount, tax_amount
            FROM hub_invoices WHERE id = :id
        """), {"id": hub_id}).fetchone()
        if not inv:
            return None, []

        # Get per-GL-account totals (including unmapped items)
        rows = conn.execute(text("""
            SELECT gl_cogs_account,
                   SUM(total_amount) as account_total,
                   STRING_AGG(LEFT(item_description, 40), ', ' ORDER BY id) as descriptions
            FROM hub_invoice_items
            WHERE invoice_id = :id
              AND gl_cogs_account IS NOT NULL
            GROUP BY gl_cogs_account
            ORDER BY gl_cogs_account
        """), {"id": hub_id}).fetchall()

        return inv, rows


def get_account_id(acct_conn, account_number):
    """Look up accounting DB account ID from account number."""
    row = acct_conn.execute(text(
        "SELECT id FROM accounts WHERE account_number = :num"
    ), {"num": str(account_number)}).fetchone()
    return row[0] if row else None


def fix_bill(acct_conn, bill_id, journal_entry_id, hub_id, dry_run=False):
    """Fix a single bill's lines and JE lines."""
    inv, gl_lines = get_hub_invoice_gl_lines(hub_id)
    if not inv:
        print(f"  SKIP: Hub invoice {hub_id} not found")
        return False

    invoice_total = Decimal(str(inv[3]))
    invoice_tax = Decimal(str(inv[4] or 0))

    if not gl_lines:
        if invoice_total < 0:
            # Credit memo — need to create a single line
            print(f"  Credit memo ${invoice_total} — will create single line")
        else:
            print(f"  SKIP: No GL lines in Hub for invoice {hub_id}")
            return False

    # Calculate correct line amounts with proportional tax
    items_total = sum(Decimal(str(row[1])) for row in gl_lines)
    tax_already_in_items = abs(items_total - invoice_total) < Decimal('0.02')

    correct_lines = []
    running_total = Decimal('0.00')

    for i, row in enumerate(gl_lines):
        account_number = str(row[0])
        account_total = Decimal(str(row[1]))
        descriptions = row[2] or ""

        # Add proportional tax if needed
        if not tax_already_in_items and items_total != 0 and invoice_tax != 0:
            line_tax = (account_total / items_total) * invoice_tax
            line_amount = account_total + line_tax
        else:
            line_amount = account_total

        # Get account DB ID
        account_id = get_account_id(acct_conn, account_number)
        if not account_id:
            print(f"  WARNING: Account {account_number} not found, skipping line")
            continue

        # Truncate descriptions
        desc_parts = descriptions.split(', ')[:3]
        desc = ', '.join(desc_parts)
        if len(descriptions.split(', ')) > 3:
            desc += f" (+{len(descriptions.split(', ')) - 3} more)"

        correct_lines.append({
            "account_id": account_id,
            "amount": line_amount,
            "description": desc,
            "account_number": account_number
        })
        running_total += line_amount

    # Handle credit memos with no lines
    if not correct_lines and invoice_total < 0:
        # For credit memos, we need to find the most likely expense account
        # Use the vendor's most common account from other bills
        row = acct_conn.execute(text("""
            SELECT vbl.account_id, a.account_number, a.account_name, COUNT(*) as cnt
            FROM vendor_bill_lines vbl
            JOIN accounts a ON a.id = vbl.account_id
            JOIN vendor_bills vb ON vb.id = vbl.bill_id
            WHERE vb.vendor_name = :vendor AND vbl.account_id != :ap_id AND vbl.amount > 0
            GROUP BY vbl.account_id, a.account_number, a.account_name
            ORDER BY cnt DESC LIMIT 1
        """), {"vendor": inv[2], "ap_id": AP_ACCOUNT_ID}).fetchone()

        if row:
            correct_lines.append({
                "account_id": row[0],
                "amount": invoice_total,  # Negative = credit
                "description": f"Credit memo: {inv[1]}",
                "account_number": row[1]
            })
            running_total = invoice_total
        else:
            print(f"  SKIP: Can't determine account for credit memo")
            return False

    if not correct_lines:
        print(f"  SKIP: No valid lines to create")
        return False

    # Show what we'll do
    print(f"  Invoice total: ${invoice_total}, Lines total: ${running_total}")
    for line in correct_lines:
        print(f"    GL {line['account_number']}: ${line['amount']:.2f} - {line['description'][:60]}")

    if dry_run:
        return True

    # Get bill's area_id
    bill_row = acct_conn.execute(text(
        "SELECT area_id FROM vendor_bills WHERE id = :id"
    ), {"id": bill_id}).fetchone()
    area_id = bill_row[0] if bill_row else None

    # Delete existing bill lines
    acct_conn.execute(text("DELETE FROM vendor_bill_lines WHERE bill_id = :id"), {"id": bill_id})

    # Create correct bill lines
    for idx, line in enumerate(correct_lines, 1):
        acct_conn.execute(text("""
            INSERT INTO vendor_bill_lines (bill_id, account_id, area_id, description, amount,
                                           is_taxable, tax_amount, line_number)
            VALUES (:bill_id, :account_id, :area_id, :description, :amount, false, 0.00, :line_number)
        """), {
            "bill_id": bill_id,
            "account_id": line["account_id"],
            "area_id": area_id,
            "description": line["description"],
            "amount": float(line["amount"]),
            "line_number": idx
        })

    # Fix JE lines if journal_entry_id exists
    if journal_entry_id:
        # Delete existing expense lines (keep AP credit)
        acct_conn.execute(text("""
            DELETE FROM journal_entry_lines
            WHERE journal_entry_id = :je_id AND account_id != :ap_id
        """), {"je_id": journal_entry_id, "ap_id": AP_ACCOUNT_ID})

        # Update AP credit line to correct total
        acct_conn.execute(text("""
            UPDATE journal_entry_lines
            SET credit_amount = :total, debit_amount = 0
            WHERE journal_entry_id = :je_id AND account_id = :ap_id
        """), {"je_id": journal_entry_id, "total": float(abs(invoice_total)), "ap_id": AP_ACCOUNT_ID})

        # Create correct expense lines
        for idx, line in enumerate(correct_lines, 1):
            amount = line["amount"]
            if amount >= 0:
                debit = float(amount)
                credit = 0.0
            else:
                debit = 0.0
                credit = float(abs(amount))

            acct_conn.execute(text("""
                INSERT INTO journal_entry_lines (journal_entry_id, account_id, area_id,
                    debit_amount, credit_amount, description, line_number)
                VALUES (:je_id, :account_id, :area_id, :debit, :credit, :description, :line_number)
            """), {
                "je_id": journal_entry_id,
                "account_id": line["account_id"],
                "area_id": area_id,
                "description": line["description"],
                "debit": debit,
                "credit": credit,
                "line_number": idx
            })

        # Re-add AP line at end (we need to handle credit memos — AP is debited)
        # Delete old AP line and recreate
        acct_conn.execute(text("""
            DELETE FROM journal_entry_lines
            WHERE journal_entry_id = :je_id AND account_id = :ap_id
        """), {"je_id": journal_entry_id, "ap_id": AP_ACCOUNT_ID})

        if invoice_total >= 0:
            ap_debit = 0.0
            ap_credit = float(invoice_total)
        else:
            ap_debit = float(abs(invoice_total))
            ap_credit = 0.0

        acct_conn.execute(text("""
            INSERT INTO journal_entry_lines (journal_entry_id, account_id, area_id,
                debit_amount, credit_amount, description, line_number)
            VALUES (:je_id, :ap_id, :area_id, :debit, :credit, :description, :line_number)
        """), {
            "je_id": journal_entry_id,
            "ap_id": AP_ACCOUNT_ID,
            "area_id": area_id,
            "debit": ap_debit,
            "credit": ap_credit,
            "description": f"AP: {inv[2]} - {inv[1]}",
            "line_number": len(correct_lines) + 1
        })

    return True


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no changes will be made\n")

    with acct_engine.begin() as acct_conn:
        # Get all mismatched bills
        rows = acct_conn.execute(text("""
            WITH mismatches AS (
                SELECT vb.id as bill_id, vb.bill_number, vb.vendor_name, vb.total_amount,
                       COALESCE(SUM(vbl.amount), 0) as lines_total,
                       vb.reference_number, vb.journal_entry_id
                FROM vendor_bills vb
                LEFT JOIN vendor_bill_lines vbl ON vbl.bill_id = vb.id
                WHERE vb.status != 'VOID'
                GROUP BY vb.id
                HAVING ABS(vb.total_amount - COALESCE(SUM(vbl.amount), 0)) > 0.10
            )
            SELECT * FROM mismatches
            WHERE reference_number LIKE 'HUB-%'
            ORDER BY vendor_name, bill_number
        """)).fetchall()

        print(f"Found {len(rows)} mismatched bills to fix\n")

        stats = {"fixed": 0, "skipped": 0, "errors": 0}

        for row in rows:
            bill_id, bill_number, vendor_name, total_amount, lines_total, ref_number, je_id = row
            hub_id = int(ref_number.replace("HUB-", ""))
            diff = float(total_amount - lines_total)

            print(f"Bill {bill_id} ({vendor_name} - {bill_number}): total=${total_amount}, lines=${lines_total}, diff=${diff:.2f}")

            try:
                success = fix_bill(acct_conn, bill_id, je_id, hub_id, dry_run)
                if success:
                    stats["fixed"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                print(f"  ERROR: {e}")
                stats["errors"] += 1

            print()

        print("=" * 50)
        print(f"Fixed: {stats['fixed']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
