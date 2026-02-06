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
from integration_hub.models.vendor_parsing_rule import VendorParsingRule
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text, func

logger = logging.getLogger(__name__)


def to_title_case(text: str) -> str:
    """
    Convert text to title case with smart handling for food/restaurant items.

    Handles edge cases:
    - Preserves common abbreviations (LB, OZ, CS, EA, etc.)
    - Handles slash/comma separated items
    - Preserves numbers and units
    - Handles hyphenated words

    Examples:
    - "CHICKEN BREAST BNLS SKNLS" -> "Chicken Breast Bnls Sknls"
    - "BEEF, GROUND 80/20" -> "Beef, Ground 80/20"
    - "OIL OLIVE EXTRA-VIRGIN" -> "Oil Olive Extra-Virgin"
    """
    if not text:
        return text

    # Common abbreviations/units to preserve in uppercase
    preserve_upper = {
        'LB', 'OZ', 'CS', 'EA', 'CT', 'PK', 'BX', 'BG', 'GL', 'QT', 'PT',
        'GAL', 'PKG', 'DOZ', 'PC', 'SL', 'BTL', 'CAN', 'JAR', 'TUB',
        'USDA', 'IQF', 'RTU', 'RTE', 'NAE', 'ABF', 'LSRW'
    }

    # Common words to keep lowercase (unless first word)
    lowercase_words = {'and', 'or', 'with', 'w/', 'in', 'for', 'of', 'the', 'a', 'an'}

    def process_word(word: str, is_first: bool) -> str:
        """Process a single word for title casing."""
        # Skip empty words
        if not word:
            return word

        # Check if it's a preserved abbreviation
        word_upper = word.upper()
        if word_upper in preserve_upper:
            return word_upper

        # Check for numbers/fractions (e.g., "80/20", "6x5", "0.75")
        if any(c.isdigit() for c in word):
            # Keep as-is if mostly numbers/symbols
            alpha_count = sum(1 for c in word if c.isalpha())
            if alpha_count <= 1:
                return word
            # Title case the letters, keep numbers
            result = []
            capitalize_next = True
            for c in word:
                if c.isalpha():
                    if capitalize_next:
                        result.append(c.upper())
                        capitalize_next = False
                    else:
                        result.append(c.lower())
                else:
                    result.append(c)
            return ''.join(result)

        # Handle hyphenated words (e.g., "extra-virgin")
        if '-' in word:
            parts = word.split('-')
            return '-'.join(process_word(p, i == 0) for i, p in enumerate(parts))

        # Lowercase words (except if first word)
        word_lower = word.lower()
        if not is_first and word_lower in lowercase_words:
            return word_lower

        # Standard title case
        return word.capitalize()

    # Split by spaces but preserve original spacing
    words = text.split(' ')
    result_words = []

    for i, word in enumerate(words):
        # Handle comma at end of word
        suffix = ''
        if word.endswith(','):
            suffix = ','
            word = word[:-1]
        elif word.endswith('.'):
            suffix = '.'
            word = word[:-1]

        processed = process_word(word, i == 0)
        result_words.append(processed + suffix)

    return ' '.join(result_words)


def normalize_vendor_name(name: str) -> str:
    """
    Normalize vendor name to title case with smart handling for company names.

    Handles:
    - All caps names ("GORDON FOOD SERVICE, INC." -> "Gordon Food Service, Inc.")
    - Common suffixes (Inc, LLC, Corp, Co, etc.)
    - Preserves acronyms, abbreviations, and state codes
    - Preserves known brand name capitalizations

    Examples:
    - "GORDON FOOD SERVICE, INC." -> "Gordon Food Service, Inc."
    - "GOLD COAST BEVERAGE LLC" -> "Gold Coast Beverage LLC"
    - "US FOODS" -> "US Foods"
    - "Southern Glazer's of FL" -> "Southern Glazer's of FL"
    - "AmeriGas" -> "AmeriGas"
    """
    if not name:
        return name

    # Known brand names with specific capitalizations
    brand_names = {
        'AMERIGAS': 'AmeriGas',
        'SYSCO': 'Sysco',
        'USFOODS': 'US Foods',
        'MCDONALDS': "McDonald's",
        'MCDONALD\'S': "McDonald's",
    }

    # Check if the entire name (normalized) matches a known brand
    name_upper = name.upper().strip()
    if name_upper in brand_names:
        return brand_names[name_upper]

    # Common company suffixes to handle specially
    company_suffixes = {
        'INC': 'Inc.',
        'INC.': 'Inc.',
        'LLC': 'LLC',
        'LLC.': 'LLC',
        'CORP': 'Corp.',
        'CORP.': 'Corp.',
        'CO': 'Co.',
        'CO.': 'Co.',
        'LTD': 'Ltd.',
        'LTD.': 'Ltd.',
        'LP': 'LP',
        'LLP': 'LLP',
    }

    # Common abbreviations to preserve in uppercase (including state codes)
    preserve_upper = {
        'US', 'USA', 'GFS', 'LLC', 'LP', 'LLP', 'DBA', 'ATT', 'IBM',
        # State codes
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
    }

    # Common words to keep lowercase (unless first word)
    lowercase_words = {'of', 'the', 'and', 'for', 'in', 'at', 'by', 'to'}

    # Split by spaces
    words = name.strip().split()
    result_words = []

    for i, word in enumerate(words):
        # Check for punctuation at end
        suffix = ''
        clean_word = word
        if word.endswith(','):
            suffix = ','
            clean_word = word[:-1]
        elif word.endswith('.'):
            suffix = '.'
            clean_word = word[:-1]

        word_upper = clean_word.upper()
        word_lower = clean_word.lower()

        # Check if it's a company suffix
        check_suffix = word_upper + suffix if suffix == '.' else word_upper
        if check_suffix in company_suffixes:
            result_words.append(company_suffixes[check_suffix])
            continue

        # Check if it should be preserved as uppercase
        if word_upper in preserve_upper:
            result_words.append(word_upper + suffix)
            continue

        # Check for lowercase words (not first word)
        if i > 0 and word_lower in lowercase_words:
            result_words.append(word_lower + suffix)
            continue

        # Check for possessives
        if clean_word.upper().endswith("'S"):
            base = clean_word[:-2]
            result_words.append(base.capitalize() + "'s" + suffix)
            continue

        # Standard title case
        result_words.append(clean_word.capitalize() + suffix)

    return ' '.join(result_words)


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def digit_similarity_score(code1: str, code2: str) -> float:
    """
    Calculate similarity score between two item codes, accounting for common OCR errors.

    Common OCR errors for digits:
    - 0 <-> O, 6, 8
    - 1 <-> I, l, 7
    - 2 <-> Z
    - 5 <-> S, 6
    - 6 <-> 0, 8, 5
    - 8 <-> 0, 6, B

    Returns a score from 0.0 to 1.0, where 1.0 is exact match.
    """
    # Remove any non-alphanumeric characters and normalize
    code1 = ''.join(c for c in str(code1).upper() if c.isalnum())
    code2 = ''.join(c for c in str(code2).upper() if c.isalnum())

    if not code1 or not code2:
        return 0.0

    if code1 == code2:
        return 1.0

    # Must be same length for high-confidence digit matching
    if len(code1) != len(code2):
        # Allow 1 character difference if very similar
        if abs(len(code1) - len(code2)) == 1:
            # Pad shorter string and check
            shorter, longer = (code1, code2) if len(code1) < len(code2) else (code2, code1)
            # Try inserting at each position
            best_score = 0.0
            for i in range(len(longer)):
                padded = shorter[:i] + longer[i] + shorter[i:]
                if padded == longer:
                    return 0.85  # One missing digit
            return 0.0
        return 0.0

    # Count matching positions and OCR-likely confusions
    exact_matches = 0
    ocr_confusions = 0

    # OCR confusion pairs (digit -> commonly confused with)
    ocr_pairs = {
        '0': {'O', '6', '8', 'D', 'Q'},
        '1': {'I', 'L', '7', 'T'},
        '2': {'Z'},
        '5': {'S', '6'},
        '6': {'0', '8', '5', 'G', 'B'},
        '8': {'0', '6', 'B'},
        'O': {'0', 'Q', 'D'},
        'B': {'8', '6'},
        'S': {'5'},
        'Z': {'2'},
        'I': {'1', 'L'},
        'L': {'1', 'I'},
        'G': {'6'},
    }

    for c1, c2 in zip(code1, code2):
        if c1 == c2:
            exact_matches += 1
        elif c2 in ocr_pairs.get(c1, set()) or c1 in ocr_pairs.get(c2, set()):
            ocr_confusions += 1

    # Score calculation
    total = len(code1)
    # Exact matches are worth 1.0, OCR confusions are worth 0.7 (still likely same item)
    score = (exact_matches + ocr_confusions * 0.7) / total

    # Require at least 70% of characters to match or be OCR confusable
    if (exact_matches + ocr_confusions) / total < 0.7:
        return 0.0

    return score


class InvoiceParser:
    """Parse invoices using OpenAI GPT-4o Vision"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key or self.api_key == "your-openai-key-here":
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY environment variable")

        self.client = OpenAI(api_key=self.api_key, timeout=120.0)  # 2 minute timeout

    def get_vendor_parsing_rules(self, vendor_id: int, db: Session) -> Optional[VendorParsingRule]:
        """
        Get vendor-specific parsing rules if they exist.

        Args:
            vendor_id: The vendor ID to look up rules for
            db: Database session

        Returns:
            VendorParsingRule or None if no rules exist
        """
        return db.query(VendorParsingRule).filter(
            VendorParsingRule.vendor_id == vendor_id,
            VendorParsingRule.is_active == True
        ).first()

    def _build_ai_system_prompt(self, vendor_rules: Optional[VendorParsingRule] = None) -> str:
        """
        Build the AI system prompt for invoice parsing.

        If vendor-specific rules exist, append them to the base prompt.

        Args:
            vendor_rules: Optional vendor-specific parsing rules

        Returns:
            Complete system prompt string
        """
        base_prompt = """You are an expert at parsing invoices and receipts for restaurant supply purchases.
                        This includes:
                        - Traditional wholesale invoices (Sysco, US Foods, Gordon Food Service)
                        - Retail warehouse receipts (BJ's Wholesale, Costco, Sam's Club, Restaurant Depot)
                        - Online order receipts (Amazon, WebstaurantStore)

                        You will receive one or more images representing all pages of a document.
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
                            "is_statement": boolean (true if document title/header contains "Statement", "Account Statement", "Final-Notification", "EFT", "Electronic Funds Transfer", or similar non-invoice payment notifications, false otherwise),
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
                        - FOR MULTI-PAGE DOCUMENTS: Combine line items from ALL pages into a single list
                        - is_statement: Set to true if the document title contains words like "Statement", "Account Statement", "Monthly Statement"
                          Statements are summary documents showing account activity/balance, not individual invoices for specific deliveries
                          Look for the word "Statement" prominently displayed at the top of the document
                        - vendor_name: The company/store name (BJ's Wholesale Club, Costco, Sysco, etc.)
                          For retail receipts, this is the store name at the top
                          For invoices, look for company name near logo, top-left, or "From:" section
                        - location_name: The DELIVERY/SHIP TO location OR the member/customer name
                          For retail receipts, this may be the member name or business name on the account
                          Look for "Ship To:", "Deliver To:", "Member:", or customer name
                        - invoice_number: Use receipt number, transaction number, or order number if no invoice number
                        - invoice_date: Transaction date, order date, or purchase date
                        - vendor_account_number: Member number, account number, or customer ID
                        - Extract ALL line items from ALL pages with precise quantities and prices

                        *** RETAIL RECEIPT HANDLING (BJ's, Costco, Sam's Club) ***
                        - These are point-of-sale receipts, not traditional invoices
                        - Look for item descriptions, quantities, and prices in receipt format
                        - Item codes may be UPC barcodes or internal SKU numbers
                        - Quantity is usually shown as "Qty: X" or just a number before the item
                        - Unit is typically "EA" (each) unless weight-based (then "LB")
                        - Tax may be shown as a separate line or included in total
                        - Total is at the bottom, often after payment method details

                        *** EXTREMELY IMPORTANT - TOTALS FROM LAST PAGE ONLY ***
                        - Multi-page invoices often show "Page Total" or "Page Subtotal" on early pages
                        - These intermediate page totals are NOT the invoice total
                        - You MUST read the FINAL INVOICE TOTAL from the LAST page only
                        - Look for labels like "Invoice Total", "Total Amount", "Amount Due", "Balance Due" on the LAST page
                        - IGNORE any "Page Total", "Page Subtotal", or "Continued on next page" amounts
                        - The subtotal, tax_amount, and total_amount fields must come from the LAST page's final totals section
                        - Common locations: bottom right of last page, in a box labeled "Total" or "Amount Due"

                        *** CRITICAL - ITEM CODE vs UPC/BARCODE ***
                        - Many invoices have BOTH an "Item Code" (or ITEM#, SKU, Product Code) AND a "UPC" (barcode number)
                        - The item_code field should contain the vendor's ITEM#/SKU/Product Code, NOT the UPC barcode
                        - UPC barcodes are typically 12-13 digits and often start with leading zeros (e.g., 0007199030106)
                        - Item codes/SKUs are typically shorter (4-8 digits) and are what vendors use for ordering
                        - For beverage distributors (Gold Coast, Southern Glaziers, etc.):
                          * Look for columns labeled "ITEM#", "Item", "SKU", "Prod#", or "Code" - use this value
                          * IGNORE columns labeled "UPC", "Barcode", or very long numeric codes starting with 000
                          * Example: If invoice shows ITEM# "14889" and UPC "0007199030106", use "14889" as item_code

                        - Verify that the sum of all line_total values approximately equals the subtotal
                        - For pack_size, look for packaging info in item description or separate column
                        - If any field is not visible/present, use null
                        - Be extremely precise with numbers (quantities, prices, totals)
                        - Return ONLY valid JSON, no explanations or markdown

                        *** CRITICAL - QUANTITY COLUMN SELECTION ***
                        - Many food service invoices (Gordon Food Service, Sysco, US Foods) have MULTIPLE quantity columns:
                          * "Qty Ord" or "Ordered" = quantity originally ordered (may differ from shipped)
                          * "Qty Ship" or "Shipped" or "Ship" = quantity ACTUALLY SHIPPED - USE THIS ONE
                          * "Pack Size" or "Size" = packaging info like "2x5 LB" meaning 2 bags of 5lb - THIS IS NOT QUANTITY
                        - ALWAYS use the SHIPPED quantity (Qty Ship), NOT the ordered quantity or pack size
                        - Pack size values like "2x5 LB", "6x1 GAL", "4x3 LB" describe PACKAGING, not quantity
                          * "2x5 LB" = 2 bags of 5 pounds each per case
                          * "6x1 GAL" = 6 one-gallon containers per case
                        - The quantity field should be the NUMBER OF CASES/UNITS shipped, usually a small integer (1-10)"""

        # If vendor-specific rules exist, append them
        if vendor_rules and vendor_rules.ai_instructions:
            vendor_instructions = f"""

                        *** VENDOR-SPECIFIC INSTRUCTIONS ***
                        The following rules are specific to this vendor's invoice format:

                        {vendor_rules.ai_instructions}"""
            base_prompt += vendor_instructions

            # Add column-specific hints if provided
            column_hints = []
            if vendor_rules.quantity_column:
                column_hints.append(f"- Use the \"{vendor_rules.quantity_column}\" column for quantity")
            if vendor_rules.item_code_column:
                column_hints.append(f"- Use the \"{vendor_rules.item_code_column}\" column for item code/SKU")
            if vendor_rules.price_column:
                column_hints.append(f"- Use the \"{vendor_rules.price_column}\" column for unit price")
            if vendor_rules.pack_size_format:
                column_hints.append(f"- Pack size format is \"{vendor_rules.pack_size_format}\" (e.g., packaging info, NOT quantity)")

            if column_hints:
                base_prompt += "\n\n                        Column mappings:\n                        " + "\n                        ".join(column_hints)

        return base_prompt

    def parse_invoice_pdf(self, pdf_path: str, vendor_rules: Optional[VendorParsingRule] = None) -> Dict:
        """
        Parse invoice PDF using OpenAI GPT-4o Vision

        Converts PDF to images and uses vision model to extract structured data.

        Args:
            pdf_path: Path to the PDF file
            vendor_rules: Optional vendor-specific parsing rules to customize the AI prompt

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

            # Build AI system prompt - with vendor rules if provided
            system_prompt = self._build_ai_system_prompt(vendor_rules)

            # Retry logic for transient API failures
            max_retries = 2
            result_text = None
            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"OpenAI API call attempt {attempt + 1}/{max_retries + 1}")
                    response = self.client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "system",
                                "content": system_prompt
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

                    # Check for content filter or refusal
                    if response.choices[0].finish_reason == 'content_filter':
                        logger.error("OpenAI content filter triggered")
                        return {
                            "success": False,
                            "error": "AI content filter blocked the response - document may contain restricted content",
                            "message": "Failed to parse invoice due to content restrictions"
                        }

                    # Check for empty response - retry if we have attempts left
                    if not result_text:
                        logger.warning(f"OpenAI returned empty response on attempt {attempt + 1}. Finish reason: {response.choices[0].finish_reason}")
                        if attempt < max_retries:
                            import time
                            time.sleep(2)  # Wait before retry
                            continue
                        else:
                            return {
                                "success": False,
                                "error": "AI returned empty response after retries - the invoice image may not be readable",
                                "message": "Failed to parse invoice - try a clearer scan"
                            }

                    # Success - break out of retry loop
                    break

                except Exception as api_error:
                    last_error = api_error
                    logger.warning(f"OpenAI API error on attempt {attempt + 1}: {str(api_error)}")
                    if attempt < max_retries:
                        import time
                        time.sleep(2)  # Wait before retry
                        continue
                    else:
                        raise  # Re-raise on final attempt

            logger.info(f"Raw AI response (first 500 chars): {result_text[:500]}...")

            # Parse JSON from response
            # Extract JSON from markdown code blocks if present
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]

            result_text = result_text.strip()
            if not result_text:
                logger.error("AI response contained no JSON data after extraction")
                return {
                    "success": False,
                    "error": "AI response contained no parseable data",
                    "message": "Failed to extract invoice data"
                }

            parsed_data = json.loads(result_text)

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
        1. Check vendor aliases table first
        2. Exact match (case insensitive)
        3. Partial match - vendor name contains parsed name
        4. Partial match - parsed name contains vendor name
        """
        if not vendor_name:
            return None

        vendor_name = vendor_name.strip()

        # 1. Check vendor aliases first - this handles known variations
        from integration_hub.models.vendor_alias import VendorAlias
        normalized = vendor_name.lower().strip()
        alias = db.query(VendorAlias).filter(
            VendorAlias.alias_name_normalized == normalized,
            VendorAlias.is_active == True
        ).first()

        if alias:
            vendor = db.query(Vendor).filter(Vendor.id == alias.vendor_id).first()
            if vendor:
                logger.info(f"Vendor alias match: '{vendor_name}' -> '{vendor.name}' (ID: {vendor.id})")
                return vendor

        # 2. Exact match (case insensitive)
        vendor = db.query(Vendor).filter(
            Vendor.name.ilike(vendor_name)
        ).first()

        if vendor:
            logger.info(f"Exact vendor match: '{vendor_name}' -> '{vendor.name}' (ID: {vendor.id})")
            return vendor

        # 3. Partial match - vendor name contains the parsed name
        vendor = db.query(Vendor).filter(
            Vendor.name.ilike(f"%{vendor_name}%")
        ).first()

        if vendor:
            logger.info(f"Partial vendor match (contains): '{vendor_name}' -> '{vendor.name}' (ID: {vendor.id})")
            return vendor

        # 4. Partial match - parsed name contains vendor name
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

        inventory_db_url = os.getenv('INVENTORY_DATABASE_URL')
        if not inventory_db_url:
            logger.warning("INVENTORY_DATABASE_URL not set, cannot match location")
            return None

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

    def _fix_upc_as_item_code(self, invoice_id: int, db: Session) -> dict:
        """
        Fix cases where UPC barcode was extracted instead of item code.

        UPC codes are typically 12-13 digits starting with leading zeros (e.g., 0007199030106).
        Item codes are typically shorter (4-8 digits).

        This learns from historical data - if we've seen this item description before
        with a proper item code, we use that. Also checks inventory vendor_items.

        Returns dict with fix stats.
        """
        fixes = []

        try:
            # Get invoice items that look like UPC codes (>10 digits, starts with 000)
            items_result = db.execute(
                sql_text("""
                    SELECT id, item_code, item_description
                    FROM hub_invoice_items
                    WHERE invoice_id = :invoice_id
                      AND item_code IS NOT NULL
                      AND LENGTH(item_code) > 10
                      AND item_code LIKE '000%'
                """),
                {"invoice_id": invoice_id}
            ).fetchall()

            if not items_result:
                return {"fixed": 0, "fixes": []}

            for item in items_result:
                item_id, upc_code, description = item

                # Strategy 1: Look up by description in previous invoices
                # Find items with same description that have a proper short item code
                # Normalize description for matching (remove extra spaces, case-insensitive)
                desc_normalized = ' '.join(description.split()).upper()
                historical = db.execute(
                    sql_text("""
                        SELECT item_code, COUNT(*) as cnt
                        FROM hub_invoice_items
                        WHERE UPPER(REPLACE(item_description, '  ', ' ')) = :desc
                          AND item_code IS NOT NULL
                          AND LENGTH(item_code) <= 10
                          AND item_code NOT LIKE '000%'
                        GROUP BY item_code
                        ORDER BY cnt DESC
                        LIMIT 1
                    """),
                    {"desc": desc_normalized}
                ).fetchone()

                if historical:
                    correct_code = historical[0]
                    db.execute(
                        sql_text("""
                            UPDATE hub_invoice_items
                            SET item_code = :correct_code
                            WHERE id = :item_id
                        """),
                        {"item_id": item_id, "correct_code": correct_code}
                    )
                    fixes.append({
                        "original_upc": upc_code,
                        "corrected_code": correct_code,
                        "description": description,
                        "method": "historical_match"
                    })
                    logger.info(f"Fixed UPC->ItemCode: {upc_code} -> {correct_code} (from history)")
                    continue

                # Strategy 2: Check item_code_mapping_deprecated for description match
                mapping = db.execute(
                    sql_text("""
                        SELECT item_code
                        FROM item_code_mapping_deprecated
                        WHERE UPPER(REPLACE(canonical_description, '  ', ' ')) = :desc
                          AND LENGTH(item_code) <= 10
                          AND item_code NOT LIKE '000%'
                        LIMIT 1
                    """),
                    {"desc": desc_normalized}
                ).fetchone()

                if mapping:
                    correct_code = mapping[0]
                    db.execute(
                        sql_text("""
                            UPDATE hub_invoice_items
                            SET item_code = :correct_code
                            WHERE id = :item_id
                        """),
                        {"item_id": item_id, "correct_code": correct_code}
                    )
                    fixes.append({
                        "original_upc": upc_code,
                        "corrected_code": correct_code,
                        "description": description,
                        "method": "mapping_table"
                    })
                    logger.info(f"Fixed UPC->ItemCode: {upc_code} -> {correct_code} (from mapping table)")
                    continue

            if fixes:
                db.commit()

            return {"fixed": len(fixes), "fixes": fixes}

        except Exception as e:
            logger.error(f"Error fixing UPC codes for invoice {invoice_id}: {str(e)}")
            db.rollback()
            return {"fixed": 0, "fixes": [], "error": str(e)}

    def _fix_ocr_by_description(self, invoice_id: int, db: Session) -> dict:
        """
        Fix OCR errors by matching descriptions against inventory.

        When item codes don't match but descriptions are very similar,
        use the inventory SKU instead of the OCR'd code.

        This handles cases like:
        - Parsed: 820001 "Bread Wh Ht Crwn 3/4"
        - Inventory: 622471 "Bread, White, High Crown, 3/4 Inch Sliced"

        Returns dict with fix stats.
        """
        import os
        from sqlalchemy import create_engine, text

        fixes = []

        try:
            # Get unmapped invoice items
            items_result = db.execute(
                sql_text("""
                    SELECT id, item_code, item_description
                    FROM hub_invoice_items
                    WHERE invoice_id = :invoice_id
                      AND is_mapped = false
                      AND item_code IS NOT NULL
                      AND item_code != ''
                """),
                {"invoice_id": invoice_id}
            ).fetchall()

            if not items_result:
                return {"fixed": 0, "fixes": []}

            # Get vendor_name from invoice (use name matching, not ID, since IDs differ between systems)
            invoice_vendor = db.execute(
                sql_text("""
                    SELECT vendor_name FROM hub_invoices WHERE id = :invoice_id
                """),
                {"invoice_id": invoice_id}
            ).fetchone()

            if not invoice_vendor or not invoice_vendor[0]:
                return {"fixed": 0, "fixes": []}

            vendor_name = invoice_vendor[0]

            # Get inventory items for vendors matching this name
            inventory_db_url = os.getenv('INVENTORY_DATABASE_URL')
            if not inventory_db_url:
                logger.warning("INVENTORY_DATABASE_URL not set, cannot fix UOMs")
                return {"fixed": 0, "fixes": []}
            engine = create_engine(inventory_db_url)

            # Extract base vendor name for matching (e.g., "Gordon Food Service" from "Gordon Food Service Inc.")
            # Strip common suffixes: Inc., Inc, LLC, L.L.C., Corp., Corporation
            base_vendor = vendor_name
            for suffix in ['Inc.', 'Inc', 'LLC', 'L.L.C.', 'Corp.', 'Corporation', 'Co.', 'Company']:
                base_vendor = base_vendor.replace(suffix, '')
            base_vendor = base_vendor.replace(',', '').strip()

            with engine.connect() as inv_conn:
                inv_items = inv_conn.execute(text("""
                    SELECT vi.vendor_sku, vi.vendor_product_name
                    FROM vendor_items vi
                    JOIN vendors v ON v.id = vi.vendor_id
                    WHERE v.name ILIKE :vendor_pattern AND vi.is_active = true
                """), {"vendor_pattern": f"%{base_vendor}%"}).fetchall()

            if not inv_items:
                return {"fixed": 0, "fixes": []}

            # Build normalized description lookup
            # Common abbreviation expansions for food service items
            ABBREVIATIONS = {
                # Colors
                'wh': 'white', 'wht': 'white', 'whl': 'whole',
                'grn': 'green', 'gn': 'green',
                'rd': 'red', 'yel': 'yellow', 'ylw': 'yellow',
                # Sizes
                'sml': 'small', 'sm': 'small',
                'med': 'medium', 'md': 'medium',
                'lg': 'large', 'lrg': 'large',
                'xlg': 'xlarge', 'xl': 'xlarge',
                # Units
                'oz': 'ounce', 'lb': 'pound', 'lbs': 'pound',
                'gal': 'gallon', 'qt': 'quart', 'pt': 'pint',
                'cs': 'case', 'ct': 'count',
                'btl': 'bottle', 'can': 'can', 'bag': 'bag',
                # Bread-related
                'ht': 'high', 'hi': 'high', 'hn': 'high',
                'crwn': 'crown', 'crn': 'crown', 'rcnw': 'crown', 'rcrwn': 'crown',
                'srdgh': 'sourdough', 'srdh': 'sourdough', 'srgh': 'sourdough', 'srdough': 'sourdough',
                'evrthng': 'everything', 'evrthing': 'everything', 'evtthng': 'everything',
                'pnni': 'panini', 'panni': 'panini',
                'ciab': 'ciabatta', 'ciabta': 'ciabatta',
                'focac': 'focaccia', 'foccia': 'focaccia',
                'baguet': 'baguette', 'bagut': 'baguette',
                'brioch': 'brioche', 'brich': 'brioche',
                'hoagi': 'hoagie', 'hoag': 'hoagie',
                'srcld': 'sliced', 'slcid': 'sliced',
                'slcd': 'sliced', 'sli': 'sliced',
                # Proteins
                'chix': 'chicken', 'chik': 'chicken', 'chkn': 'chicken',
                'bf': 'beef', 'bef': 'beef',
                'prk': 'pork',
                # Temperature/State
                'frz': 'frozen', 'frzn': 'frozen',
                'frsh': 'fresh',
                # Food service abbreviations (common on invoices)
                'pty': 'patties', 'pty': 'patties', 'ptty': 'patties',
                'seas': 'seasoned', 'ssnd': 'seasoned',
                'grnd': 'ground', 'grd': 'ground',
                'bnls': 'boneless', 'bnlss': 'boneless',
                'sknls': 'skinless', 'sklss': 'skinless',
                'brst': 'breast',
                'tdr': 'tender', 'tndr': 'tender',
                'flt': 'fillet', 'filt': 'fillet',
                'wng': 'wing', 'wngs': 'wings',
                'thgh': 'thigh',
                'drm': 'drum', 'drmstk': 'drumstick',
                'sldr': 'slider',
                'burg': 'burger', 'brgr': 'burger',
                'stk': 'steak',
                'rst': 'roast',
                'smkd': 'smoked', 'smk': 'smoked',
                'crspy': 'crispy',
                'brd': 'breaded', 'brdd': 'breaded',
                'frttr': 'fritter',
                'cvp': 'cup',
                'hmstyl': 'homestyle',
                'org': 'original',
                'reg': 'regular',
                'spc': 'spicy',
                'bbq': 'barbecue',
                'trky': 'turkey', 'trk': 'turkey',
                'ssg': 'sausage', 'saus': 'sausage',
                'bcon': 'bacon', 'bcn': 'bacon',
                'ham': 'ham',
                # Equipment/Supplies
                'grill': 'griddle', 'gril': 'griddle', 'drill': 'griddle',  # OCR often misreads G as D
                'brck': 'brick', 'brik': 'brick',
                # Dairy
                'chz': 'cheese', 'chs': 'cheese',
                'mzz': 'mozzarella', 'mozz': 'mozzarella',
                'parm': 'parmesan',
                'ched': 'cheddar',
                'swss': 'swiss',
                'amrc': 'american',
                'crm': 'cream',
                'btr': 'butter',
                # Produce
                'tom': 'tomato', 'tmo': 'tomato',
                'let': 'lettuce', 'ltt': 'lettuce',
                'onin': 'onion', 'onn': 'onion',
                'pep': 'pepper', 'ppr': 'pepper',
                'pot': 'potato', 'pto': 'potato',
                'mush': 'mushroom', 'mshm': 'mushroom',
                'jlpn': 'jalapeno',
                'clntr': 'cilantro',
                # Sauces/Condiments
                'sce': 'sauce', 'sc': 'sauce',
                'drsg': 'dressing',
                'may': 'mayo', 'myo': 'mayo',
                'mstrd': 'mustard',
                'ktchp': 'ketchup',
                'rnch': 'ranch',
                'alf': 'alfredo',
                'mrnra': 'marinara',
                # Packaging
                'pk': 'pack',
                'bx': 'box',
                'tub': 'tub',
                'jug': 'jug',
                'pch': 'pouch',
                'wrp': 'wrap', 'wrpd': 'wrapped',
                # Other common
                'asst': 'assorted',
                'var': 'variety',
                'mix': 'mix',
                'blnd': 'blend',
                'prem': 'premium',
                'sel': 'select',
                'chc': 'choice',
                'prm': 'prime',
                # Fries/potato related
                'wskin': 'skin', 'skinn': 'skin',
                'xlng': 'long', 'klng': 'long', 'lng': 'long',
                'xtra': 'extra',
                'fncy': 'fancy',
                # Beverages
                'lite': 'light', 'lt': 'light', 'lte': 'light',
                'bud': 'budweiser',
                'mic': 'michelob', 'mich': 'michelob',
                'mill': 'miller', 'mlr': 'miller',
                'cor': 'corona', 'crna': 'corona',
                'hein': 'heineken', 'hnkn': 'heineken',
                'mod': 'modelo', 'mdlo': 'modelo',
                'yng': 'yuengling', 'yngl': 'yuengling',
                'stla': 'stella', 'stl': 'stella',
                'blu': 'blue', 'bl': 'blue',
                'mtn': 'mountain', 'mt': 'mountain',
                'dew': 'dew',
                'sprt': 'sprite', 'spri': 'sprite',
                'fnt': 'fanta', 'fnta': 'fanta',
            }

            def normalize_desc(desc):
                """Normalize description for matching, expanding abbreviations"""
                if not desc:
                    return ""
                # Remove punctuation, lowercase, split into words
                import re
                words = re.findall(r'[a-z0-9]+', desc.lower())
                # Expand abbreviations
                expanded = []
                for w in words:
                    if w in ABBREVIATIONS:
                        expanded.append(ABBREVIATIONS[w])
                    else:
                        expanded.append(w)
                # Remove common filler words
                stopwords = {'inch', 'sliced', 'frozen', 'fresh', 'the', 'a', 'an', 'with', 'and', 'case'}
                words = [w for w in expanded if w not in stopwords and len(w) > 1]
                return set(words)

            inv_lookup = {}
            for sku, name in inv_items:
                norm_words = normalize_desc(name)
                inv_lookup[sku] = {"name": name, "words": norm_words}

            for item in items_result:
                item_id, parsed_code, parsed_desc = item

                # Check if code already exists in inventory
                if parsed_code in inv_lookup:
                    continue

                # Normalize parsed description
                parsed_words = normalize_desc(parsed_desc)
                if len(parsed_words) < 2:
                    continue

                # Find best matching inventory item by description
                best_match = None
                best_score = 0

                for sku, info in inv_lookup.items():
                    inv_words = info["words"]
                    if len(inv_words) < 2:
                        continue

                    # Calculate word overlap (Jaccard similarity)
                    common = parsed_words & inv_words
                    total = parsed_words | inv_words
                    if not total:
                        continue

                    similarity = len(common) / len(total)

                    # Also check if parsed code is similar to inventory SKU (handles OCR)
                    code_sim = digit_similarity_score(parsed_code, sku)

                    # Combined score: heavily weight description match
                    # Count significant common words (non-numeric, length > 2)
                    significant_common = [w for w in common if not w.isdigit() and len(w) > 2]

                    # Acceptance criteria (in priority order):
                    # 1. Very strong description match (>=0.8) - accept regardless of code similarity
                    #    (When descriptions match almost perfectly, OCR likely corrupted the code entirely)
                    # 2. Strong description match (>=0.6) with some code similarity (>=0.16)
                    # 3. Good description match (>=0.4) with moderate code similarity (>=0.33)
                    # 4. Multiple significant matching words (>=3) even with lower Jaccard
                    #    (Handles cases where inventory has long description but invoice is abbreviated)
                    accept = False
                    if similarity >= 0.8:
                        accept = True  # Very strong description match overrides any code mismatch
                    elif similarity >= 0.6 and code_sim >= 0.16:
                        accept = True  # Strong description match can override poor code match
                    elif similarity >= 0.4 and code_sim >= 0.33:
                        accept = True  # Moderate match on both
                    elif len(significant_common) >= 3 and similarity >= 0.3:
                        accept = True  # Multiple significant words match (e.g., angus, patties, seasoned)

                    if accept:
                        # Score calculation: when code_sim is 0 or very low, use description similarity alone
                        # This handles cases where OCR completely corrupted the code
                        if code_sim < 0.1:
                            combined = similarity  # Use description similarity directly
                        else:
                            combined = similarity * 0.8 + code_sim * 0.2  # Weight description more heavily

                        if combined > best_score:
                            best_score = combined
                            best_match = {
                                "sku": sku,
                                "name": info["name"],
                                "desc_similarity": similarity,
                                "code_similarity": code_sim
                            }

                if best_match and best_score >= 0.35:
                    # Update the item code
                    db.execute(
                        sql_text("""
                            UPDATE hub_invoice_items
                            SET item_code = :correct_code
                            WHERE id = :item_id
                        """),
                        {"item_id": item_id, "correct_code": best_match["sku"]}
                    )

                    fixes.append({
                        "original_code": parsed_code,
                        "corrected_code": best_match["sku"],
                        "original_desc": parsed_desc,
                        "matched_desc": best_match["name"],
                        "desc_similarity": round(best_match["desc_similarity"], 2),
                        "code_similarity": round(best_match["code_similarity"], 2)
                    })

                    logger.info(
                        f"Fixed by description: {parsed_code} -> {best_match['sku']} "
                        f"(desc_sim: {best_match['desc_similarity']:.2f}, "
                        f"code_sim: {best_match['code_similarity']:.2f})"
                    )

            if fixes:
                db.commit()

            return {"fixed": len(fixes), "fixes": fixes}

        except Exception as e:
            logger.error(f"Error fixing by description for invoice {invoice_id}: {str(e)}")
            db.rollback()
            return {"fixed": 0, "fixes": [], "error": str(e)}

    def _validate_and_correct_item_codes(self, invoice_id: int, db: Session) -> dict:
        """
        Validate extracted item codes against verified codes and correct OCR errors.

        Uses fuzzy matching to detect common OCR errors like:
        - 006032 instead of 206032 (leading digit confusion)
        - 260632 instead of 206032 (digit transposition)

        Only corrects codes when:
        1. The verified code has occurrence_count > 3 (well-established)
        2. The similarity score is >= 0.8 (high confidence)
        3. The descriptions are similar (prevents false matches)

        Returns dict with correction stats.
        """
        corrections = []

        try:
            # Get all invoice items with item codes
            items_result = db.execute(
                sql_text("""
                    SELECT id, item_code, item_description
                    FROM hub_invoice_items
                    WHERE invoice_id = :invoice_id
                      AND item_code IS NOT NULL
                      AND item_code != ''
                """),
                {"invoice_id": invoice_id}
            ).fetchall()

            if not items_result:
                return {"corrected": 0, "corrections": []}

            # Get verified item codes with high occurrence count
            verified_codes = db.execute(
                sql_text("""
                    SELECT item_code, canonical_description, occurrence_count
                    FROM item_code_mapping_deprecated
                    WHERE is_verified = true OR occurrence_count >= 3
                    ORDER BY occurrence_count DESC
                """)
            ).fetchall()

            if not verified_codes:
                return {"corrected": 0, "corrections": []}

            # Build lookup dict for verified codes
            verified_lookup = {
                row[0]: {"description": row[1], "occurrences": row[2]}
                for row in verified_codes
            }

            for item in items_result:
                item_id, parsed_code, parsed_desc = item

                # Skip if code already exists exactly in verified codes
                if parsed_code in verified_lookup:
                    continue

                # Find best matching verified code
                best_match = None
                best_score = 0.0

                for verified_code, info in verified_lookup.items():
                    # Calculate code similarity
                    code_score = digit_similarity_score(parsed_code, verified_code)

                    if code_score < 0.8:
                        continue

                    # Also check description similarity to avoid false positives
                    desc_words1 = set(parsed_desc.upper().split()) if parsed_desc else set()
                    desc_words2 = set(info["description"].upper().split()) if info["description"] else set()

                    if desc_words1 and desc_words2:
                        # Need at least one common word in description
                        common_words = desc_words1 & desc_words2
                        if not common_words:
                            continue

                    # Prefer higher occurrence counts for tie-breaking
                    combined_score = code_score + (info["occurrences"] / 1000)

                    if combined_score > best_score:
                        best_score = combined_score
                        best_match = {
                            "verified_code": verified_code,
                            "code_score": code_score,
                            "verified_desc": info["description"],
                            "occurrences": info["occurrences"]
                        }

                if best_match and best_match["code_score"] >= 0.8:
                    # Correct the item code
                    db.execute(
                        sql_text("""
                            UPDATE hub_invoice_items
                            SET item_code = :correct_code,
                                item_description = COALESCE(:correct_desc, item_description)
                            WHERE id = :item_id
                        """),
                        {
                            "item_id": item_id,
                            "correct_code": best_match["verified_code"],
                            "correct_desc": best_match["verified_desc"]
                        }
                    )

                    corrections.append({
                        "original_code": parsed_code,
                        "corrected_code": best_match["verified_code"],
                        "similarity": round(best_match["code_score"], 2),
                        "description": best_match["verified_desc"]
                    })

                    logger.info(
                        f"OCR correction: {parsed_code} -> {best_match['verified_code']} "
                        f"(similarity: {best_match['code_score']:.2f}, "
                        f"verified occurrences: {best_match['occurrences']})"
                    )

            if corrections:
                db.commit()

            return {
                "corrected": len(corrections),
                "corrections": corrections
            }

        except Exception as e:
            logger.error(f"Error validating item codes for invoice {invoice_id}: {str(e)}")
            db.rollback()
            return {"corrected": 0, "corrections": [], "error": str(e)}

    def _normalize_item_descriptions(self, invoice_id: int, db: Session) -> int:
        """
        Normalize item descriptions based on item codes.

        If an item code already exists in the item_code_mapping_deprecated table with a canonical description,
        update the item description to match. This fixes OCR variations where the same product
        gets parsed with slightly different descriptions.

        Returns the number of items normalized.
        """
        try:
            # Update item descriptions to match canonical descriptions based on item code
            result = db.execute(
                sql_text("""
                    UPDATE hub_invoice_items hi
                    SET item_description = icm.canonical_description
                    FROM item_code_mapping_deprecated icm
                    WHERE hi.invoice_id = :invoice_id
                      AND hi.item_code IS NOT NULL
                      AND hi.item_code != ''
                      AND hi.item_code = icm.item_code
                      AND hi.item_description != icm.canonical_description
                """),
                {"invoice_id": invoice_id}
            )
            normalized_count = result.rowcount
            db.commit()

            if normalized_count > 0:
                logger.info(f"Normalized {normalized_count} item descriptions for invoice {invoice_id}")

            # Also add any new item codes to the mapping table for future normalization
            db.execute(
                sql_text("""
                    INSERT INTO item_code_mapping_deprecated (item_code, canonical_description, occurrence_count)
                    SELECT item_code, item_description, 1
                    FROM hub_invoice_items
                    WHERE invoice_id = :invoice_id
                      AND item_code IS NOT NULL
                      AND item_code != ''
                    ON CONFLICT (item_code) DO UPDATE SET
                        occurrence_count = item_code_mapping_deprecated.occurrence_count + 1,
                        updated_at = NOW()
                """),
                {"invoice_id": invoice_id}
            )
            db.commit()

            return normalized_count

        except Exception as e:
            logger.error(f"Error normalizing item descriptions for invoice {invoice_id}: {str(e)}")
            db.rollback()
            return 0

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
            # Check if invoice already has a vendor - if so, use vendor-specific parsing rules
            vendor_rules = None
            if invoice.vendor_id:
                vendor_rules = self.get_vendor_parsing_rules(invoice.vendor_id, db)
                if vendor_rules:
                    logger.info(f"Using vendor parsing rules for vendor_id={invoice.vendor_id} during re-parse")

            # Parse with AI (with vendor rules if available)
            parse_result = self.parse_invoice_pdf(invoice.pdf_path, vendor_rules=vendor_rules)

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

            # Update invoice with parsed data (normalize vendor name to title case)
            raw_vendor_name = parsed_data.get('vendor_name') or 'Unknown Vendor'
            invoice.vendor_name = normalize_vendor_name(raw_vendor_name)
            invoice.vendor_account_number = parsed_data.get('vendor_account_number')
            invoice.invoice_number = parsed_data.get('invoice_number')
            invoice.total_amount = parsed_data.get('total_amount')
            invoice.tax_amount = parsed_data.get('tax_amount')
            invoice.is_statement = parsed_data.get('is_statement', False)  # AI-detected statement flag
            invoice.raw_data = parsed_data

            # Check for duplicate invoice (same invoice_number + vendor_name, different record)
            if invoice.invoice_number and invoice.vendor_name:
                # Normalize vendor name for comparison (case-insensitive, trim whitespace)
                normalized_vendor = invoice.vendor_name.strip().upper()

                duplicate = db.query(HubInvoice).filter(
                    HubInvoice.id != invoice_id,
                    HubInvoice.invoice_number == invoice.invoice_number,
                    func.upper(func.trim(HubInvoice.vendor_name)) == normalized_vendor
                ).first()

                if duplicate:
                    # This is a duplicate - mark it and return
                    logger.warning(f"Duplicate invoice detected: {invoice.invoice_number} from {invoice.vendor_name} "
                                   f"(original ID: {duplicate.id}, duplicate ID: {invoice_id})")

                    # Delete any items we may have created
                    db.query(HubInvoiceItem).filter(HubInvoiceItem.invoice_id == invoice_id).delete()

                    # Delete this duplicate invoice
                    db.delete(invoice)
                    db.commit()

                    return {
                        "success": False,
                        "message": f"Duplicate invoice detected. Invoice #{invoice.invoice_number} from {invoice.vendor_name} already exists (ID: {duplicate.id}). This duplicate has been removed.",
                        "is_duplicate": True,
                        "original_invoice_id": duplicate.id
                    }

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

            # Check if this is a statement - skip item creation and mapping
            if invoice.is_statement:
                # Delete any existing items (in case this was re-parsed)
                existing_items = db.query(HubInvoiceItem).filter(HubInvoiceItem.invoice_id == invoice_id).count()
                if existing_items > 0:
                    db.query(HubInvoiceItem).filter(HubInvoiceItem.invoice_id == invoice_id).delete()
                    logger.info(f"Deleted {existing_items} items from invoice {invoice_id} (statement detected)")

                # Statements don't have items to map
                invoice.status = 'statement'
                db.commit()
                logger.info(f"Invoice {invoice_id} detected as statement - skipping item creation")

                return {
                    "success": True,
                    "message": f"Statement parsed successfully. No items to map.",
                    "invoice_id": invoice_id,
                    "confidence_score": confidence_score,
                    "is_statement": True,
                    "items_parsed": 0,
                    "vendor_matched": vendor is not None,
                    "vendor_name": parsed_data.get('vendor_name'),
                    "location_matched": location_matched,
                }

            # Create invoice items (only for actual invoices, not statements)
            unmapped_count = 0
            line_items = parsed_data.get('line_items', [])

            for item_data in line_items:
                quantity = float(item_data.get('quantity') or 0)
                unit_price = float(item_data.get('unit_price') or 0)
                line_total = float(item_data.get('line_total') or 0)

                # Fallback: If line_total is incorrect or missing, calculate it
                # Some AI parsers return unit_price as line_total by mistake
                calculated_total = quantity * unit_price

                # Use calculated total if:
                # 1. line_total is 0 or missing, OR
                # 2. line_total equals unit_price (common parsing error), OR
                # 3. line_total differs significantly from calculated (>$0.02 difference for rounding)
                if line_total == 0 or line_total == unit_price or abs(line_total - calculated_total) > 0.02:
                    line_total = calculated_total
                    logger.warning(f"Line total mismatch for '{item_data.get('description')}': "
                                 f"parsed=${item_data.get('line_total')}, calculated=${calculated_total:.2f}. Using calculated.")

                # Normalize description to title case for consistency
                raw_description = item_data.get('description') or 'Unknown'
                normalized_description = to_title_case(raw_description)

                # Parse pack_size - could be string like "6x5 LB", "Case - 12", "12/1 LT" or just a number
                pack_size_raw = item_data.get('pack_size')
                pack_size_int = None
                if pack_size_raw:
                    # Try to extract numeric pack size
                    import re
                    # Match patterns like: "12", "6x5", "Case - 12", "12/1", "6-pack"
                    match = re.search(r'(\d+)(?:\s*[-x/]\s*\d+)?', str(pack_size_raw))
                    if match:
                        pack_size_int = int(match.group(1))

                invoice_item = HubInvoiceItem(
                    invoice_id=invoice_id,
                    line_number=item_data.get('line_number'),
                    item_description=normalized_description,
                    item_code=item_data.get('item_code'),
                    quantity=quantity,
                    unit_of_measure=item_data.get('unit'),
                    pack_size=pack_size_int,
                    unit_price=unit_price,
                    total_amount=line_total,
                    is_mapped=False  # Will need manual mapping
                )
                db.add(invoice_item)
                unmapped_count += 1

            # Set invoice status to mapping
            invoice.status = 'mapping'
            db.commit()

            # Step 0: Fix UPC codes extracted as item codes
            # This detects long codes starting with 000 and corrects them using historical data
            upc_fix_stats = self._fix_upc_as_item_code(invoice_id, db)
            if upc_fix_stats.get('fixed', 0) > 0:
                logger.info(f"Fixed {upc_fix_stats['fixed']} UPC codes incorrectly parsed as item codes")

            # Step 1: Validate and correct OCR errors in item codes
            # This compares parsed codes against verified codes and fixes common OCR mistakes
            ocr_correction_stats = self._validate_and_correct_item_codes(invoice_id, db)
            if ocr_correction_stats.get('corrected', 0) > 0:
                logger.info(f"Corrected {ocr_correction_stats['corrected']} OCR errors in item codes")

            # Step 2: Normalize item descriptions based on item codes
            # This fixes OCR variations where the same item code has different parsed descriptions
            self._normalize_item_descriptions(invoice_id, db)

            # Step 3: Fix OCR errors using description matching
            # When codes don't match but descriptions are very similar, use inventory SKU
            desc_fix_stats = self._fix_ocr_by_description(invoice_id, db)
            if desc_fix_stats.get('fixed', 0) > 0:
                logger.info(f"Fixed {desc_fix_stats['fixed']} items by description matching")

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

            ocr_corrected = ocr_correction_stats.get('corrected', 0)
            upc_fixed = upc_fix_stats.get('fixed', 0)
            desc_fixed = desc_fix_stats.get('fixed', 0)
            return {
                "success": True,
                "message": f"Invoice parsed successfully with {items_count} items. Auto-mapped: {mapping_stats.get('mapped_count', 0)}, Unmapped: {mapping_stats.get('unmapped_count', 0)}, OCR corrected: {ocr_corrected}, UPC fixed: {upc_fixed}, Desc fixed: {desc_fixed}.",
                "invoice_id": invoice_id,
                "confidence_score": confidence_score,
                "items_parsed": items_count,
                "items_mapped": mapping_stats.get('mapped_count', 0),
                "items_unmapped": mapping_stats.get('unmapped_count', 0),
                "ocr_corrected": ocr_corrected,
                "ocr_corrections": ocr_correction_stats.get('corrections', []),
                "upc_fixed": upc_fixed,
                "upc_fixes": upc_fix_stats.get('fixes', []),
                "desc_fixed": desc_fixed,
                "desc_fixes": desc_fix_stats.get('fixes', []),
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

    def reparse_with_vendor_rules(self, invoice_id: int, db: Session) -> Dict:
        """
        Re-parse an invoice using vendor-specific parsing rules.

        This method:
        1. Gets the invoice and its matched vendor
        2. Looks up vendor-specific parsing rules
        3. Re-parses the PDF with those rules included in the AI prompt
        4. Updates the invoice items with the new parsed data

        Args:
            invoice_id: ID of the invoice to re-parse
            db: Database session

        Returns:
            Dict with success status and details
        """
        # Get invoice
        invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        if not invoice:
            return {"success": False, "message": "Invoice not found"}

        if not invoice.pdf_path:
            return {"success": False, "message": "Invoice has no PDF file"}

        if not invoice.vendor_id:
            return {"success": False, "message": "Invoice has no matched vendor. Match vendor first before using vendor rules."}

        # Get vendor parsing rules
        vendor_rules = self.get_vendor_parsing_rules(invoice.vendor_id, db)
        if not vendor_rules:
            return {"success": False, "message": f"No parsing rules found for vendor ID {invoice.vendor_id}. Create rules first in Settings > Vendor Parsing Rules."}

        # Log that we're using vendor rules
        logger.info(f"Re-parsing invoice {invoice_id} with vendor rules for vendor_id={invoice.vendor_id}")
        if vendor_rules.ai_instructions:
            logger.info(f"Using AI instructions: {vendor_rules.ai_instructions[:100]}...")

        # Delete existing items for re-parsing
        existing_count = db.query(HubInvoiceItem).filter(HubInvoiceItem.invoice_id == invoice_id).count()
        if existing_count > 0:
            db.query(HubInvoiceItem).filter(HubInvoiceItem.invoice_id == invoice_id).delete()
            logger.info(f"Deleted {existing_count} existing items for re-parse")

        # Update status
        invoice.status = 'mapping'
        db.commit()

        try:
            # Re-parse with vendor rules
            parse_result = self.parse_invoice_pdf(invoice.pdf_path, vendor_rules=vendor_rules)

            if not parse_result["success"]:
                invoice.status = 'pending'
                db.commit()
                return parse_result

            parsed_data = parse_result["data"]
            confidence_score = parse_result["confidence_score"]

            # Update invoice with new parsed data
            invoice.raw_data = parsed_data

            # Create new invoice items
            unmapped_count = 0
            line_items = parsed_data.get('line_items', [])

            for item_data in line_items:
                quantity = float(item_data.get('quantity') or 0)
                unit_price = float(item_data.get('unit_price') or 0)
                line_total = float(item_data.get('line_total') or 0)

                # Fallback: Calculate line_total if incorrect
                calculated_total = quantity * unit_price
                if line_total == 0 or line_total == unit_price or abs(line_total - calculated_total) > 0.02:
                    line_total = calculated_total

                # Normalize description
                raw_description = item_data.get('description') or 'Unknown'
                normalized_description = to_title_case(raw_description)

                # Parse pack_size
                pack_size_raw = item_data.get('pack_size')
                pack_size_int = None
                if pack_size_raw:
                    import re
                    match = re.search(r'(\d+)(?:\s*[-x/]\s*\d+)?', str(pack_size_raw))
                    if match:
                        pack_size_int = int(match.group(1))

                invoice_item = HubInvoiceItem(
                    invoice_id=invoice_id,
                    line_number=item_data.get('line_number'),
                    item_description=normalized_description,
                    item_code=item_data.get('item_code'),
                    quantity=quantity,
                    unit_of_measure=item_data.get('unit'),
                    pack_size=pack_size_int,
                    unit_price=unit_price,
                    total_amount=line_total,
                    is_mapped=False
                )
                db.add(invoice_item)
                unmapped_count += 1

            invoice.status = 'mapping'
            db.commit()

            # Run post-processing fixes
            upc_fix_stats = self._fix_upc_as_item_code(invoice_id, db)
            ocr_correction_stats = self._validate_and_correct_item_codes(invoice_id, db)
            self._normalize_item_descriptions(invoice_id, db)
            desc_fix_stats = self._fix_ocr_by_description(invoice_id, db)

            # Auto-map items
            mapping_stats = {'mapped_count': 0, 'unmapped_count': unmapped_count}
            try:
                from integration_hub.services.auto_mapper import get_auto_mapper
                mapper = get_auto_mapper(db)
                mapping_stats = mapper.map_invoice_items(invoice_id)
            except Exception as e:
                logger.error(f"Error auto-mapping items: {str(e)}")

            return {
                "success": True,
                "message": f"Invoice re-parsed with vendor rules. {len(line_items)} items, auto-mapped: {mapping_stats.get('mapped_count', 0)}",
                "invoice_id": invoice_id,
                "confidence_score": confidence_score,
                "items_parsed": len(line_items),
                "items_mapped": mapping_stats.get('mapped_count', 0),
                "items_unmapped": mapping_stats.get('unmapped_count', 0),
                "used_vendor_rules": True,
                "vendor_rule_id": vendor_rules.id,
            }

        except Exception as e:
            logger.error(f"Error in reparse_with_vendor_rules: {str(e)}", exc_info=True)
            invoice.status = 'pending'
            db.commit()
            return {
                "success": False,
                "message": f"Error re-parsing invoice: {str(e)}"
            }


def get_invoice_parser() -> InvoiceParser:
    """Get invoice parser instance"""
    return InvoiceParser()
