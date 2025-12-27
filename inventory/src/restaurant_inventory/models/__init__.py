"""
Restaurant Inventory Models

Architecture (Location-Aware Costing - Dec 25, 2025):
- Hub owns: UOM (global), Categories (global), Vendor Items, Invoices
- Inventory owns: Master Items, Count Units, Location Costs, Locations

Note: Invoice/VendorItem/VendorAlias models moved to _deprecated/ folder.
Use Integration Hub for invoice processing and vendor items.
"""

from .location import Location
from .storage_area import StorageArea, StorageAreaItem
from .user import User
from .item import MasterItem
from .master_item_count_unit import MasterItemCountUnit
from .master_item_location_cost import MasterItemLocationCost, MasterItemLocationCostHistory
from .inventory import Inventory
from .pos_sale import POSSale, POSSaleItem
from .inventory_transaction import InventoryTransaction, TransactionType
from .transfer import Transfer
from .waste import WasteRecord
from .audit_log import AuditLog
from .vendor import Vendor
from .recipe import Recipe, RecipeIngredient, RecipeCategory
from .category import Category
from .count_template import CountTemplate
from .count_session import CountSession
from .unit_of_measure import UnitCategory, UnitOfMeasure
from .role import Role
from .item_unit_conversion import ItemUnitConversion

# DEPRECATED imports - these models exist in _deprecated/ folder
# Only import if needed for backward compatibility during migration
try:
    from ._deprecated.vendor_item import VendorItem
    from ._deprecated.vendor_alias import VendorAlias
    from ._deprecated.invoice import Invoice, InvoiceItem, InvoiceStatus
except ImportError:
    # Models may not exist in all deployments
    VendorItem = None
    VendorAlias = None
    Invoice = None
    InvoiceItem = None
    InvoiceStatus = None

__all__ = [
    # Core
    "Location", "StorageArea", "StorageAreaItem", "User",
    # Items and Costing
    "MasterItem", "MasterItemCountUnit", "MasterItemLocationCost", "MasterItemLocationCostHistory",
    # Inventory Operations
    "Inventory", "POSSale", "POSSaleItem", "InventoryTransaction", "TransactionType",
    "Transfer", "WasteRecord",
    # Recipes
    "Recipe", "RecipeIngredient", "RecipeCategory",
    # Counting
    "CountTemplate", "CountSession",
    # Other
    "AuditLog", "Vendor", "Category", "UnitCategory", "UnitOfMeasure",
    "Role", "ItemUnitConversion",
    # DEPRECATED (kept for backward compatibility)
    "VendorItem", "VendorAlias", "Invoice", "InvoiceItem", "InvoiceStatus",
]
