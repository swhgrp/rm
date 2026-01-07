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
from accounting.models.pos import POSConfiguration, POSDailySalesCache, POSCategoryGLMapping, POSPaymentGLMapping
from accounting.models.area import Area
from accounting.models.daily_sales_summary import DailySalesSummary, SalesLineItem, SalesPayment
from accounting.models.account import Account

logger = logging.getLogger(__name__)


class POSSyncService:
    """Service for syncing POS sales data"""

    def __init__(self, db: Session):
        self.db = db

    async def sync_location(
        self,
        area_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Sync sales from POS for a specific location and auto-create DSS entries

        Args:
            area_id: Location/area ID
            start_date: Start date for sync (default: today)
            end_date: End date for sync (default: today)
            user_id: User ID for creating DSS entries

        Returns:
            Dictionary with sync results including DSS creation
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
            result = await self._sync_clover(config, start_date, end_date, user_id)
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
        end_date: date,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Sync sales from Clover POS using payments as source of truth"""
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
                # Calculate timestamps for current_date range
                day_start_ms = int(datetime.combine(current_date, datetime.min.time()).timestamp() * 1000)
                day_end_ms = int(datetime.combine(current_date, datetime.max.time()).timestamp() * 1000)

                # Fetch PAYMENTS for this day (source of truth for totals)
                # Payments are filtered by createdTime, which is when money was collected
                payments_response = await client.get_payments(
                    start_date=current_date,
                    end_date=current_date,
                    limit=1000
                )
                all_payments = payments_response.get("elements", [])

                # Filter payments within date range
                day_payments = []
                for payment in all_payments:
                    payment_time = payment.get("createdTime", 0)
                    if day_start_ms <= payment_time <= day_end_ms:
                        if payment.get("result") == "SUCCESS":
                            day_payments.append(payment)

                # Fetch ORDERS for this day (for category breakdown)
                orders_response = await client.get_orders(
                    start_date=current_date,
                    end_date=current_date,
                    limit=1000
                )
                orders = orders_response.get("elements", [])

                # Build order lookup by ID for category extraction
                order_lookup = {}
                for order in orders:
                    if order.get("state", "").upper() == "LOCKED":
                        order_lookup[order.get("id")] = order

                # Find missing orders (payments reference orders not in our date range)
                missing_order_ids = []
                for payment in day_payments:
                    payment_order = payment.get("order", {})
                    order_id = payment_order.get("id") if payment_order else None
                    if order_id and order_id not in order_lookup:
                        missing_order_ids.append(order_id)

                # Fetch missing orders individually
                if missing_order_ids:
                    logger.info(f"Fetching {len(missing_order_ids)} missing orders referenced by payments")
                    for order_id in missing_order_ids:
                        try:
                            order = await client.get_order(order_id)
                            if order and order.get("state", "").upper() == "LOCKED":
                                order_lookup[order_id] = order
                        except Exception as e:
                            logger.warning(f"Could not fetch order {order_id}: {e}")

                # Fetch CASH EVENTS for this day (payouts, adjustments)
                # Note: This endpoint requires additional Clover permissions
                day_payouts = []
                try:
                    cash_events_response = await client.get_cash_events(
                        start_date=current_date,
                        end_date=current_date,
                        limit=1000
                    )
                    all_cash_events = cash_events_response.get("elements", [])

                    # Filter cash events within date range - only include CASH_ADJUSTMENT type (payouts)
                    for event in all_cash_events:
                        event_time = event.get("timestamp", 0)
                        if day_start_ms <= event_time <= day_end_ms:
                            # CASH_ADJUSTMENT events are payouts/drops
                            # Negative amounts = money taken OUT (payout)
                            # Positive amounts = money added IN
                            if event.get("type") == "CASH_ADJUSTMENT":
                                day_payouts.append(event)
                except Exception as cash_events_error:
                    # Cash events endpoint may require additional permissions
                    # Continue without payout data rather than failing
                    logger.warning(f"Could not fetch cash events for {current_date}: {cash_events_error}")

                logger.info(f"Found {len(day_payments)} payments, {len(order_lookup)} orders, and {len(day_payouts)} payouts for {current_date}")

                if day_payments:
                    # Aggregate sales for this day using payments as source of truth
                    daily_summary = self._aggregate_daily_sales_from_payments(
                        day_payments, order_lookup, day_payouts, config.area_id, current_date
                    )

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
                        self.db.commit()
                        cache_entry = existing
                        total_skipped += 1
                    else:
                        # Create new record
                        cache_entry = POSDailySalesCache(**daily_summary)
                        self.db.add(cache_entry)
                        self.db.commit()
                        total_synced += 1

                    # Auto-create DSS from cache if user_id provided
                    if user_id:
                        try:
                            logger.info(f"Creating DSS for {current_date} with user_id={user_id}")
                            dss = self.create_dss_from_cache(cache_entry, user_id)
                            logger.info(f"Auto-created DSS #{dss.id} for {current_date}")
                        except Exception as dss_error:
                            logger.error(f"Error creating DSS for {current_date}: {str(dss_error)}", exc_info=True)
                            # Don't fail the sync if DSS creation fails

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
        total_gross_sales = Decimal('0')  # Sum of line items before discounts/refunds
        total_sales = Decimal('0')  # Net sales after discounts but before refunds
        total_tax = Decimal('0')
        total_tips = Decimal('0')
        total_discounts = Decimal('0')
        total_refunds = Decimal('0')
        transaction_count = len(orders)

        # Breakdowns
        order_types = defaultdict(Decimal)
        payment_methods = defaultdict(Decimal)
        payment_tips = defaultdict(Decimal)  # Track tips by payment method
        categories = defaultdict(Decimal)
        discounts = defaultdict(Decimal)  # Track discounts by name

        # Process each order
        for order in orders:
            # Clover order structure:
            # - total: Order total INCLUDING tax, EXCLUDING tips (in cents)
            # - payments[].amount: Payment amount INCLUDING tip (in cents)
            # - payments[].taxAmount: Tax portion (in cents)
            # - payments[].tipAmount: Tip portion (in cents)

            # Get order total from order object (more reliable than summing payments for split-tender)
            order_total = Decimal(order.get("total", 0)) / 100  # Includes tax, excludes tips

            # Sum tax and tips across ALL successful payments
            # Each payment can have its own tax and tip amounts
            order_tax = Decimal('0')
            order_tip = Decimal('0')

            if order.get("payments") and order["payments"].get("elements"):
                # Track payment methods by summing all successful payments
                for payment in order["payments"]["elements"]:
                    if payment.get("result") == "SUCCESS":
                        payment_amount = Decimal(payment.get("amount", 0)) / 100
                        payment_tip = Decimal(payment.get("tipAmount", 0) or 0) / 100
                        payment_tax = Decimal(payment.get("taxAmount", 0) or 0) / 100

                        # Sum tax and tips from ALL payments (not just first)
                        order_tax += payment_tax
                        order_tip += payment_tip

                        # Track payment method - group Credit Card and Debit Card as "CARD"
                        # Clover uses tender.labelKey (e.g., com.clover.tender.credit_card) to identify payment type
                        tender = payment.get("tender", {})
                        tender_label_key = tender.get("labelKey", "") if tender else ""
                        tender_label = tender.get("label", "").upper() if tender else ""

                        # Categorize payment type - first check labelKey for most accurate categorization
                        payment_key = None
                        if "cash" in tender_label_key.lower():
                            payment_key = "CASH"
                        elif "debit" in tender_label_key.lower() or "credit" in tender_label_key.lower():
                            payment_key = "CARD"  # Group credit and debit together
                        elif "gift" in tender_label_key.lower():
                            payment_key = "GIFT_CARD"
                        # Fallback to label if labelKey is not available
                        elif tender_label == "CASH":
                            payment_key = "CASH"
                        elif tender_label in ["CREDIT CARD", "DEBIT CARD"]:
                            payment_key = "CARD"  # Group credit and debit together
                        elif tender_label == "GIFT CARD":
                            payment_key = "GIFT_CARD"
                        elif tender_label:
                            payment_key = tender_label.replace(" ", "_")
                        else:
                            # If no tender info, check if there's a cardTransaction
                            card_txn = payment.get("cardTransaction")
                            if card_txn:
                                payment_key = "CARD"
                            else:
                                payment_key = "CASH"

                        # In Clover, payment.amount does NOT include tip (tip is separate)
                        # So we can use payment_amount directly as the base payment
                        payment_methods[payment_key] += payment_amount
                        if payment_tip > 0:
                            payment_tips[payment_key] += payment_tip

            # Calculate gross sales from line items (before discounts and refunds)
            # Include ALL line items, even refunded ones - refunds are tracked separately
            order_gross_sales = Decimal('0')
            if order.get("lineItems") and order["lineItems"].get("elements"):
                for item in order["lineItems"]["elements"]:
                    # Only skip deleted items (items removed before order completion)
                    if item.get("deleted"):
                        continue

                    item_price = Decimal(item.get("price", 0)) / 100
                    item_qty = item.get("unitQty", 1)
                    item_total = item_price * Decimal(item_qty)
                    order_gross_sales += item_total

                    # Get category from item's category list (Clover items can have multiple categories)
                    category_name = "Uncategorized"
                    if item.get("item") and item["item"].get("categories") and item["item"]["categories"].get("elements"):
                        # Use the first category name
                        first_category = item["item"]["categories"]["elements"][0]
                        category_name = first_category.get("name", "Uncategorized")

                    categories[category_name] += item_total

            # Calculate net sales (order total minus tax)
            # order_total already includes tax, so: net_sales = total - tax
            order_net_sales = order_total - order_tax

            # Calculate refunds for this order
            # Refunds in Clover are tracked separately and do NOT affect order.total
            # Refunds can appear as:
            # 1. Separate refund transactions (with negative amounts)
            # 2. Refund records attached to the original order
            order_refund = Decimal('0')
            if order.get("refunds") and order["refunds"].get("elements"):
                for refund in order["refunds"]["elements"]:
                    # Clover refund amount is in cents
                    refund_amount = Decimal(refund.get("amount", 0)) / 100
                    order_refund += abs(refund_amount)  # Make positive for tracking

            # Calculate order-level discount as the difference between gross and net
            # Discounts and refunds are independent - do not subtract refunds from discounts
            order_discount = order_gross_sales - order_net_sales

            # Track individual discount names for breakdown (for UI display)
            # We'll calculate these but then normalize them to match Clover's exact total
            order_discount_breakdown = {}
            order_discount_sum = Decimal('0')

            # Track order type
            order_type = order.get("orderType", {}).get("label", "unknown")
            order_types[order_type.lower()] += order_net_sales

            # Process order-level discounts (for breakdown by name)
            if order.get("discounts") and order["discounts"].get("elements"):
                for discount in order["discounts"]["elements"]:
                    discount_name = discount.get("name", "Unknown Discount")

                    # Clover has two types of discounts:
                    # 1. Fixed amount: has 'amount' field (in cents, negative)
                    # 2. Percentage: has 'percentage' field (0-100)
                    if "amount" in discount:
                        # Fixed amount discount (already in cents, negative)
                        discount_amount = Decimal(discount["amount"]) / 100
                    elif "percentage" in discount:
                        # Percentage discount - estimate from gross sales
                        percentage = Decimal(discount["percentage"])
                        if percentage == 100:
                            discount_amount = -order_gross_sales
                        elif percentage > 0:
                            discount_amount = -(order_gross_sales * percentage / 100)
                        else:
                            discount_amount = Decimal('0')
                    else:
                        discount_amount = Decimal('0')

                    order_discount_breakdown[discount_name] = discount_amount
                    order_discount_sum += abs(discount_amount)

            # Process line item discounts
            if order.get("lineItems") and order["lineItems"].get("elements"):
                for item in order["lineItems"]["elements"]:
                    if item.get("discounts") and item["discounts"].get("elements"):
                        for discount in item["discounts"]["elements"]:
                            discount_name = discount.get("name", "Unknown Discount")

                            # Same logic as order-level discounts
                            if "amount" in discount:
                                discount_amount = Decimal(discount["amount"]) / 100
                            elif "percentage" in discount:
                                percentage = Decimal(discount["percentage"])
                                item_price = Decimal(item.get("price", 0)) / 100
                                item_qty = item.get("unitQty", 1)
                                item_total = item_price * Decimal(item_qty)

                                if percentage == 100:
                                    discount_amount = -item_total
                                elif percentage > 0:
                                    discount_amount = -(item_total * percentage / 100)
                                else:
                                    discount_amount = Decimal('0')
                            else:
                                discount_amount = Decimal('0')

                            if discount_name not in order_discount_breakdown:
                                order_discount_breakdown[discount_name] = Decimal('0')
                            order_discount_breakdown[discount_name] += discount_amount
                            order_discount_sum += abs(discount_amount)

            # Accumulate discount breakdown (don't normalize per-order)
            # We'll normalize the total breakdown after processing all orders
            if order_discount_breakdown:
                for discount_name, amount in order_discount_breakdown.items():
                    discounts[discount_name] += amount
            elif order_discount > 0:
                # No breakdown available, just track as "Mixed Discounts"
                discounts["Mixed Discounts"] += -abs(order_discount)

            # Accumulate totals using Clover's exact amounts
            total_gross_sales += order_gross_sales  # Sum of line items before discounts
            total_sales += order_net_sales
            total_tax += order_tax
            total_tips += order_tip
            total_discounts += order_discount  # Use Clover's exact discount total (now excluding refunds)
            total_refunds += order_refund  # Refunds tracked separately

        # Gross sales is the sum of line items BEFORE discounts and refunds
        # This should NOT include tax or tips
        gross_sales = total_gross_sales

        # Reconcile discount breakdown with total discounts
        # Note: discounts dict stores negative values, but total_discounts is positive
        # If breakdown doesn't match total, add "Unallocated Discounts" to make up the difference
        breakdown_sum = sum(abs(v) for v in discounts.values())  # Sum absolute values
        if abs(breakdown_sum - total_discounts) > Decimal('0.01'):  # More than 1 cent difference
            unallocated = total_discounts - breakdown_sum
            if abs(unallocated) > Decimal('0.01'):
                # Store as negative to match other discount entries
                discounts["Unallocated Discounts"] = -abs(unallocated)

        # Convert order_types, payment_methods, categories, discounts, and tips Decimal values to float
        order_types_dict = {k: float(v) for k, v in order_types.items()}
        payment_methods_dict = {k: float(v) for k, v in payment_methods.items()}
        payment_tips_dict = {k: float(v) for k, v in payment_tips.items()}
        categories_dict = {k: float(v) for k, v in categories.items()}
        discounts_dict = {k: float(v) for k, v in discounts.items()}

        return {
            "area_id": area_id,
            "sale_date": sale_date,
            "provider": "clover",
            "total_sales": float(total_sales),
            "total_tax": float(total_tax),
            "total_tips": float(total_tips),
            "total_discounts": float(total_discounts),
            "total_refunds": float(total_refunds),
            "gross_sales": float(gross_sales),
            "transaction_count": transaction_count,
            "order_types": order_types_dict,
            "payment_methods": payment_methods_dict,
            "categories": categories_dict,
            "discounts": discounts_dict,
            "raw_summary": {
                "order_count": len(orders),
                "sync_date": datetime.utcnow().isoformat(),
                "payment_tips": payment_tips_dict  # Tips by payment method
            }
        }

    def _aggregate_daily_sales_from_payments(
        self,
        payments: List[Dict],
        order_lookup: Dict[str, Dict],
        payouts: List[Dict],
        area_id: int,
        sale_date: date
    ) -> Dict[str, Any]:
        """
        Aggregate Clover payments into daily sales summary.

        Uses payments as source of truth for totals (gross sales, tax, tips)
        and orders for category breakdown.

        Args:
            payments: List of Clover payment objects for the day
            order_lookup: Dictionary of order_id -> order object for category extraction
            payouts: List of Clover cash_event objects (CASH_ADJUSTMENT type) for the day
            area_id: Location ID
            sale_date: Date of sales

        Returns:
            Dictionary with daily sales aggregates
        """
        # Initialize totals from payments (source of truth)
        total_payment_amount = Decimal('0')  # Payment amount (includes tax, excludes tips)
        total_tax = Decimal('0')
        total_tips = Decimal('0')
        total_discounts = Decimal('0')
        total_refunds = Decimal('0')
        transaction_count = len(payments)

        # Track refunds by payment type for deposit calculation
        card_refunds = Decimal('0')
        cash_refunds = Decimal('0')

        # Breakdowns
        order_types = defaultdict(Decimal)
        payment_methods = defaultdict(Decimal)
        payment_tips_by_method = defaultdict(Decimal)
        categories = defaultdict(Decimal)
        discounts_breakdown = defaultdict(Decimal)
        processed_order_ids = set()

        # Process each payment
        for payment in payments:
            payment_amount = Decimal(payment.get("amount", 0)) / 100
            payment_tax = Decimal(payment.get("taxAmount", 0) or 0) / 100
            payment_tip = Decimal(payment.get("tipAmount", 0) or 0) / 100

            total_payment_amount += payment_amount
            total_tax += payment_tax
            total_tips += payment_tip

            # Track payment method - group Credit Card and Debit Card as "CARD"
            # Clover uses tender.labelKey (e.g., com.clover.tender.credit_card) to identify payment type
            tender = payment.get("tender", {})
            tender_label_key = tender.get("labelKey", "") if tender else ""
            tender_label = tender.get("label", "").upper() if tender else ""

            # First check labelKey for most accurate categorization
            if "cash" in tender_label_key.lower():
                payment_key = "CASH"
            elif "debit" in tender_label_key.lower() or "credit" in tender_label_key.lower():
                payment_key = "CARD"  # Group credit and debit together
            elif "gift" in tender_label_key.lower():
                payment_key = "GIFT_CARD"
            # Fallback to label if labelKey is not available
            elif tender_label == "CASH":
                payment_key = "CASH"
            elif tender_label in ["CREDIT CARD", "DEBIT CARD"]:
                payment_key = "CARD"  # Group credit and debit together
            elif tender_label == "GIFT CARD":
                payment_key = "GIFT_CARD"
            elif tender_label:
                payment_key = tender_label.replace(" ", "_")
            else:
                # If no tender info, check if there's a cardTransaction (card payment)
                card_txn = payment.get("cardTransaction")
                if card_txn:
                    payment_key = "CARD"  # Default card payments to CARD
                else:
                    payment_key = "CASH"  # No card transaction = likely cash

            payment_methods[payment_key] += payment_amount
            if payment_tip > 0:
                payment_tips_by_method[payment_key] += payment_tip

            # Get order for category breakdown (only process each order once)
            payment_order = payment.get("order", {})
            order_id = payment_order.get("id") if payment_order else None

            if order_id and order_id not in processed_order_ids:
                processed_order_ids.add(order_id)
                order = order_lookup.get(order_id)

                if order:
                    # Extract category breakdown from order line items
                    if order.get("lineItems") and order["lineItems"].get("elements"):
                        for item in order["lineItems"]["elements"]:
                            if item.get("deleted"):
                                continue

                            item_price = Decimal(item.get("price", 0)) / 100
                            item_qty = item.get("unitQty", 1)
                            item_total = item_price * Decimal(item_qty)

                            # Get category
                            category_name = "Uncategorized"
                            if item.get("item") and item["item"].get("categories") and item["item"]["categories"].get("elements"):
                                first_category = item["item"]["categories"]["elements"][0]
                                category_name = first_category.get("name", "Uncategorized")

                            categories[category_name] += item_total

                    # Track order type
                    order_type = order.get("orderType", {}).get("label", "unknown")
                    order_net = Decimal(order.get("total", 0)) / 100
                    # Subtract tax from order total to get net sales for order type
                    order_tax_est = Decimal('0')
                    if order.get("payments") and order["payments"].get("elements"):
                        for p in order["payments"]["elements"]:
                            if p.get("result") == "SUCCESS":
                                order_tax_est += Decimal(p.get("taxAmount", 0) or 0) / 100
                    order_types[order_type.lower()] += order_net - order_tax_est

                    # First, calculate order's gross total from line items (before discounts)
                    order_line_items_total = Decimal('0')
                    if order.get("lineItems") and order["lineItems"].get("elements"):
                        for item in order["lineItems"]["elements"]:
                            if item.get("deleted"):
                                continue
                            item_price = Decimal(item.get("price", 0)) / 100
                            item_qty = item.get("unitQty", 1)
                            order_line_items_total += item_price * Decimal(item_qty)

                    # Extract discounts from order (order-level discounts)
                    if order.get("discounts") and order["discounts"].get("elements"):
                        for disc in order["discounts"]["elements"]:
                            disc_name = disc.get("name", "Unknown Discount")
                            if "amount" in disc:
                                disc_amount = abs(Decimal(disc["amount"])) / 100
                            elif "percentage" in disc:
                                # Calculate percentage-based discount from line items total (pre-discount)
                                percentage = Decimal(disc["percentage"])
                                disc_amount = order_line_items_total * percentage / 100
                            else:
                                disc_amount = Decimal('0')
                            if disc_amount > 0:
                                discounts_breakdown[disc_name] += disc_amount
                                total_discounts += disc_amount

                    # Extract line item discounts (item-level discounts)
                    if order.get("lineItems") and order["lineItems"].get("elements"):
                        for item in order["lineItems"]["elements"]:
                            if item.get("deleted"):
                                continue
                            if item.get("discounts") and item["discounts"].get("elements"):
                                for disc in item["discounts"]["elements"]:
                                    disc_name = disc.get("name", "Unknown Discount")
                                    if "amount" in disc:
                                        disc_amount = abs(Decimal(disc["amount"])) / 100
                                    elif "percentage" in disc:
                                        # Calculate percentage-based discount from item total
                                        percentage = Decimal(disc["percentage"])
                                        item_price = Decimal(item.get("price", 0)) / 100
                                        item_qty = item.get("unitQty", 1)
                                        item_total = item_price * Decimal(item_qty)
                                        disc_amount = item_total * percentage / 100
                                    else:
                                        disc_amount = Decimal('0')
                                    if disc_amount > 0:
                                        discounts_breakdown[disc_name] += disc_amount
                                        total_discounts += disc_amount

                    # Extract refunds from order
                    if order.get("refunds") and order["refunds"].get("elements"):
                        for refund in order["refunds"]["elements"]:
                            refund_amount = abs(Decimal(refund.get("amount", 0))) / 100
                            total_refunds += refund_amount

        # Gross sales should be calculated from line items (what Clover reports)
        line_items_total = sum(categories.values())
        if line_items_total > 0:
            gross_sales = line_items_total
        else:
            # Fallback: derive from payment data
            gross_sales = total_payment_amount - total_tax + total_discounts

        # Calculate net sales using Clover's formula:
        # Net Sales = Gross Sales - Discounts - Refunds
        # Note: Payment amount includes discounts already applied, but NOT refunds
        # So we need to derive discounts from the difference
        payment_net = total_payment_amount - total_tax  # This is Gross - Discounts

        # Effective discounts = Gross - Payment Net
        effective_discounts = gross_sales - payment_net

        # Net Sales = Gross - Discounts - Refunds (Clover's definition)
        net_sales = gross_sales - effective_discounts - total_refunds

        # Process payouts (cash adjustments)
        # In Clover, negative amounts = money taken OUT (payout)
        # Positive amounts = money added IN (drop)
        total_payouts = Decimal('0')
        payout_breakdown = []
        for payout in payouts:
            payout_amount = Decimal(payout.get("amount", 0)) / 100
            # Negative amounts are money taken out (payouts)
            if payout_amount < 0:
                payout_amount = abs(payout_amount)
                total_payouts += payout_amount

                # Get employee name if available
                employee = payout.get("employee", {})
                employee_name = employee.get("name", "Unknown") if employee else "Unknown"

                # Get note/reason
                note = payout.get("note", "")

                payout_breakdown.append({
                    "amount": float(payout_amount),
                    "note": note or "Cash payout",
                    "employee": employee_name,
                    "timestamp": payout.get("timestamp")
                })

        # Calculate deposit amounts
        #
        # How tips flow in a restaurant:
        # 1. Customer pays $100 on card with $20 tip = $120 charged to card
        # 2. Merchant account receives $120 (minus fees) - this is the CARD DEPOSIT
        # 3. Restaurant pays employee $20 cash from the drawer = CASH TIPS PAID
        # 4. Expected Cash Deposit = Cash Sales - Cash Tips Paid - Other Payouts
        #
        # So: Card Deposit = full card amount including tips (what processor deposits)
        #     Expected Cash Deposit = Cash Sales - Tips Paid Out - Payouts
        #
        # Total Deposits = Card Deposit + Expected Cash Deposit
        #                = (Card Amount + Card Tips) + (Cash Amount - Card Tips - Payouts)
        #                = Card Amount + Cash Amount - Payouts
        #                = Total Collected - Payouts (when no variance)

        card_amount = payment_methods.get("CARD", Decimal('0'))
        card_tips = payment_tips_by_method.get("CARD", Decimal('0'))

        # Card deposit = full card amount INCLUDING tips (this is what the processor deposits)
        # Minus any refunds (which reduce the deposit)
        card_deposit = card_amount + card_tips - total_refunds

        # Cash deposit calculation
        cash_amount = payment_methods.get("CASH", Decimal('0'))

        # Cash tips paid = tips from CARD payments that are paid out to employees in cash
        # The restaurant receives card tips via the merchant account deposit,
        # then pays them out to employees from the cash drawer
        cash_tips_paid = card_tips

        # Expected Cash Deposit = Cash Sales - Cash Tips Paid Out - Payouts
        # This is what should be left in the drawer to deposit
        expected_cash_deposit = cash_amount - cash_tips_paid - total_payouts

        # Convert to float for JSON serialization
        order_types_dict = {k: float(v) for k, v in order_types.items()}
        payment_methods_dict = {k: float(v) for k, v in payment_methods.items()}
        payment_tips_dict = {k: float(v) for k, v in payment_tips_by_method.items()}
        categories_dict = {k: float(v) for k, v in categories.items()}
        discounts_dict = {k: float(-v) for k, v in discounts_breakdown.items()}  # Negative for display

        return {
            "area_id": area_id,
            "sale_date": sale_date,
            "provider": "clover",
            "total_sales": float(net_sales),  # Net Sales = Gross - Discounts - Refunds
            "total_tax": float(total_tax),
            "total_tips": float(total_tips),
            "total_discounts": float(effective_discounts),  # Calculated from Gross - Payment Net
            "total_refunds": float(total_refunds),
            "gross_sales": float(gross_sales),  # Sum of line items
            "transaction_count": transaction_count,
            "order_types": order_types_dict,
            "payment_methods": payment_methods_dict,
            "categories": categories_dict,
            "discounts": discounts_dict,
            # Deposit calculations
            "card_deposit": float(card_deposit),
            "cash_tips_paid": float(cash_tips_paid),
            "cash_payouts": float(total_payouts),
            "expected_cash_deposit": float(expected_cash_deposit),
            "payout_breakdown": payout_breakdown,
            "raw_summary": {
                "payment_count": len(payments),
                "order_count": len(processed_order_ids),
                "payout_count": len(payout_breakdown),
                "sync_date": datetime.utcnow().isoformat(),
                "payment_tips": payment_tips_dict
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

    def create_dss_from_cache(
        self,
        cached_sale: POSDailySalesCache,
        user_id: int
    ) -> DailySalesSummary:
        """
        Create Daily Sales Summary from cached POS data with GL mappings applied

        Args:
            cached_sale: Cached POS sales data
            user_id: User creating the DSS

        Returns:
            Created DailySalesSummary
        """
        # Check if DSS already exists
        existing_dss = self.db.query(DailySalesSummary).filter(
            DailySalesSummary.area_id == cached_sale.area_id,
            DailySalesSummary.business_date == cached_sale.sale_date
        ).first()

        if existing_dss:
            logger.info(f"DSS already exists for {cached_sale.sale_date} area {cached_sale.area_id}")
            return existing_dss

        # Get category mappings for this area
        category_mappings = self.db.query(POSCategoryGLMapping).filter(
            POSCategoryGLMapping.area_id == cached_sale.area_id,
            POSCategoryGLMapping.is_active == True
        ).all()

        mapping_dict = {m.pos_category: m for m in category_mappings}

        # Get tax account (2300 - Sales Tax Payable)
        tax_account = self.db.query(Account).filter(
            Account.account_number == '2300'
        ).first()

        # Get payment GL mappings for this area
        payment_mappings = self.db.query(POSPaymentGLMapping).filter(
            POSPaymentGLMapping.area_id == cached_sale.area_id,
            POSPaymentGLMapping.is_active == True
        ).all()

        payment_mapping_dict = {m.pos_payment_type.upper(): m.deposit_account_id for m in payment_mappings}

        # Fallback: Get default cash account for deposits (1000 - Cash) if no mapping found
        cash_account = self.db.query(Account).filter(
            Account.account_number == '1000'
        ).first()

        # Get deposit/payout fields from cache (calculated during sync)
        card_deposit = cached_sale.card_deposit if cached_sale.card_deposit is not None else None
        cash_tips_paid = cached_sale.cash_tips_paid if cached_sale.cash_tips_paid is not None else Decimal('0')
        cash_payouts = cached_sale.cash_payouts if cached_sale.cash_payouts is not None else Decimal('0')
        expected_cash_deposit = cached_sale.expected_cash_deposit if cached_sale.expected_cash_deposit is not None else None
        payout_breakdown = cached_sale.payout_breakdown

        # Fallback: calculate expected cash deposit from payment methods if not in cache
        if expected_cash_deposit is None and cached_sale.payment_methods:
            expected_cash = Decimal('0')
            for payment_type, amount in cached_sale.payment_methods.items():
                if payment_type.upper() == 'CASH':
                    expected_cash = Decimal(str(amount))
                    break
            expected_cash_deposit = expected_cash - cash_tips_paid - cash_payouts

        # Build enhanced payment breakdown with tips information
        # Extract payment_tips from raw_summary
        payment_tips = {}
        if cached_sale.raw_summary and 'payment_tips' in cached_sale.raw_summary:
            payment_tips = cached_sale.raw_summary['payment_tips']

        # Create payment breakdown with structure: {"CARD": {"amount": 1960.27, "tips": 339.47}, "CASH": {"amount": 429.81, "tips": 0}}
        enhanced_payment_breakdown = {}
        if cached_sale.payment_methods:
            for payment_type, amount in cached_sale.payment_methods.items():
                enhanced_payment_breakdown[payment_type] = {
                    "amount": float(amount),
                    "tips": float(payment_tips.get(payment_type, 0))
                }

        # Use net sales from cache (Clover's formula: Gross - Discounts - Refunds)
        net_sales = cached_sale.total_sales
        # Total Collected = Net Sales + Tax + Tips (this is "Amount Collected" in Clover)
        total_collected = net_sales + cached_sale.total_tax + cached_sale.total_tips

        # Use discounts from cache (already calculated as Gross - Payment Net)
        effective_discounts = cached_sale.total_discounts

        # Create DSS
        dss = DailySalesSummary(
            business_date=cached_sale.sale_date,
            area_id=cached_sale.area_id,
            pos_system=cached_sale.provider,
            gross_sales=cached_sale.gross_sales,
            discounts=effective_discounts,  # Use effective discounts (gross - net - refunds)
            refunds=cached_sale.total_refunds,
            net_sales=net_sales,
            tax_collected=cached_sale.total_tax,
            tips=cached_sale.total_tips,
            total_collected=total_collected,
            payment_breakdown=enhanced_payment_breakdown,
            category_breakdown=cached_sale.categories,
            discount_breakdown=cached_sale.discounts,
            # Deposit and payout fields
            card_deposit=card_deposit,
            cash_tips_paid=cash_tips_paid,
            cash_payouts=cash_payouts,
            payout_breakdown=payout_breakdown,
            expected_cash_deposit=expected_cash_deposit,  # Set expected cash for manager reconciliation
            status='draft',
            imported_from='clover_pos',
            imported_from_pos=True,
            imported_at=datetime.utcnow(),
            pos_sync_date=cached_sale.synced_at,
            pos_transaction_count=cached_sale.transaction_count,
            created_by=user_id,
            notes=f'Auto-imported from {cached_sale.provider.upper()} POS. {cached_sale.transaction_count} transactions.'
        )

        self.db.add(dss)
        self.db.flush()  # Get the DSS ID

        # Create sales line items from categories with GL mappings
        for category_name, amount in cached_sale.categories.items():
            mapping = mapping_dict.get(category_name)
            revenue_account_id = mapping.revenue_account_id if mapping else None

            if not revenue_account_id:
                logger.warning(f"No GL mapping found for category '{category_name}' in area {cached_sale.area_id}")

            line_item = SalesLineItem(
                dss_id=dss.id,
                category=category_name,
                gross_amount=Decimal(str(amount)),  # POS categories are already net
                discount_amount=Decimal('0'),
                net_amount=Decimal(str(amount)),
                tax_amount=Decimal('0'),  # Tax is tracked at DSS level
                revenue_account_id=revenue_account_id
            )
            self.db.add(line_item)

        # Create payment records from payment_breakdown
        # Use actual tips per payment method from raw_summary, not proportional distribution
        actual_payment_tips = {}
        if cached_sale.raw_summary and 'payment_tips' in cached_sale.raw_summary:
            actual_payment_tips = cached_sale.raw_summary['payment_tips']

        for payment_type, amount in cached_sale.payment_methods.items():
            # Use actual tips for this payment method (defaults to 0 if not found)
            tips_for_payment = Decimal(str(actual_payment_tips.get(payment_type, 0)))

            # Look up deposit account from GL mapping, fallback to cash account
            payment_type_upper = payment_type.upper()
            deposit_account_id = payment_mapping_dict.get(payment_type_upper)

            if not deposit_account_id:
                logger.warning(f"No GL mapping found for payment type '{payment_type}' in area {cached_sale.area_id}, using default cash account")
                deposit_account_id = cash_account.id if cash_account else None

            payment = SalesPayment(
                dss_id=dss.id,
                payment_type=payment_type_upper,
                amount=Decimal(str(amount)),
                tips=tips_for_payment,
                deposit_account_id=deposit_account_id
            )
            self.db.add(payment)

        self.db.commit()
        self.db.refresh(dss)

        logger.info(f"Created DSS #{dss.id} for {cached_sale.sale_date} area {cached_sale.area_id}")
        return dss
