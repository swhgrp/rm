"""
Invoice parsing service using OpenAI Vision API
"""

import os
import base64
import json
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from PIL import Image
import PyPDF2
import io

from restaurant_inventory.models import Invoice, InvoiceItem, MasterItem, InvoiceStatus, VendorItem, UnitOfMeasure
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_


class InvoiceParser:
    """Parse invoices using OpenAI Vision API"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key or self.api_key == "your-openai-key-here":
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in .env file")

        self.client = OpenAI(api_key=self.api_key)

    def encode_image(self, image_path: str) -> str:
        """Encode image to base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def pdf_to_images(self, pdf_path: str) -> List[str]:
        """Convert PDF pages to images (returns paths to temp images)"""
        # For now, just return the PDF path - OpenAI can handle PDFs directly
        # In production, you might want to convert to images for better results
        return [pdf_path]

    def parse_invoice_with_ai(self, file_path: str, file_type: str) -> Dict:
        """Parse invoice using OpenAI Vision API"""

        try:
            # Prepare the image/file
            if file_type == 'pdf':
                # For PDFs, we'll extract text and send it
                # In production, consider using pdf2image to convert to images
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text_content = ""
                    for page in pdf_reader.pages:
                        text_content += page.extract_text()

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
                                "vendor_name": "string (the supplier/vendor company name - look at the top of invoice, sender info, or letterhead)",
                                "delivery_location": "string (the delivery/ship-to address or location name - NOT the vendor address, but WHERE the items were delivered to)",
                                "invoice_number": "string",
                                "invoice_date": "YYYY-MM-DD",
                                "due_date": "YYYY-MM-DD",
                                "subtotal": float,
                                "tax": float,
                                "total": float,
                                "line_items": [
                                    {
                                        "line_number": int,
                                        "description": "string",
                                        "vendor_sku": "string",
                                        "quantity": float,
                                        "unit": "string",
                                        "pack_size": "string (exact pack configuration from invoice, e.g. '6x5 LB', '12x750ml', '4x1 GAL', '5x2 LB' - preserve the exact format shown)",
                                        "unit_price": float,
                                        "line_total": float
                                    }
                                ]
                            }

                            CRITICAL INSTRUCTIONS:
                            - vendor_name: Extract the SUPPLIER company name (who sent the invoice), typically at the top
                            - delivery_location: Extract the CUSTOMER/SHIP-TO location (where items were delivered), look for "Ship To:", "Deliver To:", or customer address
                            - For pack_size, extract packaging information like:
                              * "Case - 6" if the item comes in a case of 6
                              * "Case - 24" if it's a case of 24
                              * "Each" if sold individually
                              * "Dozen" if sold by the dozen
                              Look for pack information in the description, unit field, or anywhere on the line item.

                            If any field is not found, use null. Be precise with numbers."""
                        },
                        {
                            "role": "user",
                            "content": f"Parse this invoice:\n\n{text_content}"
                        }
                    ],
                    temperature=0.1
                )

                result_text = response.choices[0].message.content

            else:
                # For images, use Vision API
                base64_image = self.encode_image(file_path)

                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": """Parse this restaurant supply invoice image and extract structured data.
                                    Return a JSON object with:
                                    {
                                        "vendor_name": "string (the supplier/vendor company name - look at the top of invoice, sender info, or letterhead)",
                                        "delivery_location": "string (the delivery/ship-to address or location name - NOT the vendor address, but WHERE the items were delivered to)",
                                        "invoice_number": "string",
                                        "invoice_date": "YYYY-MM-DD",
                                        "due_date": "YYYY-MM-DD",
                                        "subtotal": float,
                                        "tax": float,
                                        "total": float,
                                        "line_items": [
                                            {
                                                "line_number": int,
                                                "description": "string",
                                                "vendor_sku": "string",
                                                "quantity": float,
                                                "unit": "string",
                                                "pack_size": "string (exact pack configuration from invoice, e.g. '6x5 LB', '12x750ml', '4x1 GAL', '5x2 LB' - preserve the exact format shown)",
                                                "unit_price": float,
                                                "line_total": float
                                            }
                                        ]
                                    }

                                    CRITICAL INSTRUCTIONS:
                                    - vendor_name: Extract the SUPPLIER company name (who sent the invoice), typically at the top
                                    - delivery_location: Extract the CUSTOMER/SHIP-TO location (where items were delivered), look for "Ship To:", "Deliver To:", or customer address
                                    - For pack_size, extract the EXACT pack configuration as shown on the invoice:
                                      * If you see "6x5 LB", extract "6x5 LB" (NOT "Case - 6")
                                      * If you see "12x750ml", extract "12x750ml"
                                      * If you see "4x1 GAL", extract "4x1 GAL"
                                      * Preserve the exact format including numbers, 'x', and units
                                      * Look for this in a separate column, in the description, or unit field
                                      * Do NOT make up a generic format - use what's actually printed on the invoice

                                    If any field is not visible, use null. Be precise with numbers."""
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=4096,
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
            total_fields = 7  # vendor, invoice_number, dates, totals
            found_fields = sum([
                1 for field in ['vendor_name', 'invoice_number', 'invoice_date', 'due_date', 'subtotal', 'tax', 'total']
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
            return {
                "success": False,
                "error": f"Failed to parse AI response as JSON: {str(e)}",
                "message": "AI returned invalid response format"
            }
        except Exception as e:
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

    def match_pack_size_to_uom(self, pack_size: str, db: Session) -> Optional[int]:
        """
        Match invoice pack size to a Unit of Measure.
        Examples:
        - "6x5 LB" -> "Case - 6x5lb"
        - "12x750ml" -> "Case - 12x750ml"
        - "5x2 LB" -> "Case - 5x2lb"
        """
        if not pack_size:
            return None

        # Normalize pack size for matching
        normalized_pack = pack_size.strip().lower()
        normalized_pack = normalized_pack.replace(' ', '')  # Remove spaces

        # Get all active units
        units = db.query(UnitOfMeasure).filter(UnitOfMeasure.is_active == True).all()

        # Try exact match first
        for unit in units:
            unit_name_normalized = unit.name.lower().replace(' ', '').replace('-', '')
            unit_abbr_normalized = unit.abbreviation.lower().replace(' ', '').replace('-', '')

            # Check if pack_size matches name or abbreviation
            if normalized_pack in unit_name_normalized or unit_name_normalized in normalized_pack:
                return unit.id
            if normalized_pack in unit_abbr_normalized or unit_abbr_normalized in normalized_pack:
                return unit.id

            # Try matching patterns like "6x5lb" in "Case - 6x5lb"
            if 'x' in normalized_pack:  # Pack pattern like "6x5lb"
                if normalized_pack in unit_name_normalized:
                    return unit.id

        return None

    def match_vendor_items(self, line_items: List[Dict], vendor_id: int, db: Session) -> List[Dict]:
        """Match invoice line items to vendor items with priority matching"""
        matched_items = []

        if not vendor_id:
            # No vendor, can't match vendor items
            return [{"vendor_item_id": None, "match_method": None, "match_confidence": None, **item} for item in line_items]

        # Get all active vendor items for this vendor - load once
        vendor_items = db.query(VendorItem).filter(
            and_(
                VendorItem.vendor_id == vendor_id,
                VendorItem.is_active == True
            )
        ).all()

        # Build lookup dictionaries for fast matching
        sku_lookup = {}
        name_lookup = {}
        name_pack_lookup = {}

        for vi in vendor_items:
            # SKU lookup
            if vi.vendor_sku:
                sku_lookup[vi.vendor_sku.strip().lower()] = vi

            # Name lookup
            if vi.vendor_product_name:
                name_key = vi.vendor_product_name.strip().lower()
                name_lookup[name_key] = vi

                # Name + pack lookup
                if vi.pack_size:
                    pack_key = f"{name_key}|{vi.pack_size.strip().lower()}"
                    name_pack_lookup[pack_key] = vi

        for line_item in line_items:
            description = (line_item.get('description', '') or '').strip().lower()
            vendor_sku = (line_item.get('vendor_sku', '') or '').strip().lower()
            pack_size = (line_item.get('pack_size', '') or '').strip().lower()

            best_match = None
            best_score = 0.0
            match_method = None

            # Priority 1: Exact vendor_sku match (fastest)
            if vendor_sku and vendor_sku in sku_lookup:
                best_match = sku_lookup[vendor_sku]
                best_score = 1.0
                match_method = 'vendor_sku'

            # Priority 2: Exact product name match
            elif description and description in name_lookup:
                best_match = name_lookup[description]
                best_score = 0.95
                match_method = 'exact_name'

            # Priority 3: Product name + pack size match
            elif description and pack_size:
                pack_key = f"{description}|{pack_size}"
                if pack_key in name_pack_lookup:
                    best_match = name_pack_lookup[pack_key]
                    best_score = 0.98
                    match_method = 'name_and_pack'

            # Priority 4: Fuzzy description match (only if exact matches fail)
            if not best_match and description and len(description) >= 5:
                for vi in vendor_items:
                    vi_name = (vi.vendor_product_name or '').strip().lower()

                    if len(vi_name) >= 5:
                        if description in vi_name:
                            score = 0.85 * (len(description) / len(vi_name))
                            if score > best_score and score >= 0.7:
                                best_match = vi
                                best_score = score
                                match_method = 'fuzzy_desc_in_name'
                        elif vi_name in description:
                            score = 0.85 * (len(vi_name) / len(description))
                            if score > best_score and score >= 0.7:
                                best_match = vi
                                best_score = score
                                match_method = 'fuzzy_name_in_desc'

            # Calculate price variance if we have a match
            price_variance_pct = None
            is_price_anomaly = False
            if best_match and best_match.unit_price and line_item.get('unit_price'):
                price_variance_pct = ((line_item['unit_price'] - float(best_match.unit_price)) / float(best_match.unit_price)) * 100
                # Flag if variance > 20%
                if abs(price_variance_pct) > 20:
                    is_price_anomaly = True

            # Try to match pack size to UOM
            pack_size_uom_id = None
            if pack_size:
                pack_size_uom_id = self.match_pack_size_to_uom(line_item.get('pack_size', ''), db)

            matched_items.append({
                **line_item,
                'vendor_item_id': best_match.id if best_match else None,
                'master_item_id': best_match.master_item_id if best_match else None,
                'match_method': match_method,
                'match_confidence': best_score if best_match else None,
                'last_price': float(best_match.unit_price) if best_match and best_match.unit_price else None,
                'price_variance_pct': price_variance_pct,
                'is_price_anomaly': is_price_anomaly,
                'pack_size_uom_id': pack_size_uom_id  # Matched UOM for pack size
            })

        return matched_items

    def auto_map_items(self, line_items: List[Dict], db: Session) -> List[Dict]:
        """Automatically map invoice line items to master items"""
        mapped_items = []

        # Get all master items for fuzzy matching
        master_items = db.query(MasterItem).filter(MasterItem.is_active == True).all()

        for line_item in line_items:
            description = line_item.get('description', '').lower()
            vendor_sku = line_item.get('vendor_sku', '').lower()

            best_match = None
            best_score = 0.0

            # Simple fuzzy matching logic
            for master_item in master_items:
                item_name = master_item.name.lower()
                score = 0.0

                # Exact name match
                if description == item_name:
                    score = 1.0
                # Name contains description or vice versa
                elif description in item_name or item_name in description:
                    score = 0.8
                # Check vendor SKU if available
                elif vendor_sku and hasattr(master_item, 'vendor_sku') and vendor_sku == str(master_item.vendor_sku).lower():
                    score = 0.9

                if score > best_score:
                    best_score = score
                    best_match = master_item

            # Only auto-map if confidence is high enough
            line_item['master_item_id'] = best_match.id if best_score >= 0.7 else None
            line_item['mapping_confidence'] = best_score if best_match else None
            line_item['mapping_method'] = 'auto' if best_match else None

            # Check for price anomalies if we have a match
            if best_match and best_match.cost:
                price_diff_pct = ((line_item['unit_price'] - best_match.cost) / best_match.cost) * 100
                line_item['last_price'] = best_match.cost
                line_item['price_change_pct'] = price_diff_pct

                # Flag anomalies
                if abs(price_diff_pct) > 20:
                    line_item['is_anomaly'] = 'price_spike' if price_diff_pct > 0 else 'price_drop'
            elif not best_match:
                line_item['is_anomaly'] = 'new_item'

            mapped_items.append(line_item)

        return mapped_items

    def parse_and_save(self, invoice_id: int, db: Session) -> Dict:
        """Parse an invoice and save the results"""

        # Get invoice
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            return {"success": False, "message": "Invoice not found"}

        # Update status to parsing
        invoice.status = InvoiceStatus.PARSING
        db.commit()

        try:
            # Parse with AI
            parse_result = self.parse_invoice_with_ai(invoice.file_path, invoice.file_type)

            if not parse_result["success"]:
                invoice.status = InvoiceStatus.UPLOADED
                invoice.parsed_data = {"error": parse_result.get("error")}
                db.commit()
                return parse_result

            parsed_data = parse_result["data"]
            confidence_score = parse_result["confidence_score"]

            # Auto-map vendor from vendor_name if not already set
            if not invoice.vendor_id and parsed_data.get('vendor_name'):
                from restaurant_inventory.models import Vendor
                vendor_name = parsed_data.get('vendor_name').strip()

                # Try multiple matching strategies
                vendor = None

                # 1. Exact match (case insensitive)
                vendor = db.query(Vendor).filter(
                    Vendor.name.ilike(vendor_name)
                ).first()

                # 2. Partial match - vendor name contains the parsed name
                if not vendor:
                    vendor = db.query(Vendor).filter(
                        Vendor.name.ilike(f"%{vendor_name}%")
                    ).first()

                # 3. Partial match - parsed name contains vendor name
                if not vendor:
                    all_vendors = db.query(Vendor).all()
                    for v in all_vendors:
                        if v.name.lower() in vendor_name.lower():
                            vendor = v
                            break

                if vendor:
                    invoice.vendor_id = vendor.id
                    print(f"Matched vendor: '{vendor_name}' -> '{vendor.name}' (ID: {vendor.id})")
                else:
                    print(f"No vendor match found for: '{vendor_name}'")

            # Auto-map location from delivery_location if not already set
            if not invoice.location_id and parsed_data.get('delivery_location'):
                from restaurant_inventory.models import Location
                location_text = parsed_data.get('delivery_location').strip()

                # Try multiple matching strategies
                location = None

                # 1. Exact name match (case insensitive)
                location = db.query(Location).filter(
                    Location.name.ilike(location_text)
                ).first()

                # 2. Partial name match
                if not location:
                    location = db.query(Location).filter(
                        Location.name.ilike(f"%{location_text}%")
                    ).first()

                # 3. Address match
                if not location:
                    location = db.query(Location).filter(
                        Location.address.ilike(f"%{location_text}%")
                    ).first()

                # 4. Check if location name appears in the delivery text
                if not location:
                    all_locations = db.query(Location).all()
                    for loc in all_locations:
                        if loc.name.lower() in location_text.lower():
                            location = loc
                            break

                if location:
                    invoice.location_id = location.id
                    print(f"Matched location: '{location_text}' -> '{location.name}' (ID: {location.id})")
                else:
                    print(f"No location match found for: '{location_text}'")

            # Auto-match line items to vendor items
            unmapped_count = 0
            matched_items = []
            if "line_items" in parsed_data:
                # Use vendor item matching if we have a vendor
                if invoice.vendor_id:
                    matched_items = self.match_vendor_items(parsed_data["line_items"], invoice.vendor_id, db)
                else:
                    # Fallback to old master item matching
                    matched_items = self.auto_map_items(parsed_data["line_items"], db)

                # Create invoice items
                for item_data in matched_items:
                    invoice_item = InvoiceItem(
                        invoice_id=invoice_id,
                        line_number=item_data.get('line_number'),
                        description=item_data.get('description') or 'Unknown',
                        vendor_sku=item_data.get('vendor_sku'),
                        quantity=float(item_data.get('quantity') or 0),
                        unit=item_data.get('unit'),
                        pack_size=item_data.get('pack_size'),
                        unit_price=float(item_data.get('unit_price') or 0),
                        line_total=float(item_data.get('line_total') or 0),
                        vendor_item_id=item_data.get('vendor_item_id'),
                        master_item_id=item_data.get('master_item_id'),
                        unit_of_measure_id=item_data.get('pack_size_uom_id'),  # Matched UOM for pack size
                        mapping_confidence=item_data.get('match_confidence') or item_data.get('mapping_confidence'),
                        mapping_method=item_data.get('match_method') or item_data.get('mapping_method'),
                        last_price=item_data.get('last_price'),
                        price_change_pct=item_data.get('price_variance_pct') or item_data.get('price_change_pct'),
                        is_anomaly='price_spike' if item_data.get('is_price_anomaly') else item_data.get('is_anomaly')
                    )
                    db.add(invoice_item)

                    # Count unmapped items (vendor_item_id OR unit_of_measure_id missing)
                    if not item_data.get('vendor_item_id') or not item_data.get('pack_size_uom_id'):
                        unmapped_count += 1

            # Update invoice with parsed data
            # Set status to NEEDS_MAPPING if there are unmapped items
            if unmapped_count > 0:
                invoice.status = InvoiceStatus.NEEDS_MAPPING
            else:
                invoice.status = InvoiceStatus.PARSED

            invoice.parsed_data = parsed_data
            invoice.confidence_score = confidence_score
            invoice.invoice_number = parsed_data.get('invoice_number')
            invoice.subtotal = parsed_data.get('subtotal')
            invoice.tax = parsed_data.get('tax')
            invoice.total = parsed_data.get('total')

            # Parse dates
            if parsed_data.get('invoice_date'):
                try:
                    invoice.invoice_date = datetime.strptime(parsed_data['invoice_date'], '%Y-%m-%d')
                except:
                    pass
            if parsed_data.get('due_date'):
                try:
                    invoice.due_date = datetime.strptime(parsed_data['due_date'], '%Y-%m-%d')
                except:
                    pass

            # Detect anomalies
            anomalies = []
            items_with_anomalies = db.query(InvoiceItem).filter(
                InvoiceItem.invoice_id == invoice_id,
                InvoiceItem.is_anomaly.isnot(None)
            ).all()

            for item in items_with_anomalies:
                anomalies.append({
                    "item_id": item.id,
                    "description": item.description,
                    "type": item.is_anomaly,
                    "message": f"{item.description}: {item.is_anomaly}"
                })

            if anomalies:
                invoice.anomalies = anomalies

            db.commit()

            items_count = len(parsed_data.get('line_items', []))
            items_mapped = sum([1 for item in mapped_items if item.get('master_item_id')])

            return {
                "success": True,
                "message": "Invoice parsed successfully" if unmapped_count == 0 else f"Invoice parsed with {unmapped_count} unmapped item(s)",
                "invoice_id": invoice_id,
                "confidence_score": confidence_score,
                "items_parsed": items_count,
                "items_mapped": items_mapped,
                "items_unmapped": unmapped_count,
                "needs_mapping": unmapped_count > 0,
                "anomalies": anomalies
            }

        except Exception as e:
            invoice.status = InvoiceStatus.UPLOADED
            invoice.parsed_data = {"error": str(e)}
            db.commit()

            return {
                "success": False,
                "message": f"Error parsing invoice: {str(e)}"
            }
