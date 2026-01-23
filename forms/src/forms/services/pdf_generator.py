"""PDF Generation Service using WeasyPrint"""
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# Base directory for templates
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PRINT_TEMPLATES_DIR = BASE_DIR / "templates" / "print"


class PDFGenerator:
    """Service for generating PDFs from form submissions."""

    def __init__(self):
        self.template_env = None
        if PRINT_TEMPLATES_DIR.exists():
            self.template_env = Environment(
                loader=FileSystemLoader(str(PRINT_TEMPLATES_DIR)),
                autoescape=True
            )

    def generate_pdf(
        self,
        template_slug: str,
        data: Dict[str, Any],
        signatures: list = None,
        metadata: Dict[str, Any] = None
    ) -> bytes:
        """
        Generate PDF for a form submission.

        Args:
            template_slug: Form template slug (e.g., 'first-report-of-injury')
            data: Form submission data
            signatures: List of signature records
            metadata: Additional metadata (reference_number, dates, etc.)

        Returns:
            PDF content as bytes
        """
        try:
            from weasyprint import HTML, CSS

            # Get template
            template_file = f"{template_slug}.html"
            if not self.template_env:
                template_file = "generic.html"

            try:
                template = self.template_env.get_template(template_file)
            except Exception:
                # Fall back to generic template
                template = self.template_env.get_template("generic.html")

            # Prepare context
            context = {
                "data": data,
                "signatures": signatures or [],
                "metadata": metadata or {},
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "company_name": "SW Hospitality Group"
            }

            # Render HTML
            html_content = template.render(**context)

            # Load base CSS
            css_file = PRINT_TEMPLATES_DIR / "base.css"
            stylesheets = []
            if css_file.exists():
                stylesheets.append(CSS(filename=str(css_file)))

            # Generate PDF
            html = HTML(string=html_content)
            pdf_bytes = html.write_pdf(stylesheets=stylesheets)

            return pdf_bytes

        except ImportError:
            logger.warning("WeasyPrint not available, returning placeholder PDF")
            return self._generate_placeholder_pdf(data, metadata)

        except Exception as e:
            logger.error(f"Error generating PDF: {e}")
            raise

    def _generate_placeholder_pdf(
        self,
        data: Dict[str, Any],
        metadata: Dict[str, Any] = None
    ) -> bytes:
        """Generate a simple placeholder PDF when WeasyPrint is not available."""
        # Return a simple text-based representation
        import json

        content = f"""
Form Submission Export
======================
Reference: {metadata.get('reference_number', 'N/A') if metadata else 'N/A'}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Data:
{json.dumps(data, indent=2, default=str)}
"""
        return content.encode('utf-8')


# Singleton instance
_pdf_generator = None


def get_pdf_generator() -> PDFGenerator:
    """Get PDF generator singleton."""
    global _pdf_generator
    if _pdf_generator is None:
        _pdf_generator = PDFGenerator()
    return _pdf_generator
