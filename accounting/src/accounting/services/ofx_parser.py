"""
OFX/QFX File Parser for Bank Statements
Supports Chase and other banks using OFX format
"""
import io
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date
from decimal import Decimal
import logging

try:
    from ofxparse import OfxParser
    from ofxparse.ofxparse import Account, Transaction
except ImportError:
    raise ImportError("ofxparse library not installed. Install with: pip install ofxparse")

logger = logging.getLogger(__name__)


class OFXParserService:
    """Service for parsing OFX/QFX bank statement files"""

    @staticmethod
    def parse_file(file_content: bytes) -> Dict:
        """
        Parse OFX/QFX file and extract account and transaction data

        Args:
            file_content: Raw bytes content of the OFX/QFX file

        Returns:
            Dict containing account info and transactions
        """
        try:
            # Parse OFX content
            ofx = OfxParser.parse(io.BytesIO(file_content))

            # Extract account information
            account_info = OFXParserService._extract_account_info(ofx)

            # Extract transactions from all accounts
            all_transactions = []
            for account in ofx.accounts:
                transactions = OFXParserService._extract_transactions(account)
                all_transactions.extend(transactions)

            return {
                "success": True,
                "account_info": account_info,
                "transactions": all_transactions,
                "transaction_count": len(all_transactions),
                "errors": []
            }

        except Exception as e:
            logger.error(f"Error parsing OFX file: {str(e)}")
            return {
                "success": False,
                "account_info": None,
                "transactions": [],
                "transaction_count": 0,
                "errors": [f"Failed to parse OFX file: {str(e)}"]
            }

    @staticmethod
    def _extract_account_info(ofx) -> Dict:
        """Extract account information from OFX data"""
        if not ofx.accounts:
            return {}

        # Use first account for account info
        account = ofx.accounts[0]

        info = {
            "account_number": getattr(account, 'number', None),
            "account_type": getattr(account, 'account_type', None),
            "routing_number": getattr(account, 'routing_number', None),
            "institution": getattr(account.institution, 'organization', None) if hasattr(account, 'institution') else None,
        }

        # Extract statement info if available
        statement = getattr(account, 'statement', None)
        if statement:
            info.update({
                "statement_start_date": OFXParserService._to_date(getattr(statement, 'start_date', None)),
                "statement_end_date": OFXParserService._to_date(getattr(statement, 'end_date', None)),
                "beginning_balance": OFXParserService._to_decimal(getattr(statement, 'balance', None)),
                "ending_balance": OFXParserService._to_decimal(getattr(statement, 'available_balance', None)),
            })

        return info

    @staticmethod
    def _extract_transactions(account: Account) -> List[Dict]:
        """Extract transactions from an OFX account"""
        transactions = []

        statement = getattr(account, 'statement', None)
        if not statement:
            return transactions

        for txn in statement.transactions:
            transaction = {
                "transaction_date": OFXParserService._to_date(txn.date),
                "post_date": OFXParserService._to_date(getattr(txn, 'date', None)),
                "description": getattr(txn, 'payee', '') or getattr(txn, 'memo', ''),
                "payee": OFXParserService._extract_payee(txn),
                "amount": OFXParserService._to_decimal(txn.amount),
                "transaction_type": OFXParserService._determine_transaction_type(txn),
                "check_number": getattr(txn, 'checknum', None),
                "reference_number": getattr(txn, 'id', None),
                "memo": getattr(txn, 'memo', None),
                "category": None,  # Will be filled by auto-categorization
            }
            transactions.append(transaction)

        return transactions

    @staticmethod
    def _extract_payee(txn: Transaction) -> Optional[str]:
        """Extract payee from transaction"""
        # Try payee field first
        payee = getattr(txn, 'payee', None)
        if payee and payee.strip():
            return payee.strip()

        # Fall back to memo if no payee
        memo = getattr(txn, 'memo', None)
        if memo:
            # Clean up common bank formatting
            cleaned = memo.replace('*', '').strip()
            return cleaned if cleaned else None

        return None

    @staticmethod
    def _determine_transaction_type(txn: Transaction) -> str:
        """Determine transaction type from OFX transaction"""
        amount = OFXParserService._to_decimal(txn.amount)
        txn_type = getattr(txn, 'type', '').upper()

        # Map OFX transaction types
        type_mapping = {
            'CHECK': 'check',
            'DEBIT': 'debit',
            'CREDIT': 'credit',
            'DEP': 'deposit',
            'ATM': 'atm',
            'POS': 'pos',
            'XFER': 'transfer',
            'PAYMENT': 'payment',
            'CASH': 'withdrawal',
            'DIRECTDEP': 'direct_deposit',
            'DIRECTDEBIT': 'direct_debit',
            'FEE': 'fee',
            'SRVCHG': 'service_charge',
            'INT': 'interest',
        }

        mapped_type = type_mapping.get(txn_type)
        if mapped_type:
            return mapped_type

        # Fallback: use amount sign
        if amount < 0:
            return 'debit'
        else:
            return 'credit'

    @staticmethod
    def _to_date(value) -> Optional[date]:
        """Convert value to date"""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return None

    @staticmethod
    def _to_decimal(value) -> Decimal:
        """Convert value to Decimal"""
        if value is None:
            return Decimal("0.00")
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            try:
                return Decimal(value)
            except:
                return Decimal("0.00")
        return Decimal("0.00")

    @staticmethod
    def validate_file(file_content: bytes) -> Tuple[bool, List[str]]:
        """
        Validate if file is a valid OFX/QFX file

        Returns:
            Tuple of (is_valid, errors)
        """
        errors = []

        try:
            # Try to parse the file
            ofx = OfxParser.parse(io.BytesIO(file_content))

            # Check if we have accounts
            if not ofx.accounts:
                errors.append("No accounts found in OFX file")

            # Check if we have transactions
            total_transactions = sum(
                len(getattr(account.statement, 'transactions', []))
                for account in ofx.accounts
                if hasattr(account, 'statement')
            )

            if total_transactions == 0:
                errors.append("No transactions found in OFX file")

            return (len(errors) == 0, errors)

        except Exception as e:
            errors.append(f"Invalid OFX file format: {str(e)}")
            return (False, errors)

    @staticmethod
    def get_file_summary(file_content: bytes) -> Dict:
        """
        Get a summary of the OFX file without full parsing

        Returns:
            Dict with file summary info
        """
        try:
            ofx = OfxParser.parse(io.BytesIO(file_content))

            total_transactions = 0
            date_range = {"start": None, "end": None}

            for account in ofx.accounts:
                if hasattr(account, 'statement') and account.statement:
                    stmt = account.statement
                    total_transactions += len(stmt.transactions)

                    if stmt.start_date:
                        start = stmt.start_date.date() if isinstance(stmt.start_date, datetime) else stmt.start_date
                        if date_range["start"] is None or start < date_range["start"]:
                            date_range["start"] = start

                    if stmt.end_date:
                        end = stmt.end_date.date() if isinstance(stmt.end_date, datetime) else stmt.end_date
                        if date_range["end"] is None or end > date_range["end"]:
                            date_range["end"] = end

            return {
                "success": True,
                "account_count": len(ofx.accounts),
                "transaction_count": total_transactions,
                "date_range": date_range,
                "institution": ofx.accounts[0].institution.organization if ofx.accounts and hasattr(ofx.accounts[0], 'institution') else None
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
