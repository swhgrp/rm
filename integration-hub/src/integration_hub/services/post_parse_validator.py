"""
Post-parse validation service for invoice items and totals.

Runs after AI/CSV parsing creates line items, before auto-mapping.
Catches common parsing errors: SKU-as-price, field swaps, missing items,
fee/charge misclassification.
"""
import json
import logging
import re
from typing import Dict, List

from sqlalchemy.orm import Session

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem

logger = logging.getLogger(__name__)

# Thresholds (can be made configurable via system_settings later)
MAX_REASONABLE_UNIT_PRICE = 500.0   # Flag unit prices above this
MAX_REASONABLE_QUANTITY = 999.0     # Flag quantities above this
SKU_AS_PRICE_THRESHOLD = 10000     # Integer price ≥ this with no decimal = likely SKU
TOTAL_MISMATCH_PCT_THRESHOLD = 5.0  # Flag if line items vs invoice total differs by > 5%
TOTAL_MISMATCH_ABS_THRESHOLD = 5.0  # AND differs by > $5 (avoids noise on small invoices)

# Fee/charge keywords — matched case-insensitive against item_description
FEE_PATTERNS = re.compile(
    r'\b(?:DELIVERY|FUEL\s*SURCHARGE|FREIGHT|DEPOSIT|SERVICE\s*CHARGE|'
    r'HANDLING|ENVIRONMENTAL|RECYCLING|SURCHARGE|CORE\s*CHARGE|'
    r'BOTTLE\s*DEPOSIT|CRV|SHIPPING|TRANSPORTATION|DISPOSAL)\b',
    re.IGNORECASE
)


def validate_invoice_items(invoice_id: int, db: Session) -> Dict:
    """
    Run per-item sanity checks on parsed invoice items.

    Checks:
    - Price anomalies (unit_price > threshold or looks like a SKU)
    - Quantity anomalies (quantity > threshold)
    - Field swap detection (item_code looks like price, price looks like SKU)
    - Fee/charge detection (description matches fee keywords)

    Returns:
        {"warnings": [list of warning strings], "flags_set": int, "has_anomalies": bool}
    """
    items = db.query(HubInvoiceItem).filter(
        HubInvoiceItem.invoice_id == invoice_id
    ).all()

    warnings = []
    flags_set = 0
    has_anomalies = False

    for item in items:
        item_flags = []
        price = float(item.unit_price or 0)
        qty = float(item.quantity or 0)
        code = (item.item_code or '').strip()
        desc = (item.item_description or '').strip()

        # 1. Price anomaly: unreasonably high unit price
        if price > MAX_REASONABLE_UNIT_PRICE:
            item_flags.append('price_anomaly')
            warnings.append(
                f"Item '{desc[:40]}': unit_price ${price:,.2f} exceeds ${MAX_REASONABLE_UNIT_PRICE} threshold"
            )

        # 2. Possible SKU stored as price: large integer with no meaningful decimal
        if price >= SKU_AS_PRICE_THRESHOLD and price == int(price) and not code:
            item_flags.append('possible_sku_as_price')
            warnings.append(
                f"Item '{desc[:40]}': unit_price {int(price)} looks like a SKU (integer ≥ {SKU_AS_PRICE_THRESHOLD}, no item_code)"
            )

        # 3. Quantity anomaly: unreasonably high
        if qty > MAX_REASONABLE_QUANTITY:
            item_flags.append('qty_anomaly')
            warnings.append(
                f"Item '{desc[:40]}': quantity {qty:,.0f} exceeds {MAX_REASONABLE_QUANTITY} threshold"
            )

        # 4. Field swap: item_code contains a decimal point (looks like a price)
        if code and re.match(r'^\d+\.\d{2,4}$', code):
            item_flags.append('possible_field_swap')
            warnings.append(
                f"Item '{desc[:40]}': item_code '{code}' looks like a price (contains decimal)"
            )

        # 5. Fee/charge detection
        if desc and FEE_PATTERNS.search(desc):
            item_flags.append('possible_fee')
            warnings.append(
                f"Item '{desc[:40]}': description matches fee/charge pattern"
            )

        # Store flags on item
        if item_flags:
            item.validation_flags = ','.join(item_flags)
            flags_set += 1
            has_anomalies = True

    if flags_set > 0:
        db.commit()
        logger.warning(
            f"Invoice {invoice_id}: {flags_set} items flagged with validation warnings: "
            + '; '.join(warnings[:5])  # Log first 5
        )

    return {
        "warnings": warnings,
        "flags_set": flags_set,
        "has_anomalies": has_anomalies
    }


def validate_invoice_totals(invoice_id: int, db: Session) -> Dict:
    """
    Compare sum of line item totals to invoice total_amount.

    Catches: missing line items, extra fee lines, AI total parsing errors.

    Returns:
        {
            "match": bool,
            "line_items_total": float,
            "invoice_total": float,
            "expected_subtotal": float,
            "mismatch_pct": float,
            "mismatch_abs": float,
            "needs_flag": bool
        }
    """
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        return {"match": True, "needs_flag": False, "line_items_total": 0}

    items = db.query(HubInvoiceItem).filter(
        HubInvoiceItem.invoice_id == invoice_id
    ).all()

    line_items_total = sum(float(item.total_amount or 0) for item in items)
    invoice_total = float(invoice.total_amount or 0)
    tax = float(invoice.tax_amount or 0)

    # Expected subtotal = invoice total minus tax
    expected_subtotal = invoice_total - tax

    if expected_subtotal > 0:
        mismatch_abs = abs(line_items_total - expected_subtotal)
        mismatch_pct = (mismatch_abs / expected_subtotal) * 100
    else:
        mismatch_abs = abs(line_items_total - invoice_total)
        mismatch_pct = 0.0

    # Flag if both percentage AND absolute thresholds exceeded
    needs_flag = (
        mismatch_pct > TOTAL_MISMATCH_PCT_THRESHOLD
        and mismatch_abs > TOTAL_MISMATCH_ABS_THRESHOLD
    )

    if needs_flag:
        logger.warning(
            f"Invoice {invoice_id}: total mismatch — "
            f"line items sum ${line_items_total:,.2f} vs expected subtotal ${expected_subtotal:,.2f} "
            f"(diff ${mismatch_abs:,.2f}, {mismatch_pct:.1f}%)"
        )

    return {
        "match": not needs_flag,
        "line_items_total": round(line_items_total, 2),
        "invoice_total": invoice_total,
        "expected_subtotal": round(expected_subtotal, 2),
        "mismatch_pct": round(mismatch_pct, 1),
        "mismatch_abs": round(mismatch_abs, 2),
        "needs_flag": needs_flag
    }


def apply_validation_to_invoice(invoice_id: int, db: Session) -> Dict:
    """
    Run all post-parse validations and update invoice flags.

    Combines item-level and total-level validation, sets needs_review
    and review_reason on the invoice if any issues found.

    Returns:
        Combined validation results dict
    """
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        return {"success": False, "message": "Invoice not found"}

    # Run item-level checks
    item_result = validate_invoice_items(invoice_id, db)

    # Run total reconciliation
    total_result = validate_invoice_totals(invoice_id, db)

    # Build review reasons
    reasons = []
    if invoice.review_reason:
        try:
            reasons = json.loads(invoice.review_reason)
        except (json.JSONDecodeError, TypeError):
            reasons = []

    needs_review = False

    # Flag for total mismatch
    if total_result['needs_flag']:
        reasons.append(f"total_mismatch:{total_result['mismatch_pct']:.1f}%")
        invoice.line_items_total = total_result['line_items_total']
        needs_review = True

    # Flag if any item has price/quantity anomalies (not just fee detection)
    anomaly_flags = {'price_anomaly', 'possible_sku_as_price', 'qty_anomaly', 'possible_field_swap'}
    if item_result['has_anomalies']:
        # Check if any flags are actual anomalies (not just fee detection)
        items = db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id,
            HubInvoiceItem.validation_flags.isnot(None)
        ).all()
        for item in items:
            flags = set((item.validation_flags or '').split(','))
            if flags & anomaly_flags:
                reasons.append(f"item_anomaly:{item.item_description[:30]}")
                needs_review = True
                break  # One is enough to flag the invoice

    if needs_review:
        invoice.needs_review = True
        invoice.review_reason = json.dumps(reasons)
        db.commit()
        logger.info(f"Invoice {invoice_id} flagged for review: {reasons}")

    return {
        "item_validation": item_result,
        "total_validation": total_result,
        "needs_review": needs_review,
        "review_reasons": reasons
    }
