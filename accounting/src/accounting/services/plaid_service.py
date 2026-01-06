"""
Plaid Integration Service
Handles automated bank account syncing via Plaid API
"""
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

try:
    from plaid.api import plaid_api
    from plaid.model.products import Products
    from plaid.model.country_code import CountryCode
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.transactions_sync_request import TransactionsSyncRequest
    from plaid.model.accounts_get_request import AccountsGetRequest
    from plaid.configuration import Configuration
    from plaid.api_client import ApiClient
    import plaid
except ImportError:
    logger.warning("plaid-python library not installed. Plaid features will not be available.")
    plaid = None


class PlaidService:
    """Service for Plaid API integration"""

    def __init__(self):
        """Initialize Plaid client"""
        self.enabled = False
        self.client = None

        # Get Plaid credentials from environment
        client_id = os.getenv("PLAID_CLIENT_ID")
        secret = os.getenv("PLAID_SECRET")
        env = os.getenv("PLAID_ENV", "sandbox")  # sandbox, development, production

        if not client_id or not secret:
            logger.warning("Plaid credentials not configured. Set PLAID_CLIENT_ID and PLAID_SECRET environment variables.")
            return

        if plaid is None:
            logger.warning("plaid-python library not available")
            return

        try:
            # Configure Plaid client
            configuration = Configuration(
                host=self._get_plaid_host(env),
                api_key={
                    'clientId': client_id,
                    'secret': secret,
                }
            )

            api_client = ApiClient(configuration)
            self.client = plaid_api.PlaidApi(api_client)
            self.enabled = True
            logger.info(f"Plaid service initialized in {env} environment")

        except Exception as e:
            logger.error(f"Failed to initialize Plaid client: {str(e)}")

    @staticmethod
    def _get_plaid_host(env: str) -> str:
        """Get Plaid API host based on environment"""
        hosts = {
            "sandbox": "https://sandbox.plaid.com",
            "development": "https://development.plaid.com",
            "production": "https://production.plaid.com"
        }
        return hosts.get(env, "https://sandbox.plaid.com")

    def is_enabled(self) -> bool:
        """Check if Plaid service is enabled"""
        return self.enabled and self.client is not None

    def create_link_token(self, user_id: int, user_name: str) -> Optional[Dict]:
        """
        Create a link token for Plaid Link initialization

        Args:
            user_id: User ID from our system
            user_name: User's name

        Returns:
            Dict with link_token and expiration
        """
        if not self.is_enabled():
            return None

        try:
            request_params = {
                "user": LinkTokenCreateRequestUser(client_user_id=str(user_id)),
                "client_name": "SW Hospitality Group",
                "products": [Products("transactions")],
                "country_codes": [CountryCode("US")],
                "language": "en"
            }

            request = LinkTokenCreateRequest(**request_params)

            response = self.client.link_token_create(request)
            result = response.to_dict()

            return {
                "link_token": result["link_token"],
                "expiration": result["expiration"]
            }

        except Exception as e:
            logger.error(f"Error creating Plaid link token: {str(e)}")
            return None

    def exchange_public_token(self, public_token: str) -> Optional[Dict]:
        """
        Exchange public token for access token

        Args:
            public_token: Public token from Plaid Link

        Returns:
            Dict with access_token and item_id
        """
        if not self.is_enabled():
            return None

        try:
            request = ItemPublicTokenExchangeRequest(public_token=public_token)
            response = self.client.item_public_token_exchange(request)
            result = response.to_dict()

            return {
                "access_token": result["access_token"],
                "item_id": result["item_id"]
            }

        except Exception as e:
            logger.error(f"Error exchanging public token: {str(e)}")
            return None

    def get_accounts(self, access_token: str) -> List[Dict]:
        """
        Get account information from Plaid

        Args:
            access_token: Plaid access token

        Returns:
            List of account dictionaries
        """
        if not self.is_enabled():
            return []

        try:
            request = AccountsGetRequest(access_token=access_token)
            response = self.client.accounts_get(request)
            result = response.to_dict()

            accounts = []
            for account in result.get("accounts", []):
                accounts.append({
                    "account_id": account["account_id"],
                    "name": account["name"],
                    "mask": account.get("mask"),
                    "type": account["type"],
                    "subtype": account.get("subtype"),
                    "current_balance": Decimal(str(account["balances"]["current"])) if account["balances"].get("current") else None,
                    "available_balance": Decimal(str(account["balances"]["available"])) if account["balances"].get("available") else None,
                })

            return accounts

        except Exception as e:
            logger.error(f"Error fetching Plaid accounts: {str(e)}")
            return []

    def sync_transactions(
        self,
        access_token: str,
        plaid_account_id: str,
        cursor: Optional[str] = None
    ) -> Dict:
        """
        Sync transactions from Plaid

        Args:
            access_token: Plaid access token
            plaid_account_id: Plaid account ID
            cursor: Optional cursor for pagination

        Returns:
            Dict with transactions and sync info
        """
        if not self.is_enabled():
            return {
                "success": False,
                "error": "Plaid service not enabled",
                "transactions": []
            }

        try:
            # Build request - only include cursor if it's not None
            if cursor:
                request = TransactionsSyncRequest(
                    access_token=access_token,
                    cursor=cursor
                )
            else:
                request = TransactionsSyncRequest(
                    access_token=access_token
                )

            response = self.client.transactions_sync(request)
            result = response.to_dict()

            # Filter transactions for specific account
            all_transactions = result.get("added", [])
            account_transactions = [
                t for t in all_transactions
                if t.get("account_id") == plaid_account_id
            ]

            # Parse transactions
            transactions = []
            for txn in account_transactions:
                # Handle date - Plaid may return date object or string
                txn_date = txn["date"]
                if isinstance(txn_date, str):
                    txn_date = datetime.strptime(txn_date, "%Y-%m-%d").date()
                elif isinstance(txn_date, datetime):
                    txn_date = txn_date.date()
                # else: already a date object

                # Handle authorized_date
                auth_date = txn.get("authorized_date")
                if auth_date:
                    if isinstance(auth_date, str):
                        auth_date = datetime.strptime(auth_date, "%Y-%m-%d").date()
                    elif isinstance(auth_date, datetime):
                        auth_date = auth_date.date()
                    # else: already a date object

                transaction = {
                    "transaction_date": txn_date,
                    "post_date": auth_date,
                    "description": txn.get("merchant_name") or txn.get("name", ""),
                    "payee": txn.get("merchant_name"),
                    "amount": Decimal(str(txn["amount"])) * -1,  # Plaid amounts are positive for debits
                    "transaction_type": self._map_plaid_transaction_type(txn),
                    "check_number": txn.get("check_number"),
                    "reference_number": txn.get("transaction_id"),
                    "category": ", ".join(txn.get("category", [])) if txn.get("category") else None,
                    "memo": txn.get("name"),
                    "plaid_transaction_id": txn["transaction_id"],
                    "plaid_category": txn.get("category"),
                    "plaid_pending": txn.get("pending", False),
                }
                transactions.append(transaction)

            return {
                "success": True,
                "transactions": transactions,
                "added": len(transactions),
                "modified": len(result.get("modified", [])),
                "removed": len(result.get("removed", [])),
                "next_cursor": result.get("next_cursor"),
                "has_more": result.get("has_more", False)
            }

        except Exception as e:
            logger.error(f"Error syncing Plaid transactions: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "transactions": []
            }

    @staticmethod
    def _map_plaid_transaction_type(transaction: Dict) -> str:
        """Map Plaid transaction to our transaction type"""
        # Check payment channel
        channel = transaction.get("payment_channel", "").lower()

        if channel == "online":
            return "online"
        elif channel == "in store":
            return "pos"

        # Check transaction type
        txn_type = transaction.get("transaction_type", "").lower()

        type_mapping = {
            "special": "transfer",
            "place": "pos",
            "digital": "online",
        }

        if txn_type in type_mapping:
            return type_mapping[txn_type]

        # Check category
        categories = transaction.get("category", [])
        if categories:
            first_category = categories[0].lower()
            if "transfer" in first_category:
                return "transfer"
            elif "payment" in first_category:
                return "payment"
            elif "atm" in first_category:
                return "atm"

        # Default based on amount
        amount = Decimal(str(transaction.get("amount", 0)))
        return "debit" if amount > 0 else "credit"

    def get_balance(self, access_token: str, plaid_account_id: str) -> Optional[Dict]:
        """
        Get current account balance from Plaid

        Args:
            access_token: Plaid access token
            plaid_account_id: Plaid account ID

        Returns:
            Dict with balance information
        """
        accounts = self.get_accounts(access_token)

        for account in accounts:
            if account["account_id"] == plaid_account_id:
                return {
                    "current_balance": account["current_balance"],
                    "available_balance": account["available_balance"]
                }

        return None

    def remove_item(self, access_token: str) -> bool:
        """
        Remove Plaid item (disconnect bank account)

        Args:
            access_token: Plaid access token

        Returns:
            True if successful
        """
        if not self.is_enabled():
            return False

        try:
            from plaid.model.item_remove_request import ItemRemoveRequest
            request = ItemRemoveRequest(access_token=access_token)
            self.client.item_remove(request)
            return True

        except Exception as e:
            logger.error(f"Error removing Plaid item: {str(e)}")
            return False


# Global singleton instance
_plaid_service = None


def get_plaid_service() -> PlaidService:
    """Get or create Plaid service singleton"""
    global _plaid_service
    if _plaid_service is None:
        _plaid_service = PlaidService()
    return _plaid_service
