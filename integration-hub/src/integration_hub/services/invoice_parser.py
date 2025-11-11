"""
Invoice parsing service using OpenAI Vision API for Integration Hub

This parser extracts invoice data and prepares it for routing to both
Inventory and Accounting systems.
"""

import os
import json
import logging
import base64
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path
from openai import OpenAI
from pdf2image import convert_from_path

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.vendor import Vendor
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class InvoiceParser:
    """Parse invoices using OpenAI GPT-4o Vision"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key or self.api_key == "your-openai-key-here":
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY environment variable")

        self.client = OpenAI(api_key=self.api_key)

    def parse_invoice_pdf(self, pdf_path: str) -> Dict:
        """
        Parse invoice PDF using OpenAI GPT-4o Vision

        Converts PDF to images and uses vision model to extract structured data.

        Returns:
            Dict with structure: {
                "success": bool,
                "data": {...parsed invoice data...},
                "confidence_score": float,
                "message": str
            }
        """
        try:
            # Convert ALL pages of PDF to images
            logger.info(f"Converting PDF to images: {pdf_path}")
            images = convert_from_path(pdf_path, dpi=200)

            if not images:
                return {
                    "success": False,
                    "error": "Failed to convert PDF to image",
                    "message": "PDF conversion failed"
                }

            # Convert all pages to base64 for multi-page support
            from io import BytesIO
            image_data = []
            for i, img in enumerate(images):
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                image_data.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_base64}",
                        "detail": "high"
                    }
                })

            logger.info(f"Converted {len(images)} pages from PDF")

            # Use GPT-4o Vision for image-based parsing
            logger.info("Calling GPT-4o Vision API for invoice parsing")

            # Build user message content with text prompt + all page images
            page_type = "multi-page" if len(images) > 1 else "single-page"
            user_content = [
                {
                    "type": "text",
                    "text": f"Parse this restaurant supply invoice ({page_type} document with {len(images)} page(s)). Extract vendor, location, invoice details, and ALL line items from ALL pages. Make sure to capture the final totals (subtotal, tax, and total amount) which are typically on the last page."
                }
            ]
            user_content.extend(image_data)

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert at parsing restaurant supply invoices, including multi-page invoices.
                        You will receive one or more images representing all pages of an invoice.
                        You must extract structured data from ALL pages.
                        Return ONLY a valid JSON object with this exact structure:
                        {
                            "vendor_name": "string (the supplier/vendor company name)",
                            "vendor_account_number": "string (customer/account number if present)",
                            "location_name": "string (delivery location/restaurant name if present)",
                            "invoice_number": "string",
                            "invoice_date": "YYYY-MM-DD",
                            "due_date": "YYYY-MM-DD (or null if not present)",
                            "subtotal": float,
                            "tax_amount": float,
                            "total_amount": float,
                            "line_items": [
                                {
                                    "line_number": int,
                                    "description": "string",
                                    "item_code": "string (SKU/product code)",
                                    "quantity": float,
                                    "unit": "string (EA, CS, LB, etc)",
                                    "pack_size": "string (e.g. '6x5 LB', 'Case - 12', 'Each')",
                                    "unit_price": float,
                                    "line_total": float
                                }
                            ]
                        }

                        CRITICAL INSTRUCTIONS:
                        - FOR MULTI-PAGE INVOICES: Combine line items from ALL pages into a single list
                        - vendor_name: The company at the TOP of the invoice (letterhead/logo area) who SENT the invoice
                          Example: "Gold Coast Linen Service", "SYSCO", "US Foods"
                          Look for company name near logo, top-left, or "From:" section
                        - location_name: The DELIVERY/SHIP TO location (customer receiving goods)
                          Look for "Ship To:", "Deliver To:", "Location:", or customer name
                          Example: "SW GRILL", "Seaside Grill", "The Nest Eatery"
                        - vendor_account_number: The account/customer number on the invoice
                        - Extract ALL line items from ALL pages of the invoice with precise quantities and prices
                        - The final totals (subtotal, tax_amount, total_amount) are typically on the LAST page
                        - Verify that the sum of all line_total values approximately equals the subtotal
                        - For pack_size, look for packaging info in item description or separate column
                        - If any field is not visible/present, use null
                        - Be extremely precise with numbers (quantities, prices, totals)
                        - Return ONLY valid JSON, no explanations or markdown"""
                    },
                    {
                        "role": "user",
                        "content": user_content
                    }
                ],
                max_tokens=8192,  # Increased for multi-page invoices
                temperature=0.1
            )

            result_text = response.choices[0].message.content

            # Parse JSON from response
            # Extract JSON from markdown code blocks if present
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]

            parsed_data = json.loads(result_text.strip())

            # Calculate confidence score based on how many fields were found
            total_fields = 7  # vendor, invoice_number, invoice_date, due_date, subtotal, tax, total
            found_fields = sum([
                1 for field in ['vendor_name', 'invoice_number', 'invoice_date', 'due_date',
                               'subtotal', 'tax_amount', 'total_amount']
                if parsed_data.get(field) is not None
            ])
            confidence = found_fields / total_fields

            return {
                "success": True,
                "data": parsed_data,
                "confidence_score": confidence,
                "message": "Invoice parsed successfully"
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to parse AI response as JSON: {str(e)}",
                "message": "AI returned invalid response format"
            }
        except Exception as e:
            logger.error(f"Error parsing invoice: {str(e)}")
            error_message = str(e)
            # Check if it's an OpenAI error
            if "openai" in str(type(e)).lower() or "api" in error_message.lower():
                return {
                    "success": False,
                    "error": f"OpenAI API error: {error_message}",
                    "message": "Failed to parse invoice with AI"
                }
            return {
                "success": False,
                "error": error_message,
                "message": "Unexpected error during parsing"
            }

    def match_vendor(self, vendor_name: str, db: Session) -> Optional[Vendor]:
        """
        Match parsed vendor name to existing vendor in database

        Uses multiple strategies:
        1. Exact match (case insensitive)
        2. Partial match - vendor name contains parsed name
        3. Partial match - parsed name contains vendor name
        """
        if not vendor_name:
            return None

        vendor_name = vendor_name.strip()

        # 1. Exact match (case insensitive)
        vendor = db.query(Vendor).filter(
            Vendor.name.ilike(vendor_name)
        ).first()

        if vendor:
            logger.info(f"Exact vendor match: '{vendor_name}' -> '{vendor.name}' (ID: {vendor.id})")
            return vendor

        # 2. Partial match - vendor name contains the parsed name
        vendor = db.query(Vendor).filter(
            Vendor.name.ilike(f"%{vendor_name}%")
        ).first()

        if vendor:
            logger.info(f"Partial vendor match (contains): '{vendor_name}' -> '{vendor.name}' (ID: {vendor.id})")
            return vendor

        # 3. Partial match - parsed name contains vendor name
        all_vendors = db.query(Vendor).filter(Vendor.is_active == True).all()
        for v in all_vendors:
            if v.name.lower() in vendor_name.lower():
                logger.info(f"Partial vendor match (in): '{vendor_name}' -> '{v.name}' (ID: {v.id})")
                return v

        logger.warning(f"No vendor match found for: '{vendor_name}'")
        return None

    def match_location(self, location_name: str) -> Optional[tuple]:
        """
        Match parsed location name to existing location in inventory system

        Queries the inventory database to find matching locations.
        Returns tuple of (location_id, location_name) if found.

        Uses multiple strategies:
        1. Exact match (case insensitive)
        2. Partial match - location name contains parsed name
        3. Partial match - parsed name contains location name
        """
        if not location_name:
            return None

        location_name = location_name.strip()

        # Get inventory database connection string from environment
        import os
        from sqlalchemy import create_engine, text

        inventory_db_url = os.getenv('INVENTORY_DATABASE_URL',
                                     'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db')

        try:
            engine = create_engine(inventory_db_url)
            with engine.connect() as conn:
                # 1. Exact match (case insensitive)
                result = conn.execute(
                    text("SELECT id, name FROM locations WHERE LOWER(name) = LOWER(:name) AND is_active = true LIMIT 1"),
                    {"name": location_name}
                ).fetchone()

                if result:
                    logger.info(f"Exact location match: '{location_name}' -> '{result[1]}' (ID: {result[0]})")
                    return (result[0], result[1])

                # 2. Partial match - location name contains the parsed name
                result = conn.execute(
                    text("SELECT id, name FROM locations WHERE LOWER(name) LIKE LOWER(:pattern) AND is_active = true LIMIT 1"),
                    {"pattern": f"%{location_name}%"}
                ).fetchone()

                if result:
                    logger.info(f"Partial location match (contains): '{location_name}' -> '{result[1]}' (ID: {result[0]})")
                    return (result[0], result[1])

                # 3. Partial match - parsed name contains location name
                all_locations = conn.execute(
                    text("SELECT id, name FROM locations WHERE is_active = true")
                ).fetchall()

                for loc in all_locations:
                    if loc[1].lower() in location_name.lower():
                        logger.info(f"Partial location match (in): '{location_name}' -> '{loc[1]}' (ID: {loc[0]})")
                        return (loc[0], loc[1])

                logger.warning(f"No location match found for: '{location_name}'")
                return None

        except Exception as e:
            logger.error(f"Error matching location '{location_name}': {str(e)}")
            return None

    def parse_and_save(self, invoice_id: int, db: Session) -> Dict:
        """
        Parse an invoice and save the results to database

        Updates the HubInvoice record and creates HubInvoiceItem records
        """
        # Get invoice
        invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        if not invoice:
            return {"success": False, "message": "Invoice not found"}

        if not invoice.pdf_path:
            return {"success": False, "message": "Invoice has no PDF file"}

        # Check if invoice already has items (prevent duplicate parsing)
        existing_items_count = db.query(HubInvoiceItem).filter(HubInvoiceItem.invoice_id == invoice_id).count()
        if existing_items_count > 0:
            logger.warning(f"Invoice {invoice_id} already has {existing_items_count} items. Deleting existing items before re-parsing.")
            # Delete existing items to allow re-parsing
            db.query(HubInvoiceItem).filter(HubInvoiceItem.invoice_id == invoice_id).delete()
            db.commit()

        # Update status to mapping (parsing)
        invoice.status = 'mapping'
        db.commit()

        try:
            # Parse with AI
            parse_result = self.parse_invoice_pdf(invoice.pdf_path)

            if not parse_result["success"]:
                invoice.status = 'pending'
                invoice.raw_data = {"error": parse_result.get("error")}
                db.commit()
                return parse_result

            parsed_data = parse_result["data"]
            confidence_score = parse_result["confidence_score"]

            # Auto-match vendor from vendor_name
            vendor = None
            if parsed_data.get('vendor_name'):
                vendor = self.match_vendor(parsed_data['vendor_name'], db)
                if vendor:
                    invoice.vendor_id = vendor.id

            # Auto-match location from location_name
            location_matched = False
            if parsed_data.get('location_name'):
                location_match = self.match_location(parsed_data['location_name'])
                if location_match:
                    invoice.location_id = location_match[0]
                    invoice.location_name = location_match[1]
                    location_matched = True

            # Update invoice with parsed data
            invoice.vendor_name = parsed_data.get('vendor_name') or 'Unknown Vendor'
            invoice.vendor_account_number = parsed_data.get('vendor_account_number')
            invoice.invoice_number = parsed_data.get('invoice_number')
            invoice.total_amount = parsed_data.get('total_amount')
            invoice.tax_amount = parsed_data.get('tax_amount')
            invoice.raw_data = parsed_data

            # Parse dates
            if parsed_data.get('invoice_date'):
                try:
                    invoice.invoice_date = datetime.strptime(parsed_data['invoice_date'], '%Y-%m-%d').date()
                except Exception as e:
                    logger.warning(f"Failed to parse invoice_date: {e}")

            if parsed_data.get('due_date'):
                try:
                    invoice.due_date = datetime.strptime(parsed_data['due_date'], '%Y-%m-%d').date()
                except Exception as e:
                    logger.warning(f"Failed to parse due_date: {e}")

            # Create invoice items
            unmapped_count = 0
            line_items = parsed_data.get('line_items', [])

            for item_data in line_items:
                invoice_item = HubInvoiceItem(
                    invoice_id=invoice_id,
                    line_number=item_data.get('line_number'),
                    item_description=item_data.get('description') or 'Unknown',
                    item_code=item_data.get('item_code'),
                    quantity=float(item_data.get('quantity') or 0),
                    unit_of_measure=item_data.get('unit'),
                    unit_price=float(item_data.get('unit_price') or 0),
                    total_amount=float(item_data.get('line_total') or 0),
                    is_mapped=False  # Will need manual mapping
                )
                db.add(invoice_item)
                unmapped_count += 1

            # Set invoice status to mapping
            invoice.status = 'mapping'
            db.commit()

            items_count = len(line_items)

            # Auto-map items using intelligent mapping
            mapping_stats = {'mapped_count': 0, 'unmapped_count': unmapped_count}
            try:
                from integration_hub.services.auto_mapper import get_auto_mapper
                mapper = get_auto_mapper(db)
                mapping_stats = mapper.map_invoice_items(invoice_id)
                logger.info(f"Auto-mapping stats for invoice {invoice_id}: {mapping_stats}")
            except Exception as e:
                logger.error(f"Error auto-mapping items for invoice {invoice_id}: {str(e)}")
                # Don't fail the parsing if auto-mapping fails

            return {
                "success": True,
                "message": f"Invoice parsed successfully with {items_count} items. Auto-mapped: {mapping_stats.get('mapped_count', 0)}, Unmapped: {mapping_stats.get('unmapped_count', 0)}.",
                "invoice_id": invoice_id,
                "confidence_score": confidence_score,
                "items_parsed": items_count,
                "items_mapped": mapping_stats.get('mapped_count', 0),
                "items_unmapped": mapping_stats.get('unmapped_count', 0),
                "mapping_methods": mapping_stats.get('methods', {}),
                "vendor_matched": vendor is not None,
                "vendor_name": parsed_data.get('vendor_name'),
                "location_matched": location_matched,
                "location_name": parsed_data.get('location_name')
            }

        except Exception as e:
            logger.error(f"Error in parse_and_save: {str(e)}", exc_info=True)
            invoice.status = 'pending'
            invoice.raw_data = {"error": str(e)}
            db.commit()

            return {
                "success": False,
                "message": f"Error parsing invoice: {str(e)}"
            }


def get_invoice_parser() -> InvoiceParser:
    """Get invoice parser instance"""
    return InvoiceParser()
