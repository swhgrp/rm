"""
Inventory Deduction Service

Handles automatic inventory deduction when POS sales are synced.
Supports both direct master item deduction and recipe-based ingredient deduction.
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Dict, Optional
from decimal import Decimal
import logging

from restaurant_inventory.models.inventory import Inventory
from restaurant_inventory.models.inventory_transaction import InventoryTransaction, TransactionType
from restaurant_inventory.models.pos_sale import POSSale, POSSaleItem, POSItemMapping
from restaurant_inventory.models.recipe import Recipe, RecipeIngredient
from restaurant_inventory.models.item import MasterItem

logger = logging.getLogger(__name__)


class InventoryDeductionService:
    """Service for deducting inventory based on POS sales"""

    def __init__(self, db: Session):
        self.db = db

    def process_sale(self, sale: POSSale) -> Dict[str, any]:
        """
        Process a POS sale and deduct inventory for all mapped items.

        Returns a summary of what was deducted.
        """
        results = {
            "sale_id": sale.id,
            "items_processed": 0,
            "items_deducted": 0,
            "items_skipped": 0,
            "transactions_created": 0,
            "errors": []
        }

        for sale_item in sale.line_items:
            results["items_processed"] += 1

            try:
                # Find mapping for this POS item
                mapping = self._get_item_mapping(sale_item.pos_item_id, sale.location_id)

                if not mapping:
                    results["items_skipped"] += 1
                    logger.debug(f"No mapping found for POS item {sale_item.pos_item_id}")
                    continue

                if not mapping.is_active:
                    results["items_skipped"] += 1
                    logger.debug(f"Mapping inactive for POS item {sale_item.pos_item_id}")
                    continue

                # Calculate quantity with portion multiplier
                quantity_to_deduct = float(sale_item.quantity) * float(mapping.portion_multiplier)

                # Deduct based on mapping type
                if mapping.master_item_id:
                    # Direct master item deduction
                    transactions = self._deduct_master_item(
                        master_item_id=mapping.master_item_id,
                        quantity=quantity_to_deduct,
                        location_id=sale.location_id,
                        sale=sale,
                        sale_item=sale_item
                    )
                    results["transactions_created"] += len(transactions)

                elif mapping.recipe_id:
                    # Recipe-based ingredient deduction
                    transactions = self._deduct_recipe_ingredients(
                        recipe_id=mapping.recipe_id,
                        quantity=quantity_to_deduct,
                        location_id=sale.location_id,
                        sale=sale,
                        sale_item=sale_item
                    )
                    results["transactions_created"] += len(transactions)

                results["items_deducted"] += 1

            except Exception as e:
                error_msg = f"Error processing item {sale_item.pos_item_id}: {str(e)}"
                logger.error(error_msg)
                results["errors"].append(error_msg)

        return results

    def _get_item_mapping(self, pos_item_id: str, location_id: Optional[int]) -> Optional[POSItemMapping]:
        """Get the item mapping for a POS item, preferring location-specific mappings"""

        # First try location-specific mapping
        if location_id:
            mapping = self.db.query(POSItemMapping).filter(
                and_(
                    POSItemMapping.pos_item_id == pos_item_id,
                    POSItemMapping.location_id == location_id,
                    POSItemMapping.is_active == True
                )
            ).first()

            if mapping:
                return mapping

        # Fall back to global mapping (location_id is None)
        mapping = self.db.query(POSItemMapping).filter(
            and_(
                POSItemMapping.pos_item_id == pos_item_id,
                POSItemMapping.location_id == None,
                POSItemMapping.is_active == True
            )
        ).first()

        return mapping

    def _deduct_master_item(
        self,
        master_item_id: int,
        quantity: float,
        location_id: Optional[int],
        sale: POSSale,
        sale_item: POSSaleItem
    ) -> List[InventoryTransaction]:
        """
        Deduct a master item from inventory.
        Returns list of transactions created.

        Uses pessimistic locking (SELECT FOR UPDATE) to prevent race conditions
        when multiple concurrent requests try to deduct from the same inventory.
        """
        transactions = []

        # Get or create inventory record for this item at this location
        # Use FOR UPDATE to lock the row and prevent concurrent modifications
        inventory = self.db.query(Inventory).filter(
            and_(
                Inventory.master_item_id == master_item_id,
                Inventory.location_id == location_id
            )
        ).with_for_update().first()

        if not inventory:
            # Create inventory record if it doesn't exist (starting at 0)
            inventory = Inventory(
                master_item_id=master_item_id,
                location_id=location_id,
                current_quantity=0
            )
            self.db.add(inventory)
            self.db.flush()
            logger.info(f"Created inventory record for item {master_item_id} at location {location_id}")

        # Record before/after quantities
        quantity_before = float(inventory.current_quantity)
        quantity_after = quantity_before - quantity

        # Update inventory
        inventory.current_quantity = Decimal(str(quantity_after))

        # Create transaction record
        transaction = InventoryTransaction(
            master_item_id=master_item_id,
            location_id=location_id,
            storage_area_id=inventory.storage_area_id,
            transaction_type=TransactionType.POS_SALE.value,
            quantity_change=Decimal(str(-quantity)),  # Negative for deduction
            quantity_before=Decimal(str(quantity_before)),
            quantity_after=Decimal(str(quantity_after)),
            unit_cost=inventory.unit_cost,
            total_cost=inventory.unit_cost * Decimal(str(quantity)) if inventory.unit_cost else None,
            pos_sale_id=sale.id,
            pos_sale_item_id=sale_item.id,
            reason=f"POS Sale: {sale_item.item_name}",
            notes=f"Order #{sale.order_number or sale.pos_order_id}"
        )

        self.db.add(transaction)
        transactions.append(transaction)

        logger.info(
            f"Deducted {quantity} of item {master_item_id} at location {location_id}. "
            f"Before: {quantity_before}, After: {quantity_after}"
        )

        return transactions

    def _deduct_recipe_ingredients(
        self,
        recipe_id: int,
        quantity: float,
        location_id: Optional[int],
        sale: POSSale,
        sale_item: POSSaleItem
    ) -> List[InventoryTransaction]:
        """
        Deduct all ingredients for a recipe from inventory.
        Quantity is the number of portions sold.
        Returns list of transactions created.
        """
        transactions = []

        # Get recipe with ingredients
        recipe = self.db.query(Recipe).filter(Recipe.id == recipe_id).first()

        if not recipe:
            logger.error(f"Recipe {recipe_id} not found")
            return transactions

        # Deduct each ingredient
        for ingredient in recipe.ingredients:
            # Calculate ingredient quantity needed
            # ingredient.quantity is per recipe yield, multiply by portions sold
            ingredient_qty = float(ingredient.quantity) * quantity

            # Deduct this ingredient
            ingredient_transactions = self._deduct_master_item(
                master_item_id=ingredient.master_item_id,
                quantity=ingredient_qty,
                location_id=location_id,
                sale=sale,
                sale_item=sale_item
            )

            # Update transaction to include recipe reference
            for txn in ingredient_transactions:
                txn.recipe_id = recipe_id
                txn.reason = f"POS Sale: {sale_item.item_name} (Recipe: {recipe.name})"

            transactions.extend(ingredient_transactions)

        logger.info(
            f"Deducted ingredients for recipe {recipe.name} (x{quantity}) at location {location_id}. "
            f"Processed {len(recipe.ingredients)} ingredients."
        )

        return transactions

    def process_bulk_sales(self, sales: List[POSSale]) -> Dict[str, any]:
        """
        Process multiple sales in a batch.
        Commits after all sales are processed.
        """
        summary = {
            "sales_processed": 0,
            "total_items_processed": 0,
            "total_items_deducted": 0,
            "total_items_skipped": 0,
            "total_transactions_created": 0,
            "errors": []
        }

        for sale in sales:
            try:
                result = self.process_sale(sale)
                summary["sales_processed"] += 1
                summary["total_items_processed"] += result["items_processed"]
                summary["total_items_deducted"] += result["items_deducted"]
                summary["total_items_skipped"] += result["items_skipped"]
                summary["total_transactions_created"] += result["transactions_created"]
                summary["errors"].extend(result["errors"])

                # Mark sale as inventory deducted
                sale.inventory_deducted = True

            except Exception as e:
                error_msg = f"Error processing sale {sale.id}: {str(e)}"
                logger.error(error_msg)
                summary["errors"].append(error_msg)

        # Commit all changes
        try:
            self.db.commit()
            logger.info(
                f"Bulk deduction complete: {summary['sales_processed']} sales, "
                f"{summary['total_items_deducted']} items deducted, "
                f"{summary['total_transactions_created']} transactions created"
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error committing bulk deduction: {str(e)}")
            summary["errors"].append(f"Commit failed: {str(e)}")

        return summary
