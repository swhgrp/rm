"""
CSV Invoice Parser for Fintech Beer/Alcohol Invoices

Parses CSV files from fintech (ftx_admin@fintech.com) containing beer and alcohol
invoice data. Groups line items by invoice number and maps to locations by
Retailer Store Number.
"""

import csv
import hashlib
import logging
from io import StringIO
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem

logger = logging.getLogger(__name__)


class CSVInvoiceParser:
    """Parse fintech CSV invoice files"""

    # Map Retailer Store Number to location codes
    # Location codes are stored in inventory.locations.code

    def __init__(self, db: Session):
        self.db = db
        self._location_cache: Dict[str, Tuple[int, str]] = {}
        self._name_cache: Dict[str, Tuple[int, str]] = {}
        self._load_location_mappings()

    def _load_location_mappings(self):
        """Load location code -> (id, name) mappings from inventory database"""
        try:
            from integration_hub.db.database import get_inventory_engine
            engine = get_inventory_engine()
            with engine.connect() as conn:
                result = conn.execute(sql_text(
                    "SELECT id, code, name FROM locations WHERE is_active = true"
                ))
                for row in result:
                    if row[1]:  # code
                        self._location_cache[str(row[1])] = (row[0], row[2])
                    # Also index by lowercase name for fuzzy fallback
                    if row[2]:
                        self._name_cache[row[2].lower().strip()] = (row[0], row[2])
            logger.info(f"Loaded {len(self._location_cache)} location mappings")
        except Exception as e:
            logger.warning(f"Could not load locations from inventory DB: {e}")
            self._location_cache = {
                '400': (1, 'Seaside Grill'),
                '300': (2, 'The Nest Eatery'),
                '500': (3, 'SW Grill'),
                '200': (4, 'Okee Grill'),
                '700': (5, 'Park Bistro'),
                '600': (6, 'Links Grill'),
            }
            self._name_cache = {v[1].lower(): v for v in self._location_cache.values()}

    def get_location_by_store_number(self, store_number: str, location_name: str = None) -> Optional[Tuple[int, str]]:
        """
        Get location ID and name from store number, with name fallback.

        Args:
            store_number: Store code from CSV (e.g., "500")
            location_name: Location name from CSV for fuzzy fallback

        Returns:
            Tuple of (location_id, location_name) or None if not found
        """
        store_number = str(store_number).strip()
        if store_number:
            result = self._location_cache.get(store_number)
            if result:
                return result

        # Fallback: match by location name (handles GFS store invoices with no store code)
        if location_name:
            name_lower = location_name.lower().strip()
            # Exact name match
            if name_lower in self._name_cache:
                return self._name_cache[name_lower]
            # Substring: check if any known name is contained in the CSV name or vice versa
            for known_name, loc_info in self._name_cache.items():
                if known_name in name_lower or name_lower in known_name:
                    return loc_info
            # Fuzzy: match first word (e.g., "Parks Binstro" -> "Park Bistro")
            first_word = name_lower.split()[0] if name_lower.split() else ''
            if len(first_word) >= 3:
                for known_name, loc_info in self._name_cache.items():
                    known_first = known_name.split()[0] if known_name.split() else ''
                    if first_word[:3] == known_first[:3]:
                        return loc_info

        return None

    def parse_csv_file(self, file_path: str) -> Dict:
        """
        Parse a fintech CSV file and return grouped invoice data.

        Args:
            file_path: Path to the CSV file

        Returns:
            Dict with structure:
            {
                'success': bool,
                'message': str,
                'invoices': [
                    {
                        'invoice_number': str,
                        'vendor_name': str,
                        'invoice_date': date,
                        'due_date': date,
                        'total_amount': Decimal,
                        'location_id': int,
                        'location_name': str,
                        'store_number': str,
                        'items': [
                            {
                                'product_number': str,
                                'description': str,
                                'quantity': Decimal,
                                'unit_price': Decimal,
                                'total': Decimal,
                                'unit_of_measure': str,
                                'pack_size': int,
                                'upc': str,
                            }
                        ]
                    }
                ]
            }
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.parse_csv_content(content)
        except Exception as e:
            logger.error(f"Error reading CSV file {file_path}: {e}")
            return {
                'success': False,
                'message': f"Error reading file: {str(e)}",
                'invoices': []
            }

    def _detect_csv_format(self, fieldnames: List[str]) -> str:
        """
        Detect CSV format from column headers.

        Returns:
            'gfs' for Gordon Food Service CSV
            'fintech' for fintech beer/alcohol CSV
            'statement' for summary/statement CSV
            'unknown' if unrecognized
        """
        field_set = set(fieldnames)

        # Statement/summary CSVs (camelCase columns, no line items)
        statement_columns = {'VendorName', 'InvoiceNumber', 'InvoiceAmount'}
        if statement_columns.issubset(field_set) and 'Product Number' not in field_set:
            return 'statement'

        # GFS CSV: has "Source Warehouse", "Item Number", "Item Description"
        if 'Source Warehouse' in field_set and 'Item Number' in field_set:
            return 'gfs'

        # Fintech beer CSV: has "Product Number", "Vendor Name", "Retailer Store Number"
        if 'Product Number' in field_set or 'Retailer Store Number' in field_set:
            return 'fintech'

        return 'unknown'

    def _normalize_gfs_row(self, row: Dict) -> Dict:
        """
        Map GFS CSV columns to the standard fintech column names so
        the rest of the parsing pipeline works unchanged.
        """
        # Quantity: use Quantity Shipped; for catch-weight items use CW Weight as qty
        qty_shipped = row.get('Quantity Shipped', '0') or '0'
        is_catch_weight = (row.get('Catch Weight', '') or '').upper() == 'Y'
        cw_weight = row.get('CW Weight', '0') or '0'

        if is_catch_weight and cw_weight and float(cw_weight) > 0:
            quantity = cw_weight
        else:
            quantity = qty_shipped

        # Case Price is per-case price; Extended Price is line total
        case_price = row.get('Case Price', '0') or '0'
        extended_price = row.get('Extended Price', '0') or '0'

        # Calculate unit price: extended / qty to get actual price paid per unit
        try:
            qty_val = Decimal(quantity)
            ext_val = Decimal(extended_price)
            unit_price = str(ext_val / qty_val) if qty_val else case_price
        except Exception:
            unit_price = case_price

        return {
            'Invoice Number': row.get('Invoice Number', ''),
            'Invoice Date': row.get('Invoice Date', ''),
            'Invoice DueDate': '',
            'Retailer Store Number': row.get('Store Location', ''),
            'Vendor Name': 'Gordon Food Service',
            'Retailer Name': row.get('Location Name', ''),
            'Product Number': row.get('Item Number', ''),
            'Product Description': row.get('Item Description', ''),
            'Quantity': quantity,
            'Invoice Line Item Cost': unit_price,
            'Extended Price': extended_price,
            'Unit Of Measure': row.get('Case Size', '') or 'CA',
            'Packs Per Case': row.get('Package Size', ''),
            '_gfs_content_uom': row.get('UOM', ''),
            'Units Per Pack': '',
            'Case UPC': row.get('UPC', ''),
            'Clean UPC': '',
            'Product Class': row.get('Category Description', ''),
            'GL Code': row.get('GL Code', ''),
            'Product Volume': '',
            # Preserve GFS-specific fields for reference
            '_gfs_supplier': row.get('Supplier', ''),
            '_gfs_brand': row.get('Brand', ''),
            '_gfs_sub_category': row.get('Sub Category Description', ''),
            '_gfs_catch_weight': is_catch_weight,
            '_gfs_cw_weight': cw_weight,
            '_gfs_case_price': case_price,
            '_gfs_qty_ordered': row.get('Quantity Ordered', ''),
        }

    def parse_csv_content(self, content: str) -> Dict:
        """
        Parse CSV content string and group by invoice number.

        Supports multiple CSV formats:
        - Fintech beer/alcohol CSVs (from ftx_admin@fintech.com)
        - Gordon Food Service delivery CSVs

        Args:
            content: CSV file content as string

        Returns:
            Parsed invoice data dict
        """
        try:
            reader = csv.DictReader(StringIO(content))
            fieldnames = reader.fieldnames or []

            csv_format = self._detect_csv_format(fieldnames)
            logger.info(f"Detected CSV format: {csv_format} (columns: {fieldnames[:6]}...)")

            if csv_format == 'statement':
                return {
                    'success': True,
                    'message': 'CSV is a statement/summary file (no line-item detail)',
                    'invoices': [],
                    'is_statement': True
                }

            # Group rows by invoice number + store number (same invoice can span multiple stores)
            invoice_groups: Dict[str, Dict] = {}

            for row in reader:
                # Normalize GFS rows to standard column names
                if csv_format == 'gfs':
                    row = self._normalize_gfs_row(row)

                invoice_num = row.get('Invoice Number', '').strip()
                store_num = row.get('Retailer Store Number', '').strip()

                if not invoice_num:
                    continue

                # Create unique key for invoice + location combination
                group_key = f"{invoice_num}_{store_num}"

                if group_key not in invoice_groups:
                    # Parse dates
                    invoice_date = self._parse_date(row.get('Invoice Date', ''))
                    due_date = self._parse_date(row.get('Invoice DueDate', ''))

                    # Get location mapping (with name fallback for GFS store invoices)
                    retailer_name = row.get('Retailer Name', '').strip()
                    location_info = self.get_location_by_store_number(store_num, retailer_name)
                    location_id = location_info[0] if location_info else None
                    location_name = location_info[1] if location_info else None

                    invoice_groups[group_key] = {
                        'invoice_number': invoice_num,
                        'vendor_name': row.get('Vendor Name', '').strip(),
                        'invoice_date': invoice_date,
                        'due_date': due_date,
                        'total_amount': Decimal('0'),
                        'location_id': location_id,
                        'location_name': location_name,
                        'store_number': store_num,
                        'retailer_name': row.get('Retailer Name', '').strip(),
                        'csv_format': csv_format,
                        'items': []
                    }

                # Parse line item
                item = self._parse_line_item(row)
                if item:
                    # Deduplicate — GFS CSVs sometimes contain exact duplicate rows
                    dedup_key = (
                        item['product_number'],
                        str(item['quantity']),
                        str(item['unit_price']),
                        str(item['total']),
                    )
                    seen_items = invoice_groups[group_key].setdefault('_seen', set())
                    if dedup_key in seen_items:
                        logger.debug(f"Skipping duplicate CSV row: {item['product_number']} "
                                    f"qty={item['quantity']} price={item['unit_price']}")
                        continue
                    seen_items.add(dedup_key)
                    invoice_groups[group_key]['items'].append(item)
                    invoice_groups[group_key]['total_amount'] += item['total']

            invoices = list(invoice_groups.values())
            # Clean up internal tracking sets
            for inv in invoices:
                inv.pop('_seen', None)

            return {
                'success': True,
                'message': f"Parsed {len(invoices)} invoice(s) with {sum(len(inv['items']) for inv in invoices)} line items ({csv_format} format)",
                'invoices': invoices
            }

        except Exception as e:
            logger.error(f"Error parsing CSV content: {e}")
            return {
                'success': False,
                'message': f"Parse error: {str(e)}",
                'invoices': []
            }

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string in MM/DD/YYYY format"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str.strip(), '%m/%d/%Y')
        except ValueError:
            try:
                return datetime.strptime(date_str.strip(), '%Y-%m-%d')
            except ValueError:
                logger.warning(f"Could not parse date: {date_str}")
                return None

    def _parse_line_item(self, row: Dict) -> Optional[Dict]:
        """Parse a single line item from CSV row"""
        try:
            quantity = Decimal(row.get('Quantity', '0') or '0')
            unit_price = Decimal(row.get('Invoice Line Item Cost', '0') or '0')
            extended_price = Decimal(row.get('Extended Price', '0') or '0')

            # Use extended price if available, otherwise calculate
            total = extended_price if extended_price else (quantity * unit_price)

            # Parse pack size
            packs_per_case = row.get('Packs Per Case', '')
            units_per_pack = row.get('Units Per Pack', '')
            pack_size = None
            if packs_per_case and units_per_pack:
                try:
                    pack_size = int(packs_per_case) * int(units_per_pack)
                except (ValueError, TypeError):
                    pass
            elif packs_per_case:
                try:
                    pack_size = int(packs_per_case)
                except (ValueError, TypeError):
                    pass

            return {
                'product_number': row.get('Product Number', '').strip(),
                'description': row.get('Product Description', '').strip(),
                'quantity': quantity,
                'unit_price': unit_price,
                'total': total,
                'unit_of_measure': row.get('Unit Of Measure', 'CA').strip(),
                'pack_size': pack_size,
                'upc': row.get('Case UPC', '').strip() or row.get('Clean UPC', '').strip(),
                'product_class': row.get('Product Class', '').strip(),
                'gl_code': row.get('GL Code', '').strip(),
                'product_volume': row.get('Product Volume', '').strip(),
            }
        except Exception as e:
            logger.warning(f"Error parsing line item: {e}")
            return None

    def process_hub_invoice(self, hub_invoice_id: int) -> Dict:
        """
        Process a HubInvoice record that has a CSV file attached.

        Parses the CSV, creates/updates invoice records grouped by invoice number,
        and creates line items.

        Args:
            hub_invoice_id: ID of the HubInvoice record with status 'pending_csv'

        Returns:
            Dict with success status and details
        """
        try:
            # Get the hub invoice record
            hub_invoice = self.db.query(HubInvoice).filter(
                HubInvoice.id == hub_invoice_id
            ).first()

            if not hub_invoice:
                return {'success': False, 'message': f'Invoice {hub_invoice_id} not found'}

            if not hub_invoice.pdf_path:
                return {'success': False, 'message': 'No file path set on invoice'}

            file_path = Path(hub_invoice.pdf_path)
            if not file_path.exists():
                return {'success': False, 'message': f'File not found: {hub_invoice.pdf_path}'}

            # Parse the CSV
            result = self.parse_csv_file(str(file_path))

            if not result['success']:
                hub_invoice.status = 'parse_failed'
                hub_invoice.parse_error = result['message']
                self.db.commit()
                return result

            if not result['invoices']:
                if result.get('is_statement'):
                    hub_invoice.is_statement = True
                    hub_invoice.status = 'statement'
                    hub_invoice.parse_error = None
                    self.db.commit()
                    logger.info(f"CSV invoice {hub_invoice_id} marked as statement")
                    return {'success': True, 'message': 'CSV is a statement file', 'is_statement': True}
                hub_invoice.status = 'parse_failed'
                hub_invoice.parse_error = 'No invoices found in CSV'
                self.db.commit()
                return {'success': False, 'message': 'No invoices found in CSV'}

            created_invoices = []

            # If single invoice in CSV, update the existing hub_invoice
            # If multiple invoices, find existing or create new records
            for i, inv_data in enumerate(result['invoices']):
                if i == 0:
                    # Check if a PDF-parsed invoice already exists for this invoice number
                    # If so, update that one and mark the CSV record as duplicate
                    # CSV data is authoritative — replaces PDF regardless of status
                    inv_num_stripped = inv_data['invoice_number'].lstrip('0') or '0'
                    pdf_sibling = None
                    if inv_data.get('location_id'):
                        for ps in self.db.query(HubInvoice).filter(
                            HubInvoice.id != hub_invoice.id,
                            HubInvoice.location_id == inv_data['location_id'],
                            HubInvoice.source_filename.ilike('%.pdf'),
                            HubInvoice.status.notin_(['duplicate']),
                        ).all():
                            ps_num = (ps.invoice_number or '').lstrip('0') or '0'
                            if ps_num == inv_num_stripped:
                                pdf_sibling = ps
                                break
                    if pdf_sibling:
                        # Replace PDF-parsed invoice with CSV data, mark CSV record as duplicate
                        invoice = pdf_sibling
                        hub_invoice.status = 'duplicate'
                        logger.info(f"CSV invoice {hub_invoice.id}: found PDF sibling {pdf_sibling.id} "
                                   f"(#{pdf_sibling.invoice_number}) — replacing PDF data with CSV")
                    else:
                        # Update the original hub_invoice
                        invoice = hub_invoice
                else:
                    # Check if invoice with same number + location already exists
                    # Also try leading-zero-stripped match for PDF-parsed invoices
                    inv_num_stripped = inv_data['invoice_number'].lstrip('0') or '0'
                    existing = None

                    # First: exact match on invoice number + location
                    exact = self.db.query(HubInvoice).filter(
                        HubInvoice.invoice_number == inv_data['invoice_number'],
                        HubInvoice.location_id == inv_data['location_id'],
                        HubInvoice.id != hub_invoice.id,
                        HubInvoice.status != 'duplicate'
                    ).first()

                    if exact:
                        existing = exact
                    else:
                        # Stripped-zero match across all sources
                        candidates = self.db.query(HubInvoice).filter(
                            HubInvoice.id != hub_invoice.id,
                            HubInvoice.location_id == inv_data['location_id'],
                            HubInvoice.status.notin_(['duplicate']),
                        ).all()
                        for ps in candidates:
                            ps_num = (ps.invoice_number or '').lstrip('0') or '0'
                            if ps_num == inv_num_stripped:
                                existing = ps
                                break

                    if existing:
                        # Update existing invoice — CSV data replaces PDF
                        invoice = existing
                        logger.info(f"Found existing invoice {existing.id} (#{existing.invoice_number}) for "
                                   f"{inv_data['invoice_number']} at location {inv_data['location_id']} — replacing with CSV data")
                    else:
                        pdf_match = None  # No match found
                        if pdf_match:
                            # Replace PDF-parsed invoice with CSV data
                            invoice = pdf_match
                            logger.info(f"Found PDF-parsed sibling {pdf_match.id} (#{pdf_match.invoice_number}) "
                                       f"for CSV invoice {inv_data['invoice_number']} — replacing with CSV data")
                        else:
                            # Create new HubInvoice for additional invoices in the CSV
                            invoice = HubInvoice(
                                source='email',
                                source_filename=hub_invoice.source_filename,
                                pdf_path=hub_invoice.pdf_path,
                                email_subject=hub_invoice.email_subject,
                                email_from=hub_invoice.email_from,
                                email_received_at=hub_invoice.email_received_at,
                                # Generate unique hash for child invoice (must fit varchar(64))
                                invoice_hash=hashlib.sha256(
                                    f"{hub_invoice.invoice_hash}_{inv_data['invoice_number']}_{inv_data['store_number']}".encode()
                                ).hexdigest()
                            )
                            self.db.add(invoice)

                # If replacing an existing invoice, reset sync status
                has_sync = invoice.inventory_sync_at or invoice.accounting_sync_at or invoice.status == 'sent'
                if has_sync:
                    logger.info(f"Invoice {invoice.id} was previously synced — resetting sync for CSV replacement")
                    invoice.inventory_sent = False
                    invoice.accounting_sent = False
                    invoice.inventory_error = None
                    invoice.accounting_error = None
                    invoice.inventory_sync_at = None
                    invoice.accounting_sync_at = None

                # Clear review flags
                invoice.needs_review = False
                invoice.review_reason = None

                # Update invoice fields
                invoice.vendor_name = inv_data['vendor_name']
                invoice.invoice_number = inv_data['invoice_number']
                invoice.invoice_date = inv_data['invoice_date']
                invoice.due_date = inv_data['due_date']
                invoice.total_amount = inv_data['total_amount']
                invoice.location_id = inv_data['location_id']
                invoice.location_name = inv_data['location_name']
                invoice.status = 'mapping'  # Ready for item mapping
                invoice.parse_error = None
                invoice.source = 'csv'  # Mark source as CSV

                # Match vendor name to existing vendor record
                if not invoice.vendor_id and inv_data['vendor_name']:
                    try:
                        from integration_hub.services.invoice_parser import InvoiceParser
                        parser = InvoiceParser()
                        vendor = parser.match_vendor(inv_data['vendor_name'], self.db)
                        if vendor:
                            invoice.vendor_id = vendor.id
                            logger.info(f"Matched CSV vendor '{inv_data['vendor_name']}' to vendor {vendor.id} ({vendor.name})")
                    except Exception as e:
                        logger.warning(f"Vendor matching failed for '{inv_data['vendor_name']}': {e}")

                # Store raw data for reference (include CSV file path for viewer)
                invoice.raw_data = {
                    'source': 'fintech_csv',
                    'store_number': inv_data['store_number'],
                    'retailer_name': inv_data['retailer_name'],
                    'item_count': len(inv_data['items']),
                    'csv_file_path': str(hub_invoice.pdf_path) if hub_invoice.pdf_path else None
                }

                self.db.flush()  # Get invoice ID for items

                # Clear existing items when updating (re-parse)
                self.db.query(HubInvoiceItem).filter(
                    HubInvoiceItem.invoice_id == invoice.id
                ).delete()

                # Create line items
                for line_num, item in enumerate(inv_data['items'], 1):
                    hub_item = HubInvoiceItem(
                        invoice_id=invoice.id,
                        line_number=line_num,
                        item_description=item['description'],
                        item_code=item['product_number'],
                        quantity=item['quantity'],
                        unit_of_measure=item['unit_of_measure'],
                        pack_size=item['pack_size'],
                        unit_price=item['unit_price'],
                        total_amount=item['total'],
                        is_mapped=False,
                        notes=f"UPC: {item['upc']}" if item['upc'] else None
                    )
                    self.db.add(hub_item)

                created_invoices.append({
                    'id': invoice.id,
                    'invoice_number': invoice.invoice_number,
                    'vendor': invoice.vendor_name,
                    'location': invoice.location_name,
                    'total': float(invoice.total_amount),
                    'items': len(inv_data['items'])
                })

            self.db.commit()

            # Post-parse validation: sanity checks + total reconciliation
            try:
                from integration_hub.services.post_parse_validator import apply_validation_to_invoice
                for inv_info in created_invoices:
                    validation_result = apply_validation_to_invoice(inv_info['id'], self.db)
                    inv_info['validation'] = validation_result
                    if validation_result.get('needs_review'):
                        logger.info(f"CSV invoice {inv_info['id']} flagged for review: {validation_result.get('review_reasons', [])}")
            except Exception as e:
                logger.error(f"Post-parse validation error for CSV invoices: {str(e)}")

            # Auto-map items for all created/updated invoices
            try:
                from integration_hub.services.auto_mapper import get_auto_mapper
                mapper = get_auto_mapper(self.db)
                for inv_info in created_invoices:
                    try:
                        stats = mapper.map_invoice_items(inv_info['id'])
                        inv_info['mapped'] = stats.get('mapped_count', 0)
                        inv_info['unmapped'] = stats.get('unmapped_count', 0)
                        logger.info(f"Auto-mapped CSV invoice {inv_info['id']}: {stats.get('mapped_count', 0)} mapped, {stats.get('unmapped_count', 0)} unmapped")
                    except Exception as e:
                        logger.error(f"Error auto-mapping CSV invoice {inv_info['id']}: {e}")
            except Exception as e:
                logger.error(f"Error initializing auto-mapper: {e}")

            return {
                'success': True,
                'message': f"Created/updated {len(created_invoices)} invoice(s)",
                'invoices': created_invoices
            }

        except Exception as e:
            logger.error(f"Error processing hub invoice {hub_invoice_id}: {e}")
            self.db.rollback()
            return {'success': False, 'message': str(e)}


def get_csv_parser(db: Session) -> CSVInvoiceParser:
    """Get CSV parser instance"""
    return CSVInvoiceParser(db)
