"""
Restaurant Inventory Models

Architecture (Location-Aware Costing):
- Hub owns: UOM (global), Categories (global), Vendor Items (per location)
- Inventory owns: Master Items, Count Units, Location Costs
"""

from .location import Location
from .storage_area import StorageArea, StorageAreaItem
from .user import User
from .item import MasterItem
from .master_item_count_unit import MasterItemCountUnit
from .master_item_location_cost import MasterItemLocationCost, MasterItemLocationCostHistory
from .vendor_item import VendorItem  # DEPRECATED: Use Hub's VendorItem
from .inventory import Inventory
from .pos_sale import POSSale, POSSaleItem
from .inventory_transaction import InventoryTransaction, TransactionType
from .transfer import Transfer
from .waste import WasteRecord
from .audit_log import AuditLog
from .vendor import Vendor
from .vendor_alias import VendorAlias
from .invoice import Invoice, InvoiceItem, InvoiceStatus
from .recipe import Recipe, RecipeIngredient, RecipeCategory
from .category import Category  # DEPRECATED: Use Hub's Category
from .count_template import CountTemplate
from .count_session import CountSession
from .unit_of_measure import UnitCategory, UnitOfMeasure  # DEPRECATED: Use Hub's UnitOfMeasure
from .role import Role
from .item_unit_conversion import ItemUnitConversion

__all__ = [
    # Core
    "Location", "StorageArea", "StorageAreaItem", "User",
    # Items and Costing (NEW)
    "MasterItem", "MasterItemCountUnit", "MasterItemLocationCost", "MasterItemLocationCostHistory",
    # Inventory Operations
    "Inventory", "POSSale", "POSSaleItem", "InventoryTransaction", "TransactionType",
    "Transfer", "WasteRecord",
    # Recipes
    "Recipe", "RecipeIngredient", "RecipeCategory",
    # Counting
    "CountTemplate", "CountSession",
    # DEPRECATED (kept for migration)
    "VendorItem",  # Use Hub's HubVendorItem
    "Category",  # Use Hub's Category
    "UnitCategory", "UnitOfMeasure",  # Use Hub's UnitOfMeasure
    # Other
    "AuditLog", "Vendor", "VendorAlias", "Invoice", "InvoiceItem", "InvoiceStatus",
    "Role", "ItemUnitConversion",
]
