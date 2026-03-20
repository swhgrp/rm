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
from integration_hub.models.hub_vendor_item import HubVendorItem

logger = logging.getLogger(__name__)

# Thresholds (can be made configurable via system_settings later)
MAX_REASONABLE_UNIT_PRICE = 500.0   # Flag unit prices above this
MAX_REASONABLE_QUANTITY = 999.0     # Flag quantities above this
SKU_AS_PRICE_THRESHOLD = 10000     # Integer price ≥ this with no decimal = likely SKU
TOTAL_MISMATCH_PCT_THRESHOLD = 5.0  # Flag if line items vs invoice total differs by > 5%
TOTAL_MISMATCH_ABS_THRESHOLD = 5.0  # AND differs by > $5 (avoids noise on small invoices)
MIN_VENDOR_CATALOG_SIZE = 10       # Skip catalog check if vendor has fewer known items
DESC_MISMATCH_THRESHOLD = 0.3     # Jaccard similarity below this = description mismatch

# Fee/charge keywords — matched case-insensitive against item_description
FEE_PATTERNS = re.compile(
    r'\b(?:DELIVERY|FUEL\s*SURCHARGE|FREIGHT|DEPOSIT|SERVICE\s*CHARGE|'
    r'HANDLING|ENVIRONMENTAL|RECYCLING|SURCHARGE|CORE\s*CHARGE|'
    r'BOTTLE\s*DEPOSIT|CRV|SHIPPING|TRANSPORTATION|DISPOSAL|'
    r'EMPTY\s*KEG|KEG\s*DEPOSIT|KEG\s*RETURN|POS\s*EMPTY)\b',
    re.IGNORECASE
)

# Tax keywords — line items matching these are excluded from subtotal comparison
# when tax_amount is already set (prevents double-counting)
TAX_PATTERNS = re.compile(
    r'\b(?:SALES\s*TAX|STATE\s*TAX|COUNTY\s*TAX|CITY\s*TAX|LOCAL\s*TAX|'
    r'EXCISE\s*TAX|EXC\s*TAX|USE\s*TAX|VAT|HST|GST|PST)\b',
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

        # 6. Possible wrong UOM: multi-unit pack with suspiciously low price
        #    e.g., $4.65 for a "case" of 10x5 LB (50 lbs) = $0.09/lb — likely a BAG, not a case
        #    AI sometimes misreads Unit column (BAG→CS, BAG→BX, etc.)
        pack = int(item.pack_size or 0)
        uom = (item.unit_of_measure or '').upper()
        if uom in ('CS', 'BX', 'PK') and pack >= 5 and price > 0 and price < 10.0:
            item_flags.append('possible_wrong_uom')
            warnings.append(
                f"Item '{desc[:40]}': unit_price ${price:.2f} seems low for {uom} with pack_size {pack} — check Unit column (may be BAG or EA)"
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

    invoice_total = float(invoice.total_amount or 0)
    tax = float(invoice.tax_amount or 0)

    # When tax_amount is set, exclude tax line items from sum to avoid double-counting
    # (AI sometimes puts taxes both as line items AND in the tax_amount field)
    tax_line_total = 0.0
    if tax > 0:
        for item in items:
            desc = (item.item_description or '').strip()
            if desc and TAX_PATTERNS.search(desc):
                tax_line_total += float(item.total_amount or 0)

    line_items_total = sum(float(item.total_amount or 0) for item in items) - tax_line_total

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


def _normalize_sku(code: str) -> str:
    """Normalize a SKU for comparison: strip whitespace and leading zeros."""
    return code.strip().lstrip('0') or '0'


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    stop_words = {'the', 'a', 'an', 'and', 'or', 'of', 'for', 'in', 'with', 'to'}
    words_a = {w.lower() for w in re.split(r'[\s,/\-]+', text_a) if w and w.lower() not in stop_words}
    words_b = {w.lower() for w in re.split(r'[\s,/\-]+', text_b) if w and w.lower() not in stop_words}
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def validate_item_codes_against_catalog(invoice_id: int, db: Session) -> Dict:
    """
    Cross-reference parsed item codes against the vendor's known item catalog.

    Catches AI misreads where the parser captures a valid-looking item code that
    doesn't belong to that vendor, or where the code exists but the description
    doesn't match (e.g., code for Medium eggs but description says XL eggs).

    Returns:
        {"warnings": [...], "flags_set": int}
    """
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice or not invoice.vendor_id:
        return {"warnings": [], "flags_set": 0}

    # Build vendor catalog: normalized_sku -> product_name
    vendor_items = db.query(
        HubVendorItem.vendor_sku, HubVendorItem.vendor_product_name
    ).filter(
        HubVendorItem.vendor_id == invoice.vendor_id,
        HubVendorItem.status != 'inactive'
    ).all()

    if len(vendor_items) < MIN_VENDOR_CATALOG_SIZE:
        return {"warnings": [], "flags_set": 0}

    catalog = {}
    for sku, name in vendor_items:
        if sku:
            catalog[_normalize_sku(sku)] = name or ''

    # Check each parsed item
    items = db.query(HubInvoiceItem).filter(
        HubInvoiceItem.invoice_id == invoice_id
    ).all()

    warnings = []
    flags_set = 0

    for item in items:
        code = (item.item_code or '').strip()
        if not code:
            continue

        normalized_code = _normalize_sku(code)
        desc = (item.item_description or '').strip()
        existing_flags = [f for f in (item.validation_flags or '').split(',') if f]

        if normalized_code not in catalog:
            # Skip flagging for fee/deposit/surcharge items — they won't be in vendor catalog
            if not (desc and FEE_PATTERNS.search(desc)):
                existing_flags.append('unknown_item_code')
                warnings.append(
                    f"Item '{desc[:40]}': code '{code}' not found in vendor catalog "
                    f"({len(catalog)} known items)"
                )
                flags_set += 1
        else:
            # Code exists — check if description matches
            catalog_name = catalog[normalized_code]
            if catalog_name and desc:
                similarity = _jaccard_similarity(desc, catalog_name)
                if similarity < DESC_MISMATCH_THRESHOLD:
                    existing_flags.append('item_code_desc_mismatch')
                    warnings.append(
                        f"Item '{desc[:40]}': code '{code}' maps to '{catalog_name[:40]}' "
                        f"in catalog (similarity {similarity:.0%})"
                    )
                    flags_set += 1

        item.validation_flags = ','.join(existing_flags) if existing_flags else None

    if flags_set > 0:
        db.commit()
        logger.warning(
            f"Invoice {invoice_id}: {flags_set} items flagged by catalog check: "
            + '; '.join(warnings[:5])
        )

    return {"warnings": warnings, "flags_set": flags_set}


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

    # Run item code catalog check
    catalog_result = validate_item_codes_against_catalog(invoice_id, db)

    # Build review reasons — start fresh (don't carry over old reasons from prior parse)
    reasons = []
    needs_review = False

    # Flag for total mismatch
    if total_result['needs_flag']:
        reasons.append(f"total_mismatch:{total_result['mismatch_pct']:.1f}%")
        invoice.line_items_total = total_result['line_items_total']
        needs_review = True

    # Flag if any item has price/quantity anomalies or unknown catalog codes
    # Note: item_code_desc_mismatch is informational only (abbreviation differences cause false positives)
    anomaly_flags = {
        'price_anomaly', 'possible_sku_as_price', 'qty_anomaly', 'possible_field_swap',
        'unknown_item_code', 'possible_wrong_uom'
    }
    if item_result['has_anomalies'] or catalog_result.get('flags_set', 0) > 0:
        # Check if any flags are actual anomalies (not just fee detection)
        items = db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id,
            HubInvoiceItem.validation_flags.isnot(None)
        ).all()
        for item in items:
            flags = set((item.validation_flags or '').split(','))
            # unknown_item_code on a mapped item is not an anomaly — it just means
            # the item is an expense or new product not in the vendor catalog
            effective_flags = flags & anomaly_flags
            if item.is_mapped and 'unknown_item_code' in effective_flags:
                effective_flags.discard('unknown_item_code')
            if effective_flags:
                flag_name = next(iter(effective_flags))
                reasons.append(f"item_anomaly:{flag_name}:{item.item_description[:30]}")
                needs_review = True
                break  # One is enough to flag the invoice

    invoice.needs_review = needs_review
    invoice.review_reason = json.dumps(reasons) if reasons else None
    invoice.line_items_total = total_result.get('line_items_total', invoice.line_items_total)

    if needs_review:
        invoice.status = 'needs_review'
        logger.info(f"Invoice {invoice_id} flagged for review: {reasons}")
    else:
        # If status was needs_review but flags are now cleared, recalculate status
        if invoice.status == 'needs_review':
            invoice.status = 'mapping'  # Reset so update_invoice_status can recalculate
            logger.info(f"Invoice {invoice_id} passed validation — cleared review flags, recalculating status")
            try:
                from integration_hub.services.invoice_status import update_invoice_status
                update_invoice_status(invoice, db)
            except Exception as e:
                logger.error(f"Error recalculating status after clearing review: {e}")
        else:
            logger.info(f"Invoice {invoice_id} passed validation — cleared review flags")

    db.commit()

    return {
        "item_validation": item_result,
        "total_validation": total_result,
        "catalog_validation": catalog_result,
        "needs_review": needs_review,
        "review_reasons": reasons
    }
