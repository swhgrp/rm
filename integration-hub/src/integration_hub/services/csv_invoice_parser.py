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
        self._load_location_mappings()

    def _load_location_mappings(self):
        """Load location code -> (id, name) mappings from inventory database"""
        try:
            # Query inventory database for location codes
            result = self.db.execute(sql_text("""
                SELECT id, code, name
                FROM inventory_db.locations
                WHERE is_active = true AND code IS NOT NULL
            """))
            for row in result:
                self._location_cache[str(row.code)] = (row.id, row.name)
            logger.info(f"Loaded {len(self._location_cache)} location mappings")
        except Exception as e:
            # Cross-database query failed - rollback to clear aborted transaction state
            self.db.rollback()
            logger.warning(f"Could not load locations from inventory_db: {e}")
            # Fallback: hardcode known mappings (should be updated to use proper DB connection)
            self._location_cache = {
                '400': (1, 'Seaside Grill'),
                '300': (2, 'The Nest Eatery'),
                '500': (3, 'SW Grill'),
                '200': (4, 'Okee Grill'),
                '700': (5, 'Park Bistro'),
                '600': (6, 'Links Grill'),
                '800': (7, "Tina's Treats"),
            }

    def get_location_by_store_number(self, store_number: str) -> Optional[Tuple[int, str]]:
        """
        Get location ID and name from store number.

        Args:
            store_number: Retailer Store Number from CSV (e.g., "500")

        Returns:
            Tuple of (location_id, location_name) or None if not found
        """
        return self._location_cache.get(str(store_number).strip())

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

    def parse_csv_content(self, content: str) -> Dict:
        """
        Parse CSV content string and group by invoice number.

        Args:
            content: CSV file content as string

        Returns:
            Parsed invoice data dict
        """
        try:
            reader = csv.DictReader(StringIO(content))
            fieldnames = reader.fieldnames or []

            # Detect statement/summary CSVs (no line-item detail)
            # Statement CSVs use camelCase columns like "VendorName", "InvoiceNumber"
            # Detail CSVs use spaced columns like "Invoice Number", "Product Number"
            statement_columns = {'VendorName', 'InvoiceNumber', 'InvoiceAmount'}
            if statement_columns.issubset(set(fieldnames)) and 'Product Number' not in fieldnames:
                logger.info(f"CSV detected as statement/summary (columns: {fieldnames[:5]}...)")
                return {
                    'success': True,
                    'message': 'CSV is a statement/summary file (no line-item detail)',
                    'invoices': [],
                    'is_statement': True
                }

            # Group rows by invoice number + store number (same invoice can span multiple stores)
            invoice_groups: Dict[str, Dict] = {}

            for row in reader:
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

                    # Get location mapping
                    location_info = self.get_location_by_store_number(store_num)
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
                        'items': []
                    }

                # Parse line item
                item = self._parse_line_item(row)
                if item:
                    invoice_groups[group_key]['items'].append(item)
                    invoice_groups[group_key]['total_amount'] += item['total']

            invoices = list(invoice_groups.values())

            return {
                'success': True,
                'message': f"Parsed {len(invoices)} invoice(s) with {sum(len(inv['items']) for inv in invoices)} line items",
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
            # If multiple invoices, create new records for additional ones
            for i, inv_data in enumerate(result['invoices']):
                if i == 0:
                    # Update the original hub_invoice
                    invoice = hub_invoice
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

                # Store raw data for reference
                invoice.raw_data = {
                    'source': 'fintech_csv',
                    'store_number': inv_data['store_number'],
                    'retailer_name': inv_data['retailer_name'],
                    'item_count': len(inv_data['items'])
                }

                self.db.flush()  # Get invoice ID for items

                # Clear existing items if updating
                if i == 0:
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
