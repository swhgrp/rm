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

        # Add access token to params (Clover uses token query param, not Bearer header)
        if params is None:
            params = {}
        params['access_token'] = self.access_token

        logger.debug(f"Making Clover API request: {method} {url}")
        logger.debug(f"Token length: {len(self.access_token)}")
        logger.debug(f"Params: {params}")

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
            logger.error(f"Request URL: {e.request.url}")
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
            "expand": "lineItems,payments,discounts,refunds"  # Include all order details
        }

        # Add date filters if provided
        # Clover API doesn't support AND operator, so we can only filter by start OR end
        # When both dates are provided and the range is small (<=7 days), use end_date filter
        # to get older orders, then filter by start_date manually in calling code
        if start_date and end_date:
            # Calculate day difference
            day_diff = (end_date - start_date).days
            if day_diff <= 7:
                # Short date range - use end_date filter to get older orders
                end_ms = int(datetime.combine(end_date, datetime.max.time()).timestamp() * 1000)
                params["filter"] = f"createdTime<={end_ms}"
            else:
                # Long date range - use start_date filter
                start_ms = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
                params["filter"] = f"createdTime>={start_ms}"
        elif start_date:
            # Only start date provided
            start_ms = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
            params["filter"] = f"createdTime>={start_ms}"
        elif end_date:
            # Only end date provided
            end_ms = int(datetime.combine(end_date, datetime.max.time()).timestamp() * 1000)
            params["filter"] = f"createdTime<={end_ms}"

        return await self._make_request("GET", "orders", params=params)

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get a single order by ID"""
        return await self._make_request(
            "GET",
            f"orders/{order_id}",
            params={"expand": "lineItems"}
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

    async def get_payments(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """
        Get payments from Clover (actual completed sales)

        This is different from orders - payments represent actual money collected

        Args:
            start_date: Filter payments from this date
            end_date: Filter payments until this date
            limit: Maximum number of payments to return (capped at 1000 by Clover)

        Returns:
            Dictionary with 'elements' list of payments
        """
        # Clover API has a maximum limit of 1000
        limit = min(limit, 1000)

        params = {
            "limit": limit,
            "expand": "lineItems,order"  # Include line items and order info
        }

        # Add date filters if provided
        if start_date:
            start_ms = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
            params["filter"] = f"createdTime>={start_ms}"

        return await self._make_request("GET", "payments", params=params)

    async def test_connection(self) -> bool:
        """
        Test if API credentials are valid

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to get merchant properties - this is a simple endpoint that verifies auth
            url = f"{self.base_url}/v3/merchants/{self.merchant_id}"
            params = {'access_token': self.access_token}
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Clover connection test failed: {str(e)}")
            return False


def parse_clover_payment(clover_payment: Dict) -> Dict[str, Any]:
    """
    Parse Clover payment data into our sales schema format

    Payments represent actual completed transactions with real money collected,
    including tax, tips, and discounts already calculated by Clover.

    Args:
        clover_payment: Raw payment data from Clover API

    Returns:
        Parsed payment data ready for database insertion
    """
    # Convert Clover timestamp (milliseconds) to datetime
    payment_date = datetime.fromtimestamp(clover_payment.get("createdTime", 0) / 1000)

    # Parse amounts (Clover uses cents, convert to dollars)
    # Payment amount is the total actually collected
    amount = float(clover_payment.get("amount", 0)) / 100
    tax = float(clover_payment.get("taxAmount", 0)) / 100 if clover_payment.get("taxAmount") else 0
    tip = float(clover_payment.get("tipAmount", 0)) / 100 if clover_payment.get("tipAmount") else 0

    # Calculate subtotal (net sales = amount - tax - tip)
    subtotal = amount - tax - tip

    # Check if payment was successful
    result = clover_payment.get("result", "").upper()
    status = "completed" if result == "SUCCESS" else "failed"

    # Get order ID for reference
    order_id = None
    if clover_payment.get("order") and clover_payment["order"].get("id"):
        order_id = clover_payment["order"]["id"]

    parsed = {
        "pos_order_id": clover_payment["id"],  # Use payment ID as order ID
        "order_number": order_id[-8:] if order_id else clover_payment["id"][-8:],
        "order_date": payment_date,
        "subtotal": subtotal,
        "tax": tax,
        "tip": tip,
        "discount": 0,  # Discounts are already applied to the amount
        "total": amount,
        "customer_name": None,
        "status": status,
        "order_type": None,
        "raw_data": str(clover_payment),
        "synced_at": datetime.utcnow()
    }

    return parsed


def parse_clover_order(clover_order: Dict) -> Dict[str, Any]:
    """
    Parse Clover order data into our schema format

    Args:
        clover_order: Raw order data from Clover API

    Returns:
        Parsed order data ready for database insertion
    """
    # Convert Clover timestamp (milliseconds) to datetime
    # Use clientCreatedTime (when order was placed) which matches the accounting system
    order_date = datetime.fromtimestamp(clover_order.get("clientCreatedTime", clover_order.get("createdTime", 0)) / 1000)

    # Parse amounts (Clover uses cents, convert to dollars)
    # NOTE: Clover's order.total INCLUDES tax but NOT tip
    order_total = float(clover_order.get("total", 0)) / 100

    # Extract tax and tip from payments (only count once from first successful payment)
    # This matches the accounting system approach
    tax = 0
    tip = 0
    total_paid = 0

    if clover_order.get("payments") and clover_order["payments"].get("elements"):
        for payment in clover_order["payments"]["elements"]:
            # Only process successful payments
            if payment.get("result") == "SUCCESS":
                # Sum up all successful payments
                payment_amount = float(payment.get("amount", 0)) / 100
                total_paid += payment_amount

                # Get tax and tip from first payment only (they're order-level, not payment-level)
                if tax == 0:
                    tax = float(payment.get("taxAmount", 0) or 0) / 100
                if tip == 0:
                    tip = float(payment.get("tipAmount", 0) or 0) / 100

    # Use total_paid if available (actual amount paid), otherwise use order total
    total = total_paid if total_paid > 0 else order_total

    # Calculate subtotal using the accounting system's proven approach:
    # net_sales = order_total - tax (this is the NET amount after discounts but before tax)
    # This is what Clover reports as the actual sales amount
    subtotal = order_total - tax

    # Track discounts separately for reference (not used in subtotal calculation)
    # Discounts are already reflected in order_total
    discount = 0
    if clover_order.get("discounts") and clover_order["discounts"].get("elements"):
        for disc in clover_order["discounts"]["elements"]:
            discount += abs(float(disc.get("amount", 0)) / 100)  # Make positive for tracking

    # Parse order state
    state = clover_order.get("state", "").lower()

    # Check if order has refunds
    has_refunds = False
    if clover_order.get("refunds") and clover_order["refunds"].get("elements"):
        has_refunds = True
        # Mark as refunded if there are refunds
        status = "refunded"
    else:
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

        # Clover uses thousandths for quantities (unitQty: 1000 = 1 item, 500 = 0.5 items)
        unit_qty = float(item.get("unitQty", 1000)) / 1000  # Convert to actual quantity
        unit_price = float(item.get("price", 0)) / 100  # Convert cents to dollars

        parsed_item = {
            "pos_item_id": item.get("item", {}).get("id") if item.get("item") else None,
            "item_name": item.get("name", "Unknown Item"),
            "quantity": unit_qty,
            "unit_price": unit_price,
            "total_price": unit_price * unit_qty,
            "notes": item.get("note")
        }

        line_items.append(parsed_item)

    return line_items
