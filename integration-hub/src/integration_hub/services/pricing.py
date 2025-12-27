"""
Pricing Service for UOM conversions and cost calculations.

This module implements the pricing model from the spec:
- Converts between units using dimension-based factors
- Calculates cost per stock unit from purchase prices
- Normalizes invoice line items to stock unit costs
"""

from decimal import Decimal
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class UnitInfo:
    """Information about a unit of measure."""
    id: int
    name: str
    abbreviation: str
    dimension: str  # count, volume, weight, length
    to_base_factor: Decimal  # Conversion to base unit of this dimension


@dataclass
class ItemInfo:
    """Information about a master item's stock unit configuration."""
    stock_uom_id: int
    stock_uom_name: str
    stock_content_qty: Optional[Decimal] = None  # e.g., 750 for 750ml bottle
    stock_content_uom_id: Optional[int] = None  # e.g., ID of milliliter


@dataclass
class VendorItemInfo:
    """Information about how a vendor sells an item."""
    purchase_uom_id: int  # What you buy (case, each, etc.)
    stock_units_per_purchase_unit: Decimal  # How many stock units per purchase
    last_purchase_price: Decimal  # Price per purchase unit


@dataclass
class PricingResult:
    """Result of a pricing calculation."""
    cost_per_stock_unit: Decimal  # Cost per individual stock unit
    cost_per_content_base: Optional[Decimal] = None  # Cost per base content unit (e.g., per fl oz)


def convert_units(
    quantity: Decimal,
    from_unit: UnitInfo,
    to_unit: UnitInfo
) -> Decimal:
    """
    Convert a quantity from one unit to another.
    Both units must have the same dimension.

    Example: 2 gallons -> fluid ounces
        = 2 * 128.0 / 1.0 = 256 fl oz
    """
    if from_unit.dimension != to_unit.dimension:
        raise ValueError(
            f"Cannot convert between dimensions: {from_unit.dimension} -> {to_unit.dimension}"
        )

    if not from_unit.to_base_factor or not to_unit.to_base_factor:
        raise ValueError("Missing to_base_factor for conversion")

    # Convert to base units, then to target units
    base_quantity = quantity * from_unit.to_base_factor
    return base_quantity / to_unit.to_base_factor


def calculate_cost_per_stock_unit(
    purchase_price: Decimal,
    stock_units_per_purchase_unit: Decimal
) -> Decimal:
    """
    Calculate the cost per stock unit from purchase price.

    Example: $306 case / 12 bottles per case = $25.50 per bottle
    """
    if stock_units_per_purchase_unit <= 0:
        raise ValueError("stock_units_per_purchase_unit must be positive")

    return purchase_price / stock_units_per_purchase_unit


def calculate_cost_per_content_base(
    cost_per_stock_unit: Decimal,
    stock_content_qty: Decimal,
    stock_content_uom: UnitInfo
) -> Decimal:
    """
    Calculate cost per base unit of content.

    Example: $25.50 per bottle / 750ml per bottle / 0.033814 fl oz/ml
        = $25.50 / (750 * 0.033814) = $1.01 per fl oz
    """
    if stock_content_qty <= 0:
        raise ValueError("stock_content_qty must be positive")

    if not stock_content_uom.to_base_factor:
        raise ValueError("Missing to_base_factor for content UOM")

    # Convert content to base units
    base_content = stock_content_qty * stock_content_uom.to_base_factor
    return cost_per_stock_unit / base_content


def parse_invoice_line_price(
    line_total: Decimal,
    line_qty: Decimal,
    vendor_item: VendorItemInfo,
    item: Optional[ItemInfo] = None,
    content_uom: Optional[UnitInfo] = None
) -> PricingResult:
    """
    Parse an invoice line item and calculate costs.

    Args:
        line_total: Total price for this line item
        line_qty: Quantity ordered (in purchase units)
        vendor_item: Vendor item configuration
        item: Master item configuration (optional, for content-based pricing)
        content_uom: Content UOM info (optional, for content-based pricing)

    Returns:
        PricingResult with cost per stock unit and optional cost per content base

    Example:
        Invoice line: 2 cases of Tito's @ $612 total
        vendor_item: 12 bottles per case
        item: 750ml per bottle
        content_uom: milliliter (0.033814 fl oz/ml)

        Result:
            cost_per_stock_unit = $612 / (2 * 12) = $25.50 per bottle
            cost_per_content_base = $25.50 / (750 * 0.033814) = $1.01 per fl oz
    """
    if line_qty <= 0:
        raise ValueError("line_qty must be positive")

    # Calculate total stock units purchased
    total_stock_units = line_qty * vendor_item.stock_units_per_purchase_unit

    # Cost per stock unit
    cost_per_stock_unit = line_total / total_stock_units

    # Cost per content base (if item has content info)
    cost_per_content_base = None
    if (item and item.stock_content_qty and item.stock_content_uom_id and
            content_uom and content_uom.to_base_factor):
        cost_per_content_base = calculate_cost_per_content_base(
            cost_per_stock_unit,
            item.stock_content_qty,
            content_uom
        )

    return PricingResult(
        cost_per_stock_unit=cost_per_stock_unit,
        cost_per_content_base=cost_per_content_base
    )


def format_cost_display(
    cost_per_stock_unit: Decimal,
    stock_uom_name: str,
    cost_per_content_base: Optional[Decimal] = None,
    content_base_uom_name: Optional[str] = None
) -> str:
    """
    Format cost for display.

    Example:
        $25.50/bottle ($1.01/fl oz)
    """
    display = f"${cost_per_stock_unit:.2f}/{stock_uom_name}"

    if cost_per_content_base and content_base_uom_name:
        display += f" (${cost_per_content_base:.2f}/{content_base_uom_name})"

    return display


# === Helper functions for database queries ===

def get_uom_info_from_db(db, uom_id: int) -> Optional[UnitInfo]:
    """
    Get UnitInfo from database by ID.
    Works with both Hub and Inventory database connections.
    """
    try:
        cursor = db.execute("""
            SELECT id, name, abbreviation, dimension, to_base_factor
            FROM units_of_measure
            WHERE id = %s
        """, (uom_id,))
        row = cursor.fetchone()
        if row:
            return UnitInfo(
                id=row[0],
                name=row[1],
                abbreviation=row[2],
                dimension=row[3],
                to_base_factor=Decimal(str(row[4])) if row[4] else None
            )
    except Exception:
        pass
    return None


def calculate_vendor_item_pricing(
    last_purchase_price: Decimal,
    stock_units_per_purchase_unit: Decimal,
    stock_content_qty: Optional[Decimal] = None,
    stock_content_to_base: Optional[Decimal] = None
) -> Dict[str, Any]:
    """
    Calculate all pricing metrics for a vendor item.

    Returns dict with:
        - cost_per_stock_unit: Cost per individual stock unit
        - cost_per_content_base: Cost per base unit of content (if applicable)
        - purchase_price: Original purchase price per purchase unit
    """
    result = {
        'purchase_price': last_purchase_price,
        'cost_per_stock_unit': None,
        'cost_per_content_base': None
    }

    if stock_units_per_purchase_unit and stock_units_per_purchase_unit > 0:
        result['cost_per_stock_unit'] = last_purchase_price / stock_units_per_purchase_unit

        if (stock_content_qty and stock_content_qty > 0 and
                stock_content_to_base and stock_content_to_base > 0):
            base_content = stock_content_qty * stock_content_to_base
            result['cost_per_content_base'] = result['cost_per_stock_unit'] / base_content

    return result
