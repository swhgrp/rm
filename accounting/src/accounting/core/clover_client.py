"""
Clover POS API Client
Handles communication with Clover REST API for orders and sales data
"""

import httpx
from typing import List, Dict, Optional, Any
from datetime import datetime, date, timedelta, timezone
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
            "expand": "lineItems.item.categories,lineItems.item.priceType,lineItems.discounts,lineItems.modifications,payments.cardTransaction,payments.tender,discounts,refunds"  # Include all order details with payment card data, discounts, modifications, and priceType
        }

        # Add date filters if provided
        # Clover uses millisecond timestamps for filtering
        # Clover API supports multiple filters using repeated &filter= params
        filters = []
        if start_date:
            # Use clientCreatedTime which is when order was placed at the POS device
            start_ms = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
            filters.append(f"clientCreatedTime>={start_ms}")
        if end_date:
            end_ms = int(datetime.combine(end_date, datetime.max.time()).timestamp() * 1000)
            filters.append(f"clientCreatedTime<={end_ms}")

        if filters:
            params["filter"] = filters[0]

        # Make request - if multiple filters, we need to add them as separate query params
        if len(filters) > 1:
            query_parts = [f"{k}={v}" for k, v in params.items() if k != "filter"]
            for f in filters:
                query_parts.append(f"filter={f}")
            query_string = "&".join(query_parts)
            return await self._make_request("GET", f"orders?{query_string}", params=None)

        return await self._make_request("GET", "orders", params=params)

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get a single order by ID with full details"""
        return await self._make_request(
            "GET",
            f"orders/{order_id}",
            params={"expand": "lineItems.item.categories,lineItems.item.priceType,lineItems.discounts,lineItems.modifications,payments.cardTransaction,payments.tender,discounts,refunds"}
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

    async def get_categories(self, limit: int = 100) -> Dict[str, Any]:
        """
        Get item categories from Clover

        Returns:
            Dictionary with 'elements' list of categories
        """
        return await self._make_request(
            "GET",
            "categories",
            params={"limit": limit}
        )

    async def get_category(self, category_id: str) -> Dict[str, Any]:
        """Get a single category by ID"""
        return await self._make_request("GET", f"categories/{category_id}")

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
            "expand": "tender,cardTransaction,lineItems,order"  # Include tender type and card data for payment categorization
        }

        # Add date filters if provided
        # Clover supports multiple filters separated by &filter=
        filters = []
        if start_date:
            start_ms = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
            filters.append(f"createdTime>={start_ms}")
        if end_date:
            # End of day for end_date
            end_ms = int(datetime.combine(end_date, datetime.max.time()).timestamp() * 1000)
            filters.append(f"createdTime<={end_ms}")

        if filters:
            params["filter"] = filters[0]

        # Make request - if multiple filters, we need to add them as separate query params
        # Clover's API uses &filter= for each filter condition
        if len(filters) > 1:
            # Build URL with multiple filter params
            query_parts = [f"{k}={v}" for k, v in params.items() if k != "filter"]
            for f in filters:
                query_parts.append(f"filter={f}")
            query_string = "&".join(query_parts)
            return await self._make_request("GET", f"payments?{query_string}", params=None)

        return await self._make_request("GET", "payments", params=params)

    async def get_cash_events(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """
        Get cash events from Clover (includes payouts, cash adjustments, etc.)

        Cash events include:
        - CASH_ADJUSTMENT: Manual cash add/remove (payouts, drops, etc.)
        - SALE: Cash from sales
        - REFUND: Cash refunds

        Args:
            start_date: Filter cash events from this date
            end_date: Filter cash events until this date
            limit: Maximum number of events to return

        Returns:
            Dictionary with 'elements' list of cash events
        """
        limit = min(limit, 1000)

        params = {
            "limit": limit,
            "expand": "employee"  # Include employee who made the adjustment
        }

        # Add date filters if provided
        filters = []
        if start_date:
            start_ms = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
            filters.append(f"timestamp>={start_ms}")
        if end_date:
            end_ms = int(datetime.combine(end_date, datetime.max.time()).timestamp() * 1000)
            filters.append(f"timestamp<={end_ms}")

        if filters:
            params["filter"] = filters[0]

        # Make request - if multiple filters, we need to add them as separate query params
        if len(filters) > 1:
            query_parts = [f"{k}={v}" for k, v in params.items() if k != "filter"]
            for f in filters:
                query_parts.append(f"filter={f}")
            query_string = "&".join(query_parts)
            return await self._make_request("GET", f"cash_events?{query_string}", params=None)

        return await self._make_request("GET", "cash_events", params=params)

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
        "synced_at": datetime.now(timezone.utc)
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
    order_date = datetime.fromtimestamp(clover_order.get("createdTime", 0) / 1000)

    # Parse amounts (Clover uses cents, convert to dollars)
    # NOTE: Clover's order.total INCLUDES tax but NOT tip
    order_total = float(clover_order.get("total", 0)) / 100

    # Extract tax, tip, and discounts from payments (if available)
    tax = 0
    tip = 0
    total_paid = 0
    discount = 0

    if clover_order.get("payments") and clover_order["payments"].get("elements"):
        for payment in clover_order["payments"]["elements"]:
            # Skip refunded/voided payments
            if payment.get("result") == "SUCCESS":
                # Sum up all successful payments
                total_paid += float(payment.get("amount", 0)) / 100
                tax += float(payment.get("taxAmount", 0)) / 100 if payment.get("taxAmount") else 0
                tip += float(payment.get("tipAmount", 0)) / 100 if payment.get("tipAmount") else 0

                # Check for cashDiscount (this is the discount amount)
                if payment.get("cashDiscountAmount"):
                    discount += float(payment.get("cashDiscountAmount", 0)) / 100

    # Use total_paid if available (actual amount paid), otherwise use order total
    total = total_paid if total_paid > 0 else order_total

    # If no payments yet, check order-level discount
    if discount == 0 and clover_order.get("discounts") and clover_order["discounts"].get("elements"):
        for disc in clover_order["discounts"]["elements"]:
            discount += float(disc.get("amount", 0)) / 100

    # Calculate subtotal (pre-tax sales before discounts)
    # Clover's order.total = subtotal + tax + discount (discount is negative)
    # Therefore: subtotal = order.total - tax - discount
    # Since discount is negative (e.g., -$5), subtracting it adds it back
    subtotal = order_total - tax - discount

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
        "synced_at": datetime.now(timezone.utc)
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
            "quantity": float(item.get("unitQty", 1)),  # Clover quantity is already in units
            "unit_price": float(item.get("price", 0)) / 100,  # Convert cents to dollars
            "total_price": (float(item.get("price", 0)) / 100) * float(item.get("unitQty", 1)),
            "notes": item.get("note")
        }

        line_items.append(parsed_item)

    return line_items
