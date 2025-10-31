"""
Invoice parsing service using OpenAI Vision API for Integration Hub

This parser extracts invoice data and prepares it for routing to both
Inventory and Accounting systems.
"""

import os
import json
import logging
from typing import Dict, Optional
from datetime import datetime
from openai import OpenAI
import PyPDF2

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.vendor import Vendor
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class InvoiceParser:
    """Parse invoices using OpenAI GPT-4o-mini"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key or self.api_key == "your-openai-key-here":
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY environment variable")

        self.client = OpenAI(api_key=self.api_key)

    def parse_invoice_pdf(self, pdf_path: str) -> Dict:
        """
        Parse invoice PDF using OpenAI GPT-4o-mini

        Returns:
            Dict with structure: {
                "success": bool,
                "data": {...parsed invoice data...},
                "confidence_score": float,
                "message": str
            }
        """
        try:
            # Extract text from PDF
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text_content = ""
                for page in pdf_reader.pages:
                    text_content += page.extract_text()

            if not text_content.strip():
                return {
                    "success": False,
                    "error": "No text could be extracted from PDF",
                    "message": "PDF appears to be empty or image-based"
                }

            # Use GPT-4o-mini for text-based parsing
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert at parsing restaurant supply invoices.
                        Extract structured data from the invoice text provided.
                        Return a JSON object with the following structure:
                        {
                            "vendor_name": "string (the supplier/vendor company name)",
                            "vendor_account_number": "string (customer/account number if present)",
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
                        - vendor_name: Extract the SUPPLIER/VENDOR company name (who issued the invoice)
                        - vendor_account_number: The customer account number on the invoice
                        - For pack_size, extract packaging information like:
                          * "Case - 6" if the item comes in a case of 6
                          * "6x5 LB" if it's 6 packs of 5 pounds each
                          * "Each" if sold individually
                          * "Dozen" if sold by the dozen
                        - If any field is not found, use null
                        - Be precise with numbers and dates"""
                    },
                    {
                        "role": "user",
                        "content": f"Parse this invoice:\n\n{text_content}"
                    }
                ],
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
                "vendor_name": parsed_data.get('vendor_name')
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
