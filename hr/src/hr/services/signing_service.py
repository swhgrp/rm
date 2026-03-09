"""
Self-hosted E-Signature Signing Service

Handles token generation, PDF overlay with signatures, and audit certificate generation.
"""

import os
import io
import secrets
import hashlib
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Directories
SIGNED_DOCS_DIR = "/app/documents/signed"
TEMPLATES_DIR = "/app/documents/templates"
SIGNING_COPIES_DIR = "/app/documents/signing"

# Token expiry
TOKEN_EXPIRY_DAYS = 7

# Base URL for signing links
BASE_URL = os.getenv("HR_BASE_URL", "https://rm.swhgrp.com/hr")


def generate_signing_token() -> str:
    """Generate a cryptographically secure signing token."""
    return secrets.token_urlsafe(64)


def compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_bytes_hash(data: bytes) -> str:
    """Compute SHA-256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


def create_signing_copy(template_file_path: str, employee_id: int, request_id: int) -> str:
    """
    Copy the template PDF to a per-request location for signing.
    Returns the path to the copy.
    """
    import shutil

    employee_dir = os.path.join(SIGNING_COPIES_DIR, str(employee_id))
    os.makedirs(employee_dir, exist_ok=True)

    filename = f"request_{request_id}.pdf"
    copy_path = os.path.join(employee_dir, filename)

    shutil.copy2(template_file_path, copy_path)
    return copy_path


def get_signing_url(token: str) -> str:
    """Get the public signing URL for a token."""
    return f"{BASE_URL}/sign/{token}"


def overlay_signatures_on_pdf(
    pdf_path: str,
    signature_fields: List[Dict[str, Any]],
    signature_image_b64: str,
    typed_name: str,
    field_values: Optional[Dict[str, Any]] = None
) -> bytes:
    """
    Overlay signature, name, date, and other fields onto the PDF.

    Args:
        pdf_path: Path to the original PDF
        signature_fields: List of field definitions with page, x, y, width, height, field_type
        signature_image_b64: Base64-encoded signature image (PNG)
        typed_name: Signer's typed name
        field_values: Additional field values keyed by field name

    Returns:
        Bytes of the PDF with overlaid signatures
    """
    field_values = field_values or {}

    # Read the original PDF
    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # Group fields by page
    fields_by_page = {}
    for field in signature_fields:
        page_num = field.get("page", 1) - 1  # Convert to 0-indexed
        if page_num not in fields_by_page:
            fields_by_page[page_num] = []
        fields_by_page[page_num].append(field)

    # Decode signature image
    sig_image = None
    if signature_image_b64:
        try:
            # Strip data URL prefix if present
            if "," in signature_image_b64:
                signature_image_b64 = signature_image_b64.split(",", 1)[1]
            sig_bytes = base64.b64decode(signature_image_b64)
            sig_image = ImageReader(io.BytesIO(sig_bytes))
        except Exception as e:
            logger.error(f"Error decoding signature image: {e}")

    # Process each page
    for page_idx in range(len(reader.pages)):
        page = reader.pages[page_idx]
        page_box = page.mediabox
        page_width = float(page_box.width)
        page_height = float(page_box.height)

        if page_idx in fields_by_page:
            # Create overlay for this page
            overlay_buffer = io.BytesIO()
            c = rl_canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))

            for field in fields_by_page[page_idx]:
                field_type = field.get("field_type", field.get("type", "signature"))
                # Use _percent values if available (legacy data has both pixel and percent)
                fx = float(field.get("x_percent", field.get("x", 0)))
                fy = float(field.get("y_percent", field.get("y", 0)))
                fw = float(field.get("width_percent", field.get("width", 10)))
                fh = float(field.get("height_percent", field.get("height", 3)))

                # Convert percentage to PDF points
                pdf_x = (fx / 100.0) * page_width
                # Y is from top in the UI, from bottom in PDF
                pdf_y = page_height - ((fy / 100.0) * page_height) - ((fh / 100.0) * page_height)
                pdf_w = (fw / 100.0) * page_width
                pdf_h = (fh / 100.0) * page_height

                if field_type == "signature" and sig_image:
                    c.drawImage(sig_image, pdf_x, pdf_y, width=pdf_w, height=pdf_h, mask='auto')

                elif field_type == "initial" and sig_image:
                    # Use signature scaled down for initials
                    c.drawImage(sig_image, pdf_x, pdf_y, width=pdf_w, height=pdf_h, mask='auto')

                elif field_type == "name":
                    # Typed name
                    c.setFont("Helvetica", min(pdf_h * 0.7, 14))
                    c.setFillColor(HexColor("#000000"))
                    c.drawString(pdf_x + 2, pdf_y + pdf_h * 0.25, typed_name)

                elif field_type == "date":
                    # Current date
                    date_str = datetime.now(_ET).strftime("%m/%d/%Y")
                    c.setFont("Helvetica", min(pdf_h * 0.7, 12))
                    c.setFillColor(HexColor("#000000"))
                    c.drawString(pdf_x + 2, pdf_y + pdf_h * 0.25, date_str)

                elif field_type == "text":
                    # Custom text from field_values
                    field_name = field.get("name", "")
                    text_val = field_values.get(field_name, "")
                    if text_val:
                        c.setFont("Helvetica", min(pdf_h * 0.7, 12))
                        c.setFillColor(HexColor("#000000"))
                        c.drawString(pdf_x + 2, pdf_y + pdf_h * 0.25, str(text_val))

            c.save()
            overlay_buffer.seek(0)

            # Merge overlay with original page
            overlay_reader = PdfReader(overlay_buffer)
            if len(overlay_reader.pages) > 0:
                page.merge_page(overlay_reader.pages[0])

        writer.add_page(page)

    # Write result to bytes
    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    return output_buffer.getvalue()


def generate_audit_certificate(
    document_title: str,
    request_id: int,
    signer_name: str,
    signer_email: str,
    signed_at: datetime,
    signer_ip: str,
    signer_user_agent: str,
    document_hash: str,
    signed_document_hash: str
) -> bytes:
    """
    Generate an audit certificate page as a PDF.

    Returns:
        PDF bytes for the audit certificate page
    """
    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Header background
    c.setFillColor(HexColor("#455A64"))
    c.rect(0, height - 120, width, 120, fill=True, stroke=False)

    # Header text
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - 55, "Certificate of Completion")

    c.setFont("Helvetica", 12)
    c.drawCentredString(width / 2, height - 80, "Electronic Signature Verification")

    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, height - 100, "SW Hospitality Group — rm.swhgrp.com")

    # Content area
    y = height - 160

    # Document info section
    c.setFillColor(HexColor("#455A64"))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, y, "Document Information")
    y -= 5
    c.setStrokeColor(HexColor("#455A64"))
    c.setLineWidth(1)
    c.line(60, y, width - 60, y)
    y -= 25

    rows = [
        ("Document Title", document_title),
        ("Document ID", f"SIG-{request_id:06d}"),
        ("Original Document Hash (SHA-256)", document_hash or "N/A"),
        ("Signed Document Hash (SHA-256)", signed_document_hash or "N/A"),
    ]

    c.setFillColor(HexColor("#333333"))
    for label, value in rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(60, y, f"{label}:")
        c.setFont("Helvetica", 10)
        # Handle long hashes
        if len(value) > 50:
            c.setFont("Courier", 8)
            c.drawString(60, y - 14, value)
            y -= 32
        else:
            c.drawString(280, y, value)
            y -= 20

    y -= 15

    # Signer info section
    c.setFillColor(HexColor("#455A64"))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, y, "Signer Information")
    y -= 5
    c.line(60, y, width - 60, y)
    y -= 25

    signed_at_et = signed_at
    if signed_at.tzinfo is None:
        signed_at_et = signed_at.replace(tzinfo=_ET)
    else:
        signed_at_et = signed_at.astimezone(_ET)

    signer_rows = [
        ("Signer Name", signer_name),
        ("Signer Email", signer_email),
        ("Signed Date & Time", signed_at_et.strftime("%B %d, %Y at %I:%M:%S %p ET")),
        ("Signer IP Address", signer_ip or "N/A"),
    ]

    c.setFillColor(HexColor("#333333"))
    for label, value in signer_rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(60, y, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(280, y, value)
        y -= 20

    # User agent (can be long)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "Browser / User Agent:")
    y -= 14
    c.setFont("Courier", 7)
    ua = signer_user_agent or "N/A"
    # Wrap long user agent strings
    max_chars = 100
    while ua:
        line = ua[:max_chars]
        c.drawString(60, y, line)
        ua = ua[max_chars:]
        y -= 12

    y -= 20

    # Verification section
    c.setFillColor(HexColor("#455A64"))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, y, "Verification Details")
    y -= 5
    c.line(60, y, width - 60, y)
    y -= 25

    verification_rows = [
        ("Signing Method", "Electronic Signature via SW Hospitality Group HR System"),
        ("Authentication", "Secure token-based signing link sent via email"),
        ("Consent", "Signer agreed to electronic signature terms before signing"),
        ("System", "SW Hospitality Group HR — rm.swhgrp.com"),
    ]

    c.setFillColor(HexColor("#333333"))
    for label, value in verification_rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(60, y, f"{label}:")
        c.setFont("Helvetica", 10)
        # Handle long values
        if len(value) > 45:
            c.drawString(60, y - 14, value)
            y -= 32
        else:
            c.drawString(280, y, value)
            y -= 20

    y -= 30

    # Legal notice
    c.setFillColor(HexColor("#666666"))
    c.setFont("Helvetica-Oblique", 8)
    notice_lines = [
        "This document was electronically signed using the SW Hospitality Group HR System.",
        "The electronic signature is legally binding under the Electronic Signatures in Global and National Commerce Act (E-SIGN)",
        "and the Uniform Electronic Transactions Act (UETA). The document hash values above can be used to verify",
        "the integrity of both the original and signed documents."
    ]
    for line in notice_lines:
        c.drawCentredString(width / 2, y, line)
        y -= 12

    # Footer
    c.setFillColor(HexColor("#455A64"))
    c.rect(0, 0, width, 40, fill=True, stroke=False)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, 20, f"Generated: {datetime.now(_ET).strftime('%B %d, %Y at %I:%M %p ET')} | SW Hospitality Group")

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def create_signed_pdf_with_audit(
    pdf_path: str,
    signature_fields: List[Dict[str, Any]],
    signature_image_b64: str,
    typed_name: str,
    field_values: Optional[Dict[str, Any]],
    request_id: int,
    document_title: str,
    signer_name: str,
    signer_email: str,
    signed_at: datetime,
    signer_ip: str,
    signer_user_agent: str,
    document_hash: str
) -> bytes:
    """
    Create the final signed PDF with overlaid signatures and appended audit certificate.

    Returns:
        Final PDF bytes
    """
    # Step 1: Overlay signatures on the original PDF
    signed_pdf_bytes = overlay_signatures_on_pdf(
        pdf_path, signature_fields, signature_image_b64, typed_name, field_values
    )

    # Step 2: Compute hash of signed PDF (before adding audit page)
    signed_document_hash = compute_bytes_hash(signed_pdf_bytes)

    # Step 3: Generate audit certificate page
    audit_pdf_bytes = generate_audit_certificate(
        document_title=document_title,
        request_id=request_id,
        signer_name=signer_name,
        signer_email=signer_email,
        signed_at=signed_at,
        signer_ip=signer_ip,
        signer_user_agent=signer_user_agent,
        document_hash=document_hash,
        signed_document_hash=signed_document_hash
    )

    # Step 4: Merge signed PDF + audit page
    writer = PdfWriter()

    signed_reader = PdfReader(io.BytesIO(signed_pdf_bytes))
    for page in signed_reader.pages:
        writer.add_page(page)

    audit_reader = PdfReader(io.BytesIO(audit_pdf_bytes))
    for page in audit_reader.pages:
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    final_pdf = output.getvalue()

    return final_pdf, signed_document_hash
