"""
Clover POS API Client
Handles communication with Clover REST API for orders and sales data
"""

import httpx
from typing import List, Dict, Optional, Any
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)


class CloverAPIClient:
    """Client for interacting with Clover REST API"""

    def __init__(
        self,
        merchant_id: str,
        access_token: str,
        environment: str = "production"
    ):
        """
        Initialize Clover API client

        Args:
            merchant_id: Clover merchant ID
            access_token: OAuth access token
            environment: "sandbox" or "production"
        """
        self.merchant_id = merchant_id
        self.access_token = access_token

        # Set base URL based on environment
        if environment == "sandbox":
            self.base_url = "https://apisandbox.dev.clover.com"
        else:
            self.base_url = "https://api.clover.com"  # North America

        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to Clover API"""
        url = f"{self.base_url}/v3/merchants/{self.merchant_id}/{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    params=params,
                    json=json_data
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Clover API error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Clover API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error making Clover API request: {str(e)}")
            raise

    async def get_orders(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get orders from Clover

        Args:
            start_date: Filter orders from this date
            end_date: Filter orders until this date
            limit: Maximum number of orders to return
            offset: Pagination offset

        Returns:
            Dictionary with 'elements' list of orders
        """
        params = {
            "limit": limit,
            "offset": offset,
            "expand": "lineItems"  # Include line items in response
        }

        # Add date filters if provided
        if start_date:
            # Clover uses milliseconds since epoch
            start_ms = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
            params["filter"] = f"createdTime>={start_ms}"

        if end_date:
            end_ms = int(datetime.combine(end_date, datetime.max.time()).timestamp() * 1000)
            if "filter" in params:
                params["filter"] += f" AND createdTime<={end_ms}"
            else:
                params["filter"] = f"createdTime<={end_ms}"

        return await self._make_request("GET", "orders", params=params)

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get a single order by ID"""
        return await self._make_request(
            "GET",
            f"orders/{order_id}",
            params={"expand": "lineItems,payments"}
        )

    async def get_order_line_items(self, order_id: str) -> Dict[str, Any]:
        """Get line items for an order"""
        return await self._make_request("GET", f"orders/{order_id}/line_items")

    async def get_items(self, limit: int = 100) -> Dict[str, Any]:
        """
        Get inventory items (menu items) from Clover

        Returns:
            Dictionary with 'elements' list of items
        """
        return await self._make_request(
            "GET",
            "items",
            params={"limit": limit}
        )

    async def get_item(self, item_id: str) -> Dict[str, Any]:
        """Get a single inventory item by ID"""
        return await self._make_request("GET", f"items/{item_id}")

    async def test_connection(self) -> bool:
        """
        Test if API credentials are valid

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to get merchant properties - this is a simple endpoint that verifies auth
            url = f"{self.base_url}/v3/merchants/{self.merchant_id}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Clover connection test failed: {str(e)}")
            return False


def parse_clover_order(clover_order: Dict) -> Dict[str, Any]:
    """
    Parse Clover order data into our schema format

    Args:
        clover_order: Raw order data from Clover API

    Returns:
        Parsed order data ready for database insertion
    """
    # Convert Clover timestamp (milliseconds) to datetime
    order_date = datetime.fromtimestamp(clover_order.get("createdTime", 0) / 1000)

    # Parse amounts (Clover uses cents, convert to dollars)
    total = float(clover_order.get("total", 0)) / 100
    tax = float(clover_order.get("taxAmount", 0)) / 100 if clover_order.get("taxAmount") else 0
    tip = float(clover_order.get("tipAmount", 0)) / 100 if clover_order.get("tipAmount") else 0
    discount = float(clover_order.get("discountAmount", 0)) / 100 if clover_order.get("discountAmount") else 0

    # Calculate subtotal
    subtotal = total - tax - tip + discount

    # Parse order state
    state = clover_order.get("state", "").lower()
    status = "completed" if state == "locked" else state

    # Customer info
    customer_name = None
    if clover_order.get("customers") and clover_order["customers"].get("elements"):
        customer = clover_order["customers"]["elements"][0]
        first_name = customer.get("firstName", "")
        last_name = customer.get("lastName", "")
        customer_name = f"{first_name} {last_name}".strip() or None

    parsed = {
        "pos_order_id": clover_order["id"],
        "order_number": clover_order.get("manualTransaction") or clover_order.get("id")[-8:],
        "order_date": order_date,
        "subtotal": subtotal,
        "tax": tax,
        "tip": tip,
        "discount": discount,
        "total": total,
        "customer_name": customer_name,
        "status": status,
        "order_type": clover_order.get("orderType", {}).get("label"),
        "raw_data": str(clover_order),  # Store for debugging
        "synced_at": datetime.utcnow()
    }

    return parsed


def parse_clover_line_items(clover_order: Dict) -> List[Dict[str, Any]]:
    """
    Parse Clover order line items

    Args:
        clover_order: Raw order data from Clover API with lineItems

    Returns:
        List of parsed line item data
    """
    line_items = []

    if not clover_order.get("lineItems") or not clover_order["lineItems"].get("elements"):
        return line_items

    for item in clover_order["lineItems"]["elements"]:
        # Skip if item was removed/deleted
        if item.get("deleted"):
            continue

        parsed_item = {
            "pos_item_id": item.get("item", {}).get("id") if item.get("item") else None,
            "item_name": item.get("name", "Unknown Item"),
            "quantity": float(item.get("unitQty", 1)) / 1000,  # Clover uses thousandths
            "unit_price": float(item.get("price", 0)) / 100,  # Convert cents to dollars
            "total_price": (float(item.get("price", 0)) / 100) * (float(item.get("unitQty", 1)) / 1000),
            "notes": item.get("note")
        }

        line_items.append(parsed_item)

    return line_items
