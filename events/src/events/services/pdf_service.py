"""PDF generation service using WeasyPrint"""
import os
import base64
from weasyprint import HTML, CSS
from jinja2 import Environment, FileSystemLoader
from typing import Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def _to_et(dt):
    """Convert a datetime to Eastern Time for display"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(_ET)
    return dt


_VENUE_LOGO_MAP = {
    'the nest eatery': 'the-nest-eatery.png',
    'sw grill': 'sw-grill.png',
    'seaside grill': 'seaside-grill.png',
    'the links grill': 'the-links-grill.png',
    'park bistro': 'park-bistro.png',
    'okee grill': None,  # No logo on file
}


class PDFService:
    """Handles PDF generation for BEO documents"""

    def __init__(self):
        # Setup Jinja2 for PDF templates
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.jinja_env = Environment(
            loader=FileSystemLoader(os.path.join(base_dir, "templates", "pdf"))
        )
        self.logos_dir = os.path.join(base_dir, "static", "logos")
        # Add timezone conversion filter for templates
        self.jinja_env.filters['to_et'] = _to_et

    def _get_venue_logo_data_uri(self, venue) -> str:
        """Get base64 data URI for a venue's logo, or empty string if not found."""
        if not venue or not venue.name:
            return ""
        logo_file = _VENUE_LOGO_MAP.get(venue.name.lower())
        if not logo_file:
            return ""
        logo_path = os.path.join(self.logos_dir, logo_file)
        if not os.path.exists(logo_path):
            return ""
        try:
            with open(logo_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')
            return f"data:image/png;base64,{data}"
        except Exception:
            return ""

    def generate_beo_pdf(
        self,
        event: Any,
        client: Any,
        venue: Any = None,
        output_path: str = None
    ) -> bytes:
        """
        Generate BEO (Banquet Event Order) PDF

        Args:
            event: Event object
            client: Client object
            venue: Optional Venue object
            output_path: Optional file path to save PDF

        Returns:
            bytes: PDF file content
        """
        try:
            # Prepare template variables
            variables = {
                'event': event,
                'client': client,
                'venue': venue,
                'now': datetime.now(_ET)
            }

            # Render HTML template
            template = self.jinja_env.get_template('beo_template.html')
            html_content = template.render(**variables)

            # Generate PDF
            pdf_bytes = HTML(string=html_content).write_pdf()

            # Save to file if path provided
            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(pdf_bytes)
                logger.info(f"BEO PDF saved to: {output_path}")

            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate BEO PDF: {e}")
            raise

    def generate_catering_contract_pdf(
        self,
        event: Any,
        client: Any,
        venue: Any = None,
        output_path: str = None
    ) -> bytes:
        """Generate Catering Contract PDF"""
        try:
            event_date = ""
            event_times = ""
            if event.start_at:
                dt = _to_et(event.start_at) if event.start_at.tzinfo else event.start_at
                event_date = dt.strftime('%B %-d, %Y') if dt else ""
                start_time = dt.strftime('%-I:%M %p') if dt else ""
                if event.end_at:
                    end_dt = _to_et(event.end_at) if event.end_at.tzinfo else event.end_at
                    end_time = end_dt.strftime('%-I:%M %p') if end_dt else ""
                    event_times = f"from {start_time} to {end_time}"
                else:
                    event_times = f"at {start_time}"

            # Calculate financials from menu items (fallback when financials_json is empty)
            fin = event.financials_json or {}
            menu = event.menu_json or {}
            menu_subtotal = 0
            if menu.get('sections'):
                for section in menu['sections']:
                    for item in section.get('items', []):
                        price = item.get('price') or 0
                        qty = float(item.get('quantity') or 1)
                        menu_subtotal += price * qty

            subtotal = fin.get('subtotal') or menu_subtotal
            tax_rate = fin.get('tax_rate') or 0.065
            service_rate = fin.get('service_rate') or 0.21
            apply_tax = fin.get('apply_tax', True)
            apply_service = fin.get('apply_service_charge', True)
            service_charge = fin.get('service_charge') or (subtotal * service_rate if apply_service else 0)
            tax = fin.get('tax') or ((subtotal + service_charge) * tax_rate if apply_tax else 0)
            total = fin.get('total') or (subtotal + service_charge + tax)

            variables = {
                'event': event,
                'client': client,
                'venue': venue,
                'venue_logo': self._get_venue_logo_data_uri(venue),
                'now': datetime.now(_ET),
                'contract_date': datetime.now(_ET).strftime('%B %-d, %Y'),
                'event_date': event_date or 'TBD',
                'event_times': event_times,
                'food_subtotal': subtotal,
                'service_charge': service_charge,
                'service_rate_pct': service_rate * 100,
                'tax': tax,
                'tax_rate_pct': tax_rate * 100,
                'total': total,
                'has_financials': subtotal > 0,
                'deposit_required': fin.get('deposit_required') or 0,
            }

            template = self.jinja_env.get_template('catering_contract_template.html')
            html_content = template.render(**variables)
            pdf_bytes = HTML(string=html_content).write_pdf()

            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(pdf_bytes)
                logger.info(f"Catering contract PDF saved to: {output_path}")

            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate catering contract PDF: {e}")
            raise

    def generate_price_quote_pdf(
        self,
        event: Any,
        client: Any,
        venue: Any = None,
        output_path: str = None
    ) -> bytes:
        """Generate Price Quote PDF"""
        try:
            from datetime import timedelta

            event_date = ""
            event_times = ""
            if event.start_at:
                dt = _to_et(event.start_at) if event.start_at.tzinfo else event.start_at
                event_date = dt.strftime('%B %-d, %Y') if dt else ""
                start_time = dt.strftime('%-I:%M %p') if dt else ""
                if event.end_at:
                    end_dt = _to_et(event.end_at) if event.end_at.tzinfo else event.end_at
                    end_time = end_dt.strftime('%-I:%M %p') if end_dt else ""
                    event_times = f"{start_time} to {end_time}"
                else:
                    event_times = start_time

            # Calculate financials (same logic as contract)
            fin = event.financials_json or {}
            menu = event.menu_json or {}
            menu_subtotal = 0
            if menu.get('sections'):
                for section in menu['sections']:
                    for item in section.get('items', []):
                        price = item.get('price') or 0
                        qty = float(item.get('quantity') or 1)
                        menu_subtotal += price * qty

            subtotal = fin.get('subtotal') or menu_subtotal
            tax_rate = fin.get('tax_rate') or 0.065
            service_rate = fin.get('service_rate') or 0.21
            apply_tax = fin.get('apply_tax', True)
            apply_service = fin.get('apply_service_charge', True)
            service_charge = fin.get('service_charge') or (subtotal * service_rate if apply_service else 0)
            tax = fin.get('tax') or ((subtotal + service_charge) * tax_rate if apply_tax else 0)
            total = fin.get('total') or (subtotal + service_charge + tax)

            now = datetime.now(_ET)
            variables = {
                'event': event,
                'client': client,
                'venue': venue,
                'venue_logo': self._get_venue_logo_data_uri(venue),
                'now': now,
                'quote_date': now.strftime('%B %-d, %Y'),
                'valid_through': (now + timedelta(days=30)).strftime('%B %-d, %Y'),
                'event_date': event_date or 'TBD',
                'event_times': event_times,
                'food_subtotal': subtotal,
                'service_charge': service_charge,
                'service_rate_pct': service_rate * 100,
                'tax': tax,
                'tax_rate_pct': tax_rate * 100,
                'total': total,
                'has_financials': subtotal > 0,
            }

            template = self.jinja_env.get_template('price_quote_template.html')
            html_content = template.render(**variables)
            pdf_bytes = HTML(string=html_content).write_pdf()

            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(pdf_bytes)
                logger.info(f"Price quote PDF saved to: {output_path}")

            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate price quote PDF: {e}")
            raise

    def generate_event_summary_pdf(
        self,
        event: Any,
        tasks: list = None,
        output_path: str = None
    ) -> bytes:
        """
        Generate event summary PDF with task list

        Args:
            event: Event object
            tasks: Optional list of Task objects
            output_path: Optional file path to save PDF

        Returns:
            bytes: PDF file content
        """
        try:
            variables = {
                'event': event,
                'tasks': tasks or [],
                'now': datetime.now(_ET)
            }

            # For now, use the BEO template
            # TODO: Create dedicated event_summary_template.html
            template = self.jinja_env.get_template('beo_template.html')
            html_content = template.render(**variables)

            pdf_bytes = HTML(string=html_content).write_pdf()

            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(pdf_bytes)
                logger.info(f"Event summary PDF saved to: {output_path}")

            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate event summary PDF: {e}")
            raise

    def generate_custom_pdf(
        self,
        template_name: str,
        variables: Dict[str, Any],
        output_path: str = None
    ) -> bytes:
        """
        Generate PDF from custom template

        Args:
            template_name: Template filename (without .html)
            variables: Dictionary of template variables
            output_path: Optional file path to save PDF

        Returns:
            bytes: PDF file content
        """
        try:
            template = self.jinja_env.get_template(f'{template_name}.html')
            html_content = template.render(**variables)

            pdf_bytes = HTML(string=html_content).write_pdf()

            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(pdf_bytes)
                logger.info(f"Custom PDF saved to: {output_path}")

            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate custom PDF from {template_name}: {e}")
            raise
