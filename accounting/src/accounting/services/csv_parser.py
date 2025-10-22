"""
CSV File Parser for Bank Statements
Supports multiple bank CSV formats with auto-detection
"""
import io
import csv
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date
from decimal import Decimal
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class CSVParserService:
    """Service for parsing CSV bank statement files"""

    # Common CSV formats from different banks
    BANK_FORMATS = {
        "chase": {
            "name": "Chase Bank",
            "columns": ["Details", "Posting Date", "Description", "Amount", "Type", "Balance", "Check or Slip #"],
            "date_field": "Posting Date",
            "description_field": "Description",
            "amount_field": "Amount",
            "type_field": "Type",
            "check_field": "Check or Slip #",
            "date_format": "%m/%d/%Y"
        },
        "chase_credit": {
            "name": "Chase Credit Card",
            "columns": ["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount", "Memo"],
            "date_field": "Transaction Date",
            "post_date_field": "Post Date",
            "description_field": "Description",
            "amount_field": "Amount",
            "type_field": "Type",
            "category_field": "Category",
            "memo_field": "Memo",
            "date_format": "%m/%d/%Y"
        },
        "bank_of_america": {
            "name": "Bank of America",
            "columns": ["Date", "Description", "Amount", "Running Bal."],
            "date_field": "Date",
            "description_field": "Description",
            "amount_field": "Amount",
            "date_format": "%m/%d/%Y"
        },
        "wells_fargo": {
            "name": "Wells Fargo",
            "columns": ["Date", "Amount", "Star", "Check Number", "Description"],
            "date_field": "Date",
            "description_field": "Description",
            "amount_field": "Amount",
            "check_field": "Check Number",
            "date_format": "%m/%d/%Y"
        },
        "generic": {
            "name": "Generic CSV",
            "columns": ["date", "description", "amount"],
            "date_field": "date",
            "description_field": "description",
            "amount_field": "amount",
            "date_format": "%Y-%m-%d"
        }
    }

    @staticmethod
    def parse_file(file_content: bytes, bank_format: Optional[str] = None) -> Dict:
        """
        Parse CSV file and extract transaction data

        Args:
            file_content: Raw bytes content of the CSV file
            bank_format: Optional bank format identifier (auto-detect if None)

        Returns:
            Dict containing transactions and metadata
        """
        try:
            # Convert bytes to string
            content_str = file_content.decode('utf-8-sig')  # utf-8-sig removes BOM if present

            # Try pandas for robust CSV parsing
            df = pd.read_csv(io.StringIO(content_str))

            # Auto-detect format if not provided
            if bank_format is None:
                bank_format = CSVParserService._detect_format(df)

            format_spec = CSVParserService.BANK_FORMATS.get(bank_format, CSVParserService.BANK_FORMATS["generic"])

            # Parse transactions
            transactions = CSVParserService._parse_transactions(df, format_spec)

            # Calculate date range
            date_range = CSVParserService._get_date_range(transactions)

            return {
                "success": True,
                "bank_format": bank_format,
                "format_name": format_spec["name"],
                "transactions": transactions,
                "transaction_count": len(transactions),
                "date_range": date_range,
                "errors": []
            }

        except Exception as e:
            logger.error(f"Error parsing CSV file: {str(e)}")
            return {
                "success": False,
                "bank_format": None,
                "format_name": None,
                "transactions": [],
                "transaction_count": 0,
                "date_range": {"start": None, "end": None},
                "errors": [f"Failed to parse CSV file: {str(e)}"]
            }

    @staticmethod
    def _detect_format(df: pd.DataFrame) -> str:
        """Auto-detect CSV format based on column headers"""
        columns = [col.strip() for col in df.columns]
        columns_lower = [col.lower() for col in columns]

        # Check Chase format
        if "Posting Date" in columns or "posting date" in columns_lower:
            if "Check or Slip #" in columns:
                return "chase"

        # Check Chase Credit Card format
        if "Transaction Date" in columns and "Post Date" in columns:
            return "chase_credit"

        # Check Bank of America format
        if "Running Bal." in columns or "running bal." in columns_lower:
            return "bank_of_america"

        # Check Wells Fargo format
        if "Star" in columns or any("check number" in col for col in columns_lower):
            return "wells_fargo"

        # Default to generic
        return "generic"

    @staticmethod
    def _parse_transactions(df: pd.DataFrame, format_spec: Dict) -> List[Dict]:
        """Parse transactions from DataFrame using format specification"""
        transactions = []

        # Map column names (case-insensitive)
        column_map = {}
        for col in df.columns:
            col_lower = col.strip().lower()
            for key, value in format_spec.items():
                if isinstance(value, str) and value.lower() == col or value.lower() == col_lower:
                    column_map[key] = col

        date_field = column_map.get("date_field", format_spec.get("date_field"))
        description_field = column_map.get("description_field", format_spec.get("description_field"))
        amount_field = column_map.get("amount_field", format_spec.get("amount_field"))

        for _, row in df.iterrows():
            try:
                # Skip empty rows
                if pd.isna(row.get(date_field)) and pd.isna(row.get(amount_field)):
                    continue

                # Parse transaction date
                trans_date = CSVParserService._parse_date(
                    row.get(date_field),
                    format_spec.get("date_format", "%Y-%m-%d")
                )

                # Parse post date if available
                post_date_field = column_map.get("post_date_field", format_spec.get("post_date_field"))
                post_date = None
                if post_date_field and post_date_field in row:
                    post_date = CSVParserService._parse_date(
                        row.get(post_date_field),
                        format_spec.get("date_format", "%Y-%m-%d")
                    )

                # Parse amount
                amount = CSVParserService._parse_amount(row.get(amount_field))

                # Extract description and payee
                description = str(row.get(description_field, "")).strip()
                payee = CSVParserService._extract_payee(description)

                # Get transaction type
                type_field = column_map.get("type_field", format_spec.get("type_field"))
                trans_type = CSVParserService._determine_type(
                    row.get(type_field) if type_field else None,
                    amount
                )

                # Get check number
                check_field = column_map.get("check_field", format_spec.get("check_field"))
                check_number = str(row.get(check_field, "")).strip() if check_field else None
                if check_number and check_number.lower() in ["", "nan", "none"]:
                    check_number = None

                # Get category and memo
                category_field = column_map.get("category_field", format_spec.get("category_field"))
                memo_field = column_map.get("memo_field", format_spec.get("memo_field"))

                transaction = {
                    "transaction_date": trans_date,
                    "post_date": post_date,
                    "description": description,
                    "payee": payee,
                    "amount": amount,
                    "transaction_type": trans_type,
                    "check_number": check_number,
                    "reference_number": None,
                    "category": str(row.get(category_field, "")).strip() if category_field else None,
                    "memo": str(row.get(memo_field, "")).strip() if memo_field else None,
                }

                transactions.append(transaction)

            except Exception as e:
                logger.warning(f"Error parsing row: {str(e)}")
                continue

        return transactions

    @staticmethod
    def _parse_date(date_str, date_format: str = "%Y-%m-%d") -> Optional[date]:
        """Parse date string to date object"""
        if pd.isna(date_str):
            return None

        date_str = str(date_str).strip()

        # Try specified format first
        try:
            return datetime.strptime(date_str, date_format).date()
        except:
            pass

        # Try common formats
        common_formats = [
            "%m/%d/%Y",
            "%Y-%m-%d",
            "%m/%d/%y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%b %d, %Y",
            "%B %d, %Y",
        ]

        for fmt in common_formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except:
                continue

        logger.warning(f"Could not parse date: {date_str}")
        return None

    @staticmethod
    def _parse_amount(amount_str) -> Decimal:
        """Parse amount string to Decimal"""
        if pd.isna(amount_str):
            return Decimal("0.00")

        # Convert to string and clean
        amount_str = str(amount_str).strip()

        # Remove currency symbols and commas
        amount_str = amount_str.replace('$', '').replace(',', '').replace(' ', '')

        # Handle parentheses for negative amounts (accounting format)
        if amount_str.startswith('(') and amount_str.endswith(')'):
            amount_str = '-' + amount_str[1:-1]

        try:
            return Decimal(amount_str)
        except:
            logger.warning(f"Could not parse amount: {amount_str}")
            return Decimal("0.00")

    @staticmethod
    def _extract_payee(description: str) -> Optional[str]:
        """Extract payee from description"""
        if not description:
            return None

        # Clean up common patterns
        cleaned = description.strip()

        # Remove common prefixes
        prefixes = ['DEBIT CARD PURCHASE - ', 'ELECTRONIC WITHDRAWAL - ', 'ACH ', 'CHECKCARD ']
        for prefix in prefixes:
            if cleaned.upper().startswith(prefix.upper()):
                cleaned = cleaned[len(prefix):]

        # Take first part before location/date info
        parts = cleaned.split(' - ')
        if parts:
            return parts[0].strip()

        return cleaned

    @staticmethod
    def _determine_type(type_str: Optional[str], amount: Decimal) -> str:
        """Determine transaction type"""
        if type_str:
            type_upper = str(type_str).upper().strip()

            type_mapping = {
                'DEBIT': 'debit',
                'CREDIT': 'credit',
                'CHECK': 'check',
                'ATM': 'atm',
                'DEPOSIT': 'deposit',
                'WITHDRAWAL': 'withdrawal',
                'TRANSFER': 'transfer',
                'FEE': 'fee',
                'INTEREST': 'interest',
                'PAYMENT': 'payment',
                'PURCHASE': 'purchase',
            }

            for key, value in type_mapping.items():
                if key in type_upper:
                    return value

        # Fallback to amount sign
        return 'debit' if amount < 0 else 'credit'

    @staticmethod
    def _get_date_range(transactions: List[Dict]) -> Dict:
        """Get date range from transactions"""
        dates = [t["transaction_date"] for t in transactions if t.get("transaction_date")]

        if not dates:
            return {"start": None, "end": None}

        return {
            "start": min(dates),
            "end": max(dates)
        }

    @staticmethod
    def validate_file(file_content: bytes) -> Tuple[bool, List[str]]:
        """
        Validate if file is a valid CSV file

        Returns:
            Tuple of (is_valid, errors)
        """
        errors = []

        try:
            content_str = file_content.decode('utf-8-sig')
            df = pd.read_csv(io.StringIO(content_str))

            # Check if we have data
            if df.empty:
                errors.append("CSV file is empty")

            # Check if we have minimum required columns
            if len(df.columns) < 2:
                errors.append("CSV file must have at least 2 columns")

            return (len(errors) == 0, errors)

        except Exception as e:
            errors.append(f"Invalid CSV file: {str(e)}")
            return (False, errors)

    @staticmethod
    def get_file_summary(file_content: bytes) -> Dict:
        """Get summary of CSV file"""
        try:
            content_str = file_content.decode('utf-8-sig')
            df = pd.read_csv(io.StringIO(content_str))

            # Auto-detect format
            bank_format = CSVParserService._detect_format(df)
            format_spec = CSVParserService.BANK_FORMATS.get(bank_format, CSVParserService.BANK_FORMATS["generic"])

            return {
                "success": True,
                "row_count": len(df),
                "column_count": len(df.columns),
                "columns": list(df.columns),
                "detected_format": bank_format,
                "format_name": format_spec["name"]
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def get_supported_formats() -> List[Dict]:
        """Get list of supported bank formats"""
        return [
            {
                "id": key,
                "name": value["name"],
                "columns": value.get("columns", [])
            }
            for key, value in CSVParserService.BANK_FORMATS.items()
        ]
