"""PDF generation service using WeasyPrint"""
import os
from weasyprint import HTML, CSS
from jinja2 import Environment, FileSystemLoader
from typing import Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PDFService:
    """Handles PDF generation for BEO documents"""

    def __init__(self):
        # Setup Jinja2 for PDF templates
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.jinja_env = Environment(
            loader=FileSystemLoader(os.path.join(base_dir, "templates", "pdf"))
        )

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
                'now': datetime.now()
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
                'now': datetime.now()
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
