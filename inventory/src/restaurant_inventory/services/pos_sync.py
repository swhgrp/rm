"""
POS Sync Service
Handles syncing sales data from POS systems to the database
"""

from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date
import logging

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from restaurant_inventory.models.pos_sale import (
    POSConfiguration,
    POSSale,
    POSSaleItem,
    POSProvider
)
from restaurant_inventory.core.clover_client import (
    CloverAPIClient,
    parse_clover_order,
    parse_clover_line_items,
    parse_clover_payment
)
from restaurant_inventory.services.inventory_deduction import InventoryDeductionService

logger = logging.getLogger(__name__)


class POSSyncService:
    """Service for syncing POS sales data"""

    def __init__(self, db: Session):
        self.db = db

    async def sync_sales(
        self,
        location_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        deduct_inventory: bool = True
    ) -> Tuple[int, int, List[str]]:
        """
        Sync sales from POS for a location

        Args:
            location_id: Location ID to sync for
            start_date: Start date for sync (defaults to today)
            end_date: End date for sync (defaults to today)
            limit: Max orders to fetch
            deduct_inventory: Whether to automatically deduct inventory (default: True)

        Returns:
            Tuple of (orders_synced, orders_skipped, errors)
        """
        # Get POS configuration
        config = self.db.query(POSConfiguration).filter(
            POSConfiguration.location_id == location_id
        ).first()

        if not config:
            raise ValueError(f"No POS configuration found for location {location_id}")

        if not config.is_active:
            raise ValueError(f"POS configuration for location {location_id} is not active")

        # Default to today if no dates provided
        if not start_date:
            start_date = date.today()
        if not end_date:
            end_date = date.today()

        # Sync based on provider
        if config.provider == POSProvider.CLOVER.value:
            return await self._sync_clover_sales(config, start_date, end_date, limit, deduct_inventory)
        else:
            raise ValueError(f"Unsupported POS provider: {config.provider}")

    async def _sync_clover_sales(
        self,
        config: POSConfiguration,
        start_date: date,
        end_date: date,
        limit: int,
        deduct_inventory: bool = True
    ) -> Tuple[int, int, List[str]]:
        """
        Sync sales from Clover POS

        Returns:
            Tuple of (orders_synced, orders_skipped, errors)
        """
        synced = 0
        skipped = 0
        errors = []
        synced_sales = []  # Track synced sales for inventory deduction

        try:
            # Initialize Clover client
            logger.info(f"Initializing Clover client with merchant_id={config.merchant_id}, environment={config.api_environment}")
            logger.debug(f"Access token length: {len(config.access_token) if config.access_token else 0}")

            client = CloverAPIClient(
                merchant_id=config.merchant_id,
                access_token=config.access_token,
                environment=config.api_environment
            )

            # Fetch orders with payments expanded
            logger.info(f"Fetching Clover orders from {start_date} to {end_date}, max {limit} orders")

            # Clover max limit is 1000
            fetch_limit = min(limit, 1000)

            response = await client.get_orders(
                start_date=start_date,
                end_date=end_date,  # Pass end_date to Clover API for filtering
                limit=fetch_limit,
                offset=0
            )

            orders = response.get("elements", [])
            logger.info(f"Total fetched: {len(orders)} orders from Clover")

            # Filter by date range and only paid orders
            # Note: Clover API may return orders outside our date range due to API limitations
            filtered_orders = []
            start_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
            end_datetime = datetime.combine(end_date, datetime.max.time()) if end_date else None

            for order in orders:
                # Use clientCreatedTime (when order was placed) instead of createdTime
                # This matches the accounting system and is more accurate for date filtering
                order_time = datetime.fromtimestamp(order.get("clientCreatedTime", order.get("createdTime", 0)) / 1000)

                # Use state == LOCKED instead of paymentState == PAID
                # LOCKED means the order is completed and locked from editing
                # This matches the accounting system approach and captures all completed orders
                state = order.get("state", "").upper()

                # Check if order is within date range and LOCKED (completed)
                in_range = True
                if start_datetime and order_time < start_datetime:
                    in_range = False
                if end_datetime and order_time > end_datetime:
                    in_range = False

                if in_range and state == "LOCKED":
                    filtered_orders.append(order)

            orders = filtered_orders
            logger.info(f"Filtered to {len(orders)} locked (completed) orders within date range")

            # Process each order
            for order in orders:
                try:
                    # Check if order already exists
                    existing = self.db.query(POSSale).filter(
                        POSSale.pos_order_id == order["id"]
                    ).first()

                    if existing:
                        logger.debug(f"Order {order['id']} already exists, skipping")
                        skipped += 1
                        continue

                    # Parse order data - this will now include payment info since we expanded payments
                    order_data = parse_clover_order(order)
                    order_data["pos_provider"] = POSProvider.CLOVER.value
                    order_data["pos_merchant_id"] = config.merchant_id
                    order_data["location_id"] = config.location_id

                    # Create sale record from order
                    sale = POSSale(**order_data)
                    self.db.add(sale)
                    self.db.flush()  # Get the sale ID

                    # Parse and add line items
                    line_items = parse_clover_line_items(order)
                    for item_data in line_items:
                        item_data["sale_id"] = sale.id
                        sale_item = POSSaleItem(**item_data)
                        self.db.add(sale_item)

                    synced += 1
                    synced_sales.append(sale)  # Track for inventory deduction
                    logger.info(f"Synced order {order['id']} with {len(line_items)} items (${order_data['subtotal']:.2f} net)")

                except Exception as e:
                    error_msg = f"Error processing order {order.get('id', 'unknown')}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    continue

            # Commit all changes
            self.db.commit()

            logger.info(f"Sync complete: {synced} synced, {skipped} skipped, {len(errors)} errors")

            # Process inventory deductions if enabled
            if deduct_inventory and synced_sales:
                logger.info(f"Processing inventory deductions for {len(synced_sales)} synced sales")
                try:
                    # Refresh sale objects to get relationships loaded
                    refreshed_sales = []
                    for sale in synced_sales:
                        refreshed = self.db.query(POSSale).filter(POSSale.id == sale.id).first()
                        if refreshed:
                            refreshed_sales.append(refreshed)

                    deduction_service = InventoryDeductionService(self.db)
                    deduction_result = deduction_service.process_bulk_sales(refreshed_sales)

                    logger.info(
                        f"Inventory deduction complete: {deduction_result['total_items_deducted']} items deducted, "
                        f"{deduction_result['total_transactions_created']} transactions created, "
                        f"{deduction_result['total_items_skipped']} items skipped (no mapping)"
                    )

                    if deduction_result['errors']:
                        errors.extend(deduction_result['errors'])

                except Exception as e:
                    error_msg = f"Error during inventory deduction: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            # Update last sync date in configuration
            config.last_sync_date = get_now()
            self.db.commit()

        except Exception as e:
            self.db.rollback()
            error_msg = f"Failed to sync Clover sales: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)

        return synced, skipped, errors

    def get_sales(
        self,
        location_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[POSSale]:
        """
        Get sales from database

        Args:
            location_id: Filter by location
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Max records to return
            offset: Pagination offset

        Returns:
            List of POSSale objects
        """
        query = self.db.query(POSSale)

        if location_id:
            query = query.filter(POSSale.location_id == location_id)

        if start_date:
            query = query.filter(POSSale.order_date >= datetime.combine(start_date, datetime.min.time()))

        if end_date:
            query = query.filter(POSSale.order_date <= datetime.combine(end_date, datetime.max.time()))

        query = query.order_by(POSSale.order_date.desc())
        query = query.limit(limit).offset(offset)

        return query.all()

    def get_sale(self, sale_id: int) -> Optional[POSSale]:
        """Get a single sale by ID"""
        return self.db.query(POSSale).filter(POSSale.id == sale_id).first()

    def get_sale_count(
        self,
        location_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> int:
        """Get count of sales matching filters"""
        query = self.db.query(POSSale)

        if location_id:
            query = query.filter(POSSale.location_id == location_id)

        if start_date:
            query = query.filter(POSSale.order_date >= datetime.combine(start_date, datetime.min.time()))

        if end_date:
            query = query.filter(POSSale.order_date <= datetime.combine(end_date, datetime.max.time()))

        return query.count()
