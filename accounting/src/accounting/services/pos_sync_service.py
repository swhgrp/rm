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

                # Calculate timestamps for current_date range
                day_start_ms = int(datetime.combine(current_date, datetime.min.time()).timestamp() * 1000)
                day_end_ms = int(datetime.combine(current_date, datetime.max.time()).timestamp() * 1000)

                # Filter for PAID orders within the current date
                paid_orders = []
                for order in orders:
                    # Check if order is LOCKED (completed/paid)
                    if order.get("state", "").upper() != "LOCKED":
                        continue

                    # Get order timestamp (use clientCreatedTime which is when order was placed)
                    order_time = order.get("clientCreatedTime", 0)

                    # Only include orders from the current date
                    if day_start_ms <= order_time <= day_end_ms:
                        paid_orders.append(order)

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

            # For tax and tips, get from first successful payment only to avoid duplication
            order_tax = Decimal('0')
            order_tip = Decimal('0')

            if order.get("payments") and order["payments"].get("elements"):
                # Track payment methods by summing all successful payments
                for payment in order["payments"]["elements"]:
                    if payment.get("result") == "SUCCESS":
                        payment_amount = Decimal(payment.get("amount", 0)) / 100
                        payment_tip = Decimal(payment.get("tipAmount", 0) or 0) / 100

                        # Get tax and tip from first payment only (they're order-level, not payment-level)
                        if order_tax == 0:
                            order_tax = Decimal(payment.get("taxAmount", 0) or 0) / 100
                        if order_tip == 0:
                            order_tip = Decimal(payment.get("tipAmount", 0) or 0) / 100

                        # Track payment method - get actual tender type from Clover
                        tender = payment.get("tender", {})
                        tender_label = tender.get("label", "").upper() if tender else ""

                        # Categorize payment type based on tender label
                        # Clover uses: "Cash", "Credit Card", "Debit Card", "Gift Card", "Check", etc.
                        payment_key = None
                        if tender_label == "CASH":
                            payment_key = "CASH"
                        elif tender_label in ["CREDIT CARD", "DEBIT CARD"]:
                            # Combine credit and debit cards into CARD
                            payment_key = "CARD"
                        elif tender_label in ["GIFT CARD"]:
                            payment_key = "GIFT_CARD"
                        elif tender_label:
                            # Use the tender label for any other payment types
                            # Replace spaces with underscores for consistency
                            payment_key = tender_label.replace(" ", "_")
                        else:
                            # Default to cash if we can't determine
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

        # Calculate expected cash deposit (cash payment amount only, excluding tips on cash)
        # This is used for manager cash reconciliation
        expected_cash = Decimal('0')
        if cached_sale.payment_methods:
            for payment_type, amount in cached_sale.payment_methods.items():
                if payment_type.upper() == 'CASH':
                    expected_cash = Decimal(str(amount))
                    break

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

        # Calculate net sales and total collected
        # Net Sales = Gross Sales - Discounts - Refunds
        net_sales = cached_sale.gross_sales - cached_sale.total_discounts - cached_sale.total_refunds
        # Total Collected = Net Sales + Tax + Tips
        total_collected = net_sales + cached_sale.total_tax + cached_sale.total_tips

        # Create DSS
        dss = DailySalesSummary(
            business_date=cached_sale.sale_date,
            area_id=cached_sale.area_id,
            pos_system=cached_sale.provider,
            gross_sales=cached_sale.gross_sales,
            discounts=cached_sale.total_discounts,
            refunds=cached_sale.total_refunds,  # Use actual refunds from cache
            net_sales=net_sales,
            tax_collected=cached_sale.total_tax,
            tips=cached_sale.total_tips,
            total_collected=total_collected,
            payment_breakdown=enhanced_payment_breakdown,
            category_breakdown=cached_sale.categories,
            discount_breakdown=cached_sale.discounts,
            expected_cash_deposit=expected_cash,  # Set expected cash for manager reconciliation
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
        total_payments = sum(Decimal(str(amt)) for amt in cached_sale.payment_methods.values())

        for payment_type, amount in cached_sale.payment_methods.items():
            # Distribute tips proportionally
            payment_pct = Decimal(str(amount)) / total_payments if total_payments > 0 else Decimal('0')
            payment_tips = cached_sale.total_tips * payment_pct

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
                tips=payment_tips,
                deposit_account_id=deposit_account_id
            )
            self.db.add(payment)

        self.db.commit()
        self.db.refresh(dss)

        logger.info(f"Created DSS #{dss.id} for {cached_sale.sale_date} area {cached_sale.area_id}")
        return dss
