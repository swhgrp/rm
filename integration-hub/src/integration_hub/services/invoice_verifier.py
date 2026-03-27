"""
Invoice Verification Service — PDF-to-DB comparison and auto-correction.

Reads the original PDF via Claude Vision, compares extracted data against
DB items, auto-fixes discrepancies, and re-verifies.  Triple-check flow:
  1. Extract items from PDF (Claude Vision API)
  2. Compare against DB → auto-correct mismatches
  3. Re-extract from PDF to confirm corrections match

Designed to run on individual invoices (API trigger) or in batch
(daily review integration).
"""

import base64
import json
import logging
import os
import re
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import anthropic
from pdf2image import convert_from_path
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem

logger = logging.getLogger(__name__)

# ── thresholds ──────────────────────────────────────────────────────
PRICE_TOLERANCE = 0.02       # Allow $0.02 rounding on unit prices
TOTAL_TOLERANCE = 0.05       # Allow $0.05 rounding on line totals
QTY_TOLERANCE = 0.01         # Allow 0.01 rounding on quantities
INVOICE_TOTAL_TOLERANCE = 0.10  # Allow $0.10 on invoice-level total

# Claude model for verification — Sonnet for cost efficiency with strong vision
VERIFY_MODEL = os.getenv("INVOICE_VERIFY_MODEL", "claude-sonnet-4-20250514")


class InvoiceVerifier:
    """Verify parsed invoice data against the original PDF using Claude Vision."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        self.client = anthropic.Anthropic(api_key=self.api_key)

    # ── PDF → image helpers ─────────────────────────────────────────

    def _pdf_to_base64_images(self, pdf_path: str) -> List[dict]:
        """Convert a PDF file to a list of base64-encoded image content blocks for Claude."""
        images = convert_from_path(pdf_path, dpi=200)
        if not images:
            raise ValueError(f"Failed to convert PDF to images: {pdf_path}")

        image_blocks = []
        for img in images:
            buf = BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            image_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": b64,
                },
            })
        return image_blocks

    # ── Vision API call ─────────────────────────────────────────────

    def _extract_items_from_pdf(self, pdf_path: str) -> Dict:
        """
        Send PDF to Claude Vision and get structured item list back.

        Returns dict with:
            items: [{item_code, description, quantity, unit_price, total, uom}]
            invoice_total, subtotal, tax_amount
        """
        image_blocks = self._pdf_to_base64_images(pdf_path)

        system_prompt = """You are an invoice data extraction auditor. Your job is to read
the EXACT data printed on this invoice and return a JSON object.

CRITICAL RULES:
- Read item codes EXACTLY as printed — every digit matters. Do not transpose, skip, or guess digits.
- Read quantities EXACTLY — use the SHIPPED column (not ordered). For catch-weight items, the weight IS the quantity.
- Read unit prices EXACTLY as printed on the invoice.
- Read line totals (extended price) EXACTLY as printed.
- Each line item on the invoice is a SEPARATE item — do NOT combine similar items (e.g., three different sodas are three separate items even if they look similar).
- Include ALL fees, surcharges, delivery charges, fuel charges, deposits as separate items.
- For multi-page invoices, include items from ALL pages.
- Use the FINAL totals from the last page (subtotal, tax, total).

Return ONLY valid JSON (no markdown fences, no explanation):
{
  "items": [
    {
      "item_code": "string or null",
      "description": "string",
      "quantity": number,
      "unit_price": number,
      "total": number,
      "uom": "string or null"
    }
  ],
  "subtotal": number_or_null,
  "tax_amount": number_or_null,
  "invoice_total": number_or_null,
  "invoice_number": "string or null",
  "item_count": number
}"""

        page_type = "multi-page" if len(image_blocks) > 1 else "single-page"
        user_content = [
            {
                "type": "text",
                "text": (
                    f"Read this {page_type} invoice ({len(image_blocks)} page(s)) and extract "
                    f"EVERY line item with exact item codes, quantities, unit prices, and totals. "
                    f"Be precise — this is an audit verification. Read each digit of each item code carefully."
                ),
            }
        ]
        user_content.extend(image_blocks)

        # Retry logic
        result_text = None
        for attempt in range(3):
            try:
                response = self.client.messages.create(
                    model=VERIFY_MODEL,
                    max_tokens=8192,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": user_content},
                    ],
                )
                result_text = response.content[0].text
                if result_text:
                    break
            except Exception as e:
                logger.warning(f"Claude Vision attempt {attempt+1} failed: {e}")
                if attempt == 2:
                    raise
                import time
                time.sleep(2)

        # Parse JSON
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]
        result_text = result_text.strip()

        # Fix math expressions (rare but possible)
        result_text = re.sub(
            r':\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)',
            lambda m: f': {round(float(m.group(1)) / float(m.group(2)), 6)}',
            result_text,
        )

        return json.loads(result_text)

    # ── Comparison logic ────────────────────────────────────────────

    def _normalize_code(self, code: str) -> str:
        """Normalize an item code for comparison: strip, uppercase, remove leading zeros."""
        if not code:
            return ""
        return code.strip().upper().lstrip("0") or "0"

    def _match_items(
        self, pdf_items: List[dict], db_items: List[HubInvoiceItem]
    ) -> List[dict]:
        """
        Match PDF-extracted items to DB items using multiple strategies.

        Returns list of match dicts:
        {
            "pdf_item": {...},
            "db_item": HubInvoiceItem or None,
            "match_method": str,
            "discrepancies": [{"field": str, "pdf_value": ..., "db_value": ...}]
        }
        """
        matches = []
        used_db_ids = set()

        # Build lookup structures for DB items
        db_by_code = {}
        db_by_idx = {}
        for i, item in enumerate(db_items):
            code = self._normalize_code(item.item_code or "")
            if code:
                db_by_code.setdefault(code, []).append(item)
            db_by_idx[i] = item

        for pdf_item in pdf_items:
            pdf_code = self._normalize_code(pdf_item.get("item_code") or "")
            pdf_desc = (pdf_item.get("description") or "").strip().lower()
            pdf_qty = float(pdf_item.get("quantity") or 0)
            pdf_price = float(pdf_item.get("unit_price") or 0)
            pdf_total = float(pdf_item.get("total") or 0)

            best_match = None
            best_method = "unmatched"

            # Strategy 1: exact item code match
            if pdf_code and pdf_code in db_by_code:
                for candidate in db_by_code[pdf_code]:
                    if candidate.id not in used_db_ids:
                        best_match = candidate
                        best_method = "exact_code"
                        break

            # Strategy 2: fuzzy code (off-by-one digit) — only if no exact
            if not best_match and pdf_code:
                for code, candidates in db_by_code.items():
                    if code == pdf_code:
                        continue
                    # Same length, differ by at most 1 character
                    if len(code) == len(pdf_code):
                        diffs = sum(1 for a, b in zip(code, pdf_code) if a != b)
                        if diffs <= 1:
                            for candidate in candidates:
                                if candidate.id not in used_db_ids:
                                    best_match = candidate
                                    best_method = "near_code"
                                    break
                            if best_match:
                                break

            # Strategy 3: description + total match
            if not best_match:
                for item in db_items:
                    if item.id in used_db_ids:
                        continue
                    db_desc = (item.item_description or "").strip().lower()
                    db_total = float(item.total_amount or 0)
                    # Check if descriptions share significant words
                    pdf_words = set(pdf_desc.split())
                    db_words = set(db_desc.split())
                    common = pdf_words & db_words
                    if len(common) >= 2 and abs(db_total - pdf_total) < TOTAL_TOLERANCE:
                        best_match = item
                        best_method = "desc_total"
                        break

            # Strategy 4: total amount match (for fees/charges)
            if not best_match and pdf_total != 0:
                for item in db_items:
                    if item.id in used_db_ids:
                        continue
                    db_total = float(item.total_amount or 0)
                    db_desc = (item.item_description or "").strip().lower()
                    # Check description similarity for fee items
                    if abs(db_total - pdf_total) < TOTAL_TOLERANCE:
                        pdf_words = set(pdf_desc.split())
                        db_words = set(db_desc.split())
                        if pdf_words & db_words:
                            best_match = item
                            best_method = "total_match"
                            break

            # Build discrepancy list
            discrepancies = []
            if best_match:
                used_db_ids.add(best_match.id)

                # Check item code
                db_code = self._normalize_code(best_match.item_code or "")
                if pdf_code and db_code and pdf_code != db_code:
                    discrepancies.append({
                        "field": "item_code",
                        "pdf_value": pdf_item.get("item_code"),
                        "db_value": best_match.item_code,
                    })

                # Check quantity
                db_qty = float(best_match.quantity or 0)
                if abs(pdf_qty - db_qty) > QTY_TOLERANCE:
                    discrepancies.append({
                        "field": "quantity",
                        "pdf_value": pdf_qty,
                        "db_value": db_qty,
                    })

                # Check unit price
                db_price = float(best_match.unit_price or 0)
                if abs(pdf_price - db_price) > PRICE_TOLERANCE:
                    discrepancies.append({
                        "field": "unit_price",
                        "pdf_value": pdf_price,
                        "db_value": db_price,
                    })

                # Check line total
                db_total = float(best_match.total_amount or 0)
                if abs(pdf_total - db_total) > TOTAL_TOLERANCE:
                    discrepancies.append({
                        "field": "total_amount",
                        "pdf_value": pdf_total,
                        "db_value": db_total,
                    })

            matches.append({
                "pdf_item": pdf_item,
                "db_item": best_match,
                "match_method": best_method,
                "discrepancies": discrepancies,
            })

        # Check for unmatched DB items (items in DB that aren't in the PDF)
        for item in db_items:
            if item.id not in used_db_ids:
                matches.append({
                    "pdf_item": None,
                    "db_item": item,
                    "match_method": "db_only",
                    "discrepancies": [{"field": "missing_from_pdf", "pdf_value": None, "db_value": str(item.item_description)}],
                })

        return matches

    # ── Auto-correction ─────────────────────────────────────────────

    def _apply_corrections(
        self, matches: List[dict], invoice: HubInvoice, db: Session
    ) -> List[dict]:
        """
        Apply corrections to DB items based on PDF extraction.

        Returns list of correction dicts describing what was changed.
        """
        corrections = []

        for match in matches:
            pdf_item = match.get("pdf_item")
            db_item = match.get("db_item")
            discrepancies = match.get("discrepancies", [])
            method = match.get("match_method")

            if not discrepancies or not db_item:
                continue

            # Skip DB-only items (items in DB not found in PDF) — needs manual review
            if method == "db_only":
                continue

            for disc in discrepancies:
                field = disc["field"]
                pdf_val = disc["pdf_value"]
                db_val = disc["db_value"]

                if field == "item_code" and pdf_val:
                    # Only correct item_code if matched by near_code (1-digit transposition)
                    # or desc_total (description matched, code was wrong)
                    if method in ("near_code", "desc_total", "total_match"):
                        old_val = db_item.item_code
                        db_item.item_code = str(pdf_val).strip()
                        corrections.append({
                            "item_id": db_item.id,
                            "field": "item_code",
                            "old": old_val,
                            "new": str(pdf_val).strip(),
                            "description": db_item.item_description,
                        })

                elif field == "quantity":
                    old_val = float(db_item.quantity or 0)
                    db_item.quantity = pdf_val
                    # Recalculate total
                    new_total = round(pdf_val * float(db_item.unit_price or 0), 4)
                    db_item.total_amount = new_total
                    corrections.append({
                        "item_id": db_item.id,
                        "field": "quantity",
                        "old": old_val,
                        "new": pdf_val,
                        "description": db_item.item_description,
                    })

                elif field == "unit_price":
                    old_val = float(db_item.unit_price or 0)
                    db_item.unit_price = pdf_val
                    # Recalculate total
                    new_total = round(float(db_item.quantity or 0) * pdf_val, 4)
                    db_item.total_amount = new_total
                    corrections.append({
                        "item_id": db_item.id,
                        "field": "unit_price",
                        "old": old_val,
                        "new": pdf_val,
                        "description": db_item.item_description,
                    })

                elif field == "total_amount":
                    # Only fix total if qty and price weren't already corrected
                    already_fixed = any(
                        c["item_id"] == db_item.id and c["field"] in ("quantity", "unit_price")
                        for c in corrections
                    )
                    if not already_fixed:
                        old_val = float(db_item.total_amount or 0)
                        db_item.total_amount = pdf_val
                        corrections.append({
                            "item_id": db_item.id,
                            "field": "total_amount",
                            "old": old_val,
                            "new": pdf_val,
                            "description": db_item.item_description,
                        })

        # Handle missing items (in PDF but not in DB)
        for match in matches:
            if match["match_method"] == "unmatched" and match["pdf_item"]:
                pdf_item = match["pdf_item"]
                qty = float(pdf_item.get("quantity") or 0)
                price = float(pdf_item.get("unit_price") or 0)
                total = float(pdf_item.get("total") or 0)
                desc = (pdf_item.get("description") or "").strip()

                if not desc or total == 0:
                    continue

                # Create new item
                new_item = HubInvoiceItem(
                    invoice_id=invoice.id,
                    item_code=pdf_item.get("item_code"),
                    item_description=desc,
                    quantity=qty,
                    unit_price=price,
                    total_amount=total if total else round(qty * price, 4),
                    unit_of_measure=pdf_item.get("uom"),
                    is_mapped=False,
                    mapping_method=None,
                )
                db.add(new_item)
                corrections.append({
                    "item_id": None,
                    "field": "new_item",
                    "old": None,
                    "new": f"{desc} (qty={qty}, price=${price:.2f}, total=${total:.2f})",
                    "description": desc,
                })

        if corrections:
            # Update invoice line_items_total
            db.flush()  # Ensure new items have IDs
            items = db.query(HubInvoiceItem).filter(
                HubInvoiceItem.invoice_id == invoice.id
            ).all()
            line_total = sum(float(item.total_amount or 0) for item in items)
            invoice.line_items_total = round(line_total, 2)
            db.commit()

        return corrections

    # ── Re-verification (pass 2) ───────────────────────────────────

    def _re_verify(
        self, pdf_path: str, db_items: List[HubInvoiceItem]
    ) -> Dict:
        """
        Second-pass verification: send PDF again and compare against corrected DB.

        Returns summary of remaining discrepancies (should be zero if corrections worked).
        """
        pdf_data = self._extract_items_from_pdf(pdf_path)
        pdf_items = pdf_data.get("items", [])

        remaining_issues = []
        used_db_ids = set()

        for pdf_item in pdf_items:
            pdf_code = self._normalize_code(pdf_item.get("item_code") or "")
            pdf_total = float(pdf_item.get("total") or 0)
            pdf_price = float(pdf_item.get("unit_price") or 0)
            pdf_qty = float(pdf_item.get("quantity") or 0)

            # Find matching DB item
            matched = None
            for item in db_items:
                if item.id in used_db_ids:
                    continue
                db_code = self._normalize_code(item.item_code or "")
                if pdf_code and db_code and pdf_code == db_code:
                    matched = item
                    break

            if not matched:
                # Try total match
                for item in db_items:
                    if item.id in used_db_ids:
                        continue
                    if abs(float(item.total_amount or 0) - pdf_total) < TOTAL_TOLERANCE:
                        matched = item
                        break

            if matched:
                used_db_ids.add(matched.id)
                # Check key fields
                db_price = float(matched.unit_price or 0)
                db_qty = float(matched.quantity or 0)
                db_total = float(matched.total_amount or 0)

                issues = []
                if abs(pdf_price - db_price) > PRICE_TOLERANCE:
                    issues.append(f"price: PDF=${pdf_price:.2f} vs DB=${db_price:.2f}")
                if abs(pdf_qty - db_qty) > QTY_TOLERANCE:
                    issues.append(f"qty: PDF={pdf_qty} vs DB={db_qty}")
                if abs(pdf_total - db_total) > TOTAL_TOLERANCE:
                    issues.append(f"total: PDF=${pdf_total:.2f} vs DB=${db_total:.2f}")

                if issues:
                    remaining_issues.append({
                        "item": matched.item_description,
                        "item_code": matched.item_code,
                        "issues": issues,
                    })
            else:
                remaining_issues.append({
                    "item": pdf_item.get("description", "unknown"),
                    "item_code": pdf_item.get("item_code"),
                    "issues": ["not found in DB after corrections"],
                })

        return {
            "verified": len(remaining_issues) == 0,
            "remaining_issues": remaining_issues,
            "pdf_item_count": len(pdf_items),
            "db_item_count": len(db_items),
        }

    # ── Main entry point ────────────────────────────────────────────

    def verify_invoice(self, invoice_id: int, db: Session, auto_fix: bool = True) -> Dict:
        """
        Full verification pipeline for a single invoice.

        1. Load invoice + items from DB
        2. Read PDF via Vision API
        3. Compare PDF data to DB items
        4. Auto-correct discrepancies (if auto_fix=True)
        5. Re-verify corrected data against PDF (second Vision call)

        Args:
            invoice_id: Hub invoice ID
            db: Database session
            auto_fix: Whether to auto-correct discrepancies

        Returns:
            Comprehensive verification report dict
        """
        invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        if not invoice:
            return {"success": False, "error": "Invoice not found"}

        pdf_path = invoice.pdf_path
        if not pdf_path:
            return {"success": False, "error": "No PDF path on invoice"}

        # Check PDF exists
        if not os.path.exists(pdf_path):
            return {"success": False, "error": f"PDF file not found: {pdf_path}"}

        logger.info(f"Starting verification for invoice {invoice_id} ({invoice.vendor_name} #{invoice.invoice_number})")

        # Load DB items
        db_items = db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id
        ).order_by(HubInvoiceItem.line_number, HubInvoiceItem.id).all()

        if not db_items:
            return {
                "success": True,
                "invoice_id": invoice_id,
                "message": "No items to verify",
                "corrections": [],
                "verified": True,
            }

        # ── Pass 1: Extract from PDF ────────────────────────────────
        try:
            pdf_data = self._extract_items_from_pdf(pdf_path)
        except Exception as e:
            logger.error(f"Failed to extract data from PDF for invoice {invoice_id}: {e}")
            return {"success": False, "error": f"PDF extraction failed: {str(e)}"}

        pdf_items = pdf_data.get("items", [])
        pdf_total = pdf_data.get("invoice_total")

        logger.info(
            f"Invoice {invoice_id}: PDF has {len(pdf_items)} items, "
            f"DB has {len(db_items)} items"
        )

        # ── Compare ────────────────────────────────────────────────
        matches = self._match_items(pdf_items, db_items)

        total_discrepancies = sum(len(m["discrepancies"]) for m in matches)
        unmatched_pdf = sum(1 for m in matches if m["match_method"] == "unmatched")
        db_only = sum(1 for m in matches if m["match_method"] == "db_only")

        logger.info(
            f"Invoice {invoice_id}: {total_discrepancies} discrepancies, "
            f"{unmatched_pdf} unmatched PDF items, {db_only} DB-only items"
        )

        # Build initial comparison report
        comparison = {
            "pdf_item_count": len(pdf_items),
            "db_item_count": len(db_items),
            "total_discrepancies": total_discrepancies,
            "unmatched_pdf_items": unmatched_pdf,
            "db_only_items": db_only,
            "matches": [
                {
                    "pdf_desc": (m["pdf_item"] or {}).get("description", "N/A"),
                    "db_desc": m["db_item"].item_description if m["db_item"] else "N/A",
                    "method": m["match_method"],
                    "discrepancies": m["discrepancies"],
                }
                for m in matches
            ],
        }

        # Check invoice total
        invoice_total_match = True
        if pdf_total is not None:
            db_total_amt = float(invoice.total_amount or 0)
            if abs(float(pdf_total) - db_total_amt) > INVOICE_TOTAL_TOLERANCE:
                invoice_total_match = False
                comparison["invoice_total_mismatch"] = {
                    "pdf_total": float(pdf_total),
                    "db_total": db_total_amt,
                    "diff": round(float(pdf_total) - db_total_amt, 2),
                }

        # ── Auto-correct ────────────────────────────────────────────
        corrections = []
        if auto_fix and total_discrepancies > 0:
            corrections = self._apply_corrections(matches, invoice, db)
            logger.info(f"Invoice {invoice_id}: Applied {len(corrections)} corrections")

        # ── Pass 2: Re-verify ───────────────────────────────────────
        verification = {"verified": True, "remaining_issues": []}
        if corrections:
            try:
                # Reload items after corrections
                db.expire_all()
                db_items_updated = db.query(HubInvoiceItem).filter(
                    HubInvoiceItem.invoice_id == invoice_id
                ).order_by(HubInvoiceItem.line_number, HubInvoiceItem.id).all()

                verification = self._re_verify(pdf_path, db_items_updated)
                logger.info(
                    f"Invoice {invoice_id}: Re-verification "
                    f"{'PASSED' if verification['verified'] else 'FAILED'} "
                    f"({len(verification.get('remaining_issues', []))} issues remaining)"
                )
            except Exception as e:
                logger.error(f"Re-verification failed for invoice {invoice_id}: {e}")
                verification = {
                    "verified": False,
                    "remaining_issues": [{"item": "re-verification", "issues": [str(e)]}],
                }

        # ── Recalculate status after corrections ────────────────────
        if corrections:
            try:
                from integration_hub.services.post_parse_validator import apply_validation_to_invoice
                apply_validation_to_invoice(invoice_id, db)
            except Exception as e:
                logger.error(f"Post-correction validation failed: {e}")

            try:
                from integration_hub.services.invoice_status import update_invoice_status
                db.refresh(invoice)
                update_invoice_status(invoice, db)
                db.commit()
            except Exception as e:
                logger.error(f"Post-correction status update failed: {e}")

        return {
            "success": True,
            "invoice_id": invoice_id,
            "vendor": invoice.vendor_name,
            "invoice_number": invoice.invoice_number,
            "comparison": comparison,
            "corrections": corrections,
            "corrections_count": len(corrections),
            "verification": verification,
            "invoice_total_match": invoice_total_match,
            "needs_attention": not verification.get("verified", True) or not invoice_total_match,
        }


def verify_invoice(invoice_id: int, db: Session, auto_fix: bool = True) -> Dict:
    """Convenience function — instantiates verifier and runs."""
    verifier = InvoiceVerifier()
    return verifier.verify_invoice(invoice_id, db, auto_fix=auto_fix)


def batch_verify_invoices(
    db: Session,
    status_filter: Optional[str] = None,
    limit: int = 50,
    auto_fix: bool = True,
) -> Dict:
    """
    Verify multiple invoices in batch. Used by daily review.

    Targets invoices that:
    - Have a PDF file
    - Are not statements
    - Have items
    - Optionally filtered by status

    Args:
        db: Database session
        status_filter: e.g. 'needs_review', 'mapping', 'ready'
        limit: Max invoices to process (Vision API calls are expensive)
        auto_fix: Whether to auto-correct

    Returns:
        Summary dict with per-invoice results
    """
    query = db.query(HubInvoice).filter(
        HubInvoice.pdf_path.isnot(None),
        HubInvoice.is_statement == False,
        HubInvoice.status != 'statement',
    )

    if status_filter:
        query = query.filter(HubInvoice.status == status_filter)
    else:
        # Default: focus on needs_review and recently-parsed invoices
        query = query.filter(
            HubInvoice.status.in_(['needs_review', 'mapping', 'ready'])
        )

    # Only invoices that haven't been sent yet
    query = query.filter(
        HubInvoice.sent_to_accounting == False,
        HubInvoice.sent_to_inventory == False,
    )

    # Subquery: only invoices with items
    query = query.filter(
        db.query(HubInvoiceItem.id).filter(
            HubInvoiceItem.invoice_id == HubInvoice.id
        ).exists()
    )

    invoices = query.order_by(HubInvoice.id.desc()).limit(limit).all()

    verifier = InvoiceVerifier()
    results = {
        "total": len(invoices),
        "verified_ok": 0,
        "corrected": 0,
        "needs_attention": 0,
        "errors": 0,
        "details": [],
    }

    for invoice in invoices:
        try:
            result = verifier.verify_invoice(invoice.id, db, auto_fix=auto_fix)
            if not result.get("success"):
                results["errors"] += 1
            elif result.get("corrections_count", 0) > 0:
                results["corrected"] += 1
            elif result.get("needs_attention"):
                results["needs_attention"] += 1
            else:
                results["verified_ok"] += 1

            results["details"].append({
                "invoice_id": invoice.id,
                "vendor": invoice.vendor_name,
                "invoice_number": invoice.invoice_number,
                "success": result.get("success", False),
                "corrections": result.get("corrections_count", 0),
                "verified": result.get("verification", {}).get("verified", False),
                "needs_attention": result.get("needs_attention", False),
            })
        except Exception as e:
            logger.error(f"Verification failed for invoice {invoice.id}: {e}")
            results["errors"] += 1
            results["details"].append({
                "invoice_id": invoice.id,
                "vendor": invoice.vendor_name,
                "invoice_number": invoice.invoice_number,
                "success": False,
                "error": str(e),
            })

    logger.info(
        f"Batch verification complete: {results['total']} invoices — "
        f"{results['verified_ok']} OK, {results['corrected']} corrected, "
        f"{results['needs_attention']} need attention, {results['errors']} errors"
    )

    return results
