"""
POS Sync Service
Handles syncing sales data from POS systems (Clover, Square, Toast) into accounting
"""

import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from collections import defaultdict

from accounting.core.clover_client import CloverAPIClient, parse_clover_order
from accounting.models.pos import POSConfiguration, POSDailySalesCache
from accounting.models.area import Area

logger = logging.getLogger(__name__)


class POSSyncService:
    """Service for syncing POS sales data"""

    def __init__(self, db: Session):
        self.db = db

    async def sync_location(
        self,
        area_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Sync sales from POS for a specific location

        Args:
            area_id: Location/area ID
            start_date: Start date for sync (default: today)
            end_date: End date for sync (default: today)

        Returns:
            Dictionary with sync results
        """
        # Get POS configuration for this location
        config = self.db.query(POSConfiguration).filter(
            POSConfiguration.area_id == area_id,
            POSConfiguration.is_active == True
        ).first()

        if not config:
            raise ValueError(f"No active POS configuration found for area {area_id}")

        # Default date range to today
        if not start_date:
            start_date = date.today()
        if not end_date:
            end_date = date.today()

        logger.info(f"Syncing POS sales for area {area_id} from {start_date} to {end_date}")

        # Sync based on provider
        if config.provider == "clover":
            result = await self._sync_clover(config, start_date, end_date)
        elif config.provider == "square":
            raise NotImplementedError("Square integration not yet implemented")
        elif config.provider == "toast":
            raise NotImplementedError("Toast integration not yet implemented")
        else:
            raise ValueError(f"Unsupported POS provider: {config.provider}")

        # Update last sync date
        config.last_sync_date = datetime.utcnow()
        self.db.commit()

        return result

    async def _sync_clover(
        self,
        config: POSConfiguration,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """Sync sales from Clover POS"""
        # Initialize Clover client
        client = CloverAPIClient(
            merchant_id=config.merchant_id,
            access_token=config.access_token,
            environment=config.api_environment
        )

        # Test connection first
        if not await client.test_connection():
            raise Exception("Failed to connect to Clover API. Check credentials.")

        # Track results
        total_synced = 0
        total_skipped = 0
        errors = []

        # Iterate through each day in the range
        current_date = start_date
        while current_date <= end_date:
            try:
                # Fetch orders for this day
                orders_response = await client.get_orders(
                    start_date=current_date,
                    end_date=current_date,
                    limit=1000  # Clover max
                )

                orders = orders_response.get("elements", [])

                # Filter for PAID orders only
                paid_orders = [
                    order for order in orders
                    if order.get("state", "").upper() == "LOCKED"  # LOCKED = completed/paid
                ]

                logger.info(f"Found {len(paid_orders)} paid orders for {current_date}")

                if paid_orders:
                    # Aggregate sales for this day
                    daily_summary = self._aggregate_daily_sales(paid_orders, config.area_id, current_date)

                    # Save to cache (upsert)
                    existing = self.db.query(POSDailySalesCache).filter(
                        POSDailySalesCache.area_id == config.area_id,
                        POSDailySalesCache.sale_date == current_date,
                        POSDailySalesCache.provider == config.provider
                    ).first()

                    if existing:
                        # Update existing record
                        for key, value in daily_summary.items():
                            setattr(existing, key, value)
                        existing.synced_at = datetime.utcnow()
                        total_skipped += 1
                    else:
                        # Create new record
                        cache_entry = POSDailySalesCache(**daily_summary)
                        self.db.add(cache_entry)
                        total_synced += 1

                    self.db.commit()

            except Exception as e:
                logger.error(f"Error syncing {current_date}: {str(e)}")
                errors.append({"date": str(current_date), "error": str(e)})

            current_date += timedelta(days=1)

        return {
            "synced_count": total_synced,
            "updated_count": total_skipped,
            "error_count": len(errors),
            "errors": errors,
            "date_range": {
                "start": str(start_date),
                "end": str(end_date)
            }
        }

    def _aggregate_daily_sales(
        self,
        orders: List[Dict],
        area_id: int,
        sale_date: date
    ) -> Dict[str, Any]:
        """
        Aggregate Clover orders into daily sales summary

        Args:
            orders: List of Clover order objects
            area_id: Location ID
            sale_date: Date of sales

        Returns:
            Dictionary with daily sales aggregates
        """
        # Initialize totals
        total_sales = Decimal('0')
        total_tax = Decimal('0')
        total_tips = Decimal('0')
        total_discounts = Decimal('0')
        transaction_count = len(orders)

        # Breakdowns
        order_types = defaultdict(Decimal)
        payment_methods = defaultdict(Decimal)
        categories = defaultdict(Decimal)

        # Process each order
        for order in orders:
            # Parse order amounts (Clover uses cents)
            order_total = Decimal(order.get("total", 0)) / 100

            # Extract from payments
            order_tax = Decimal('0')
            order_tip = Decimal('0')
            order_payment_total = Decimal('0')

            if order.get("payments") and order["payments"].get("elements"):
                for payment in order["payments"]["elements"]:
                    if payment.get("result") == "SUCCESS":
                        order_payment_total += Decimal(payment.get("amount", 0)) / 100
                        order_tax += Decimal(payment.get("taxAmount", 0) or 0) / 100
                        order_tip += Decimal(payment.get("tipAmount", 0) or 0) / 100

                        # Track payment method
                        card_type = payment.get("cardTransaction", {}).get("cardType", "CASH")
                        if card_type and card_type != "CASH":
                            payment_methods["credit_card"] += Decimal(payment.get("amount", 0)) / 100
                        else:
                            payment_methods["cash"] += Decimal(payment.get("amount", 0)) / 100

            # Calculate subtotal (sales before tax and tips)
            order_subtotal = order_total - order_tax

            # Accumulate totals
            total_sales += order_subtotal
            total_tax += order_tax
            total_tips += order_tip

            # Track order type
            order_type = order.get("orderType", {}).get("label", "unknown")
            order_types[order_type.lower()] += order_subtotal

            # Categorize line items
            if order.get("lineItems") and order["lineItems"].get("elements"):
                for item in order["lineItems"]["elements"]:
                    if item.get("deleted"):
                        continue

                    item_price = Decimal(item.get("price", 0)) / 100
                    item_qty = item.get("unitQty", 1)
                    item_total = item_price * Decimal(item_qty)

                    # Try to categorize (would need item category mapping)
                    # For now, use a simple heuristic or default
                    item_name = item.get("name", "").lower()
                    category = self._categorize_item(item_name)
                    categories[category] += item_total

        # Calculate gross sales (total including tax and tips)
        gross_sales = total_sales + total_tax + total_tips

        # Convert categories dict to list for JSON storage
        categories_list = [
            {"name": name, "sales": float(amount)}
            for name, amount in categories.items()
        ]

        return {
            "area_id": area_id,
            "sale_date": sale_date,
            "provider": "clover",
            "total_sales": float(total_sales),
            "total_tax": float(total_tax),
            "total_tips": float(total_tips),
            "total_discounts": float(total_discounts),
            "gross_sales": float(gross_sales),
            "transaction_count": transaction_count,
            "order_types": dict(order_types),  # Convert defaultdict to dict
            "payment_methods": dict(payment_methods),
            "categories": categories_list,
            "raw_summary": {
                "order_count": len(orders),
                "sync_date": datetime.utcnow().isoformat()
            }
        }

    def _categorize_item(self, item_name: str) -> str:
        """
        Simple categorization of items based on name
        In production, this would use a mapping table
        """
        item_name = item_name.lower()

        # Beverage keywords
        if any(word in item_name for word in ["beer", "wine", "cocktail", "liquor", "vodka", "whiskey", "rum", "gin"]):
            return "Alcohol"
        elif any(word in item_name for word in ["soda", "coke", "pepsi", "sprite", "tea", "coffee", "juice", "water"]):
            return "Beverages"
        else:
            return "Food"

    async def get_daily_sales_cache(
        self,
        area_id: int,
        sale_date: date
    ) -> Optional[POSDailySalesCache]:
        """Get cached POS sales for a specific day"""
        return self.db.query(POSDailySalesCache).filter(
            POSDailySalesCache.area_id == area_id,
            POSDailySalesCache.sale_date == sale_date
        ).first()

    def get_sales_summary(
        self,
        area_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[POSDailySalesCache]:
        """Get POS sales summaries with optional filters"""
        query = self.db.query(POSDailySalesCache)

        if area_id:
            query = query.filter(POSDailySalesCache.area_id == area_id)
        if start_date:
            query = query.filter(POSDailySalesCache.sale_date >= start_date)
        if end_date:
            query = query.filter(POSDailySalesCache.sale_date <= end_date)

        return query.order_by(POSDailySalesCache.sale_date.desc()).all()
