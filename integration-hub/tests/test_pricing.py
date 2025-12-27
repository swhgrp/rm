"""
Tests for the pricing service.
"""

import pytest
from decimal import Decimal
from integration_hub.services.pricing import (
    UnitInfo,
    ItemInfo,
    VendorItemInfo,
    convert_units,
    calculate_cost_per_stock_unit,
    calculate_cost_per_content_base,
    parse_invoice_line_price,
    calculate_vendor_item_pricing
)


class TestUnitConversion:
    """Test unit conversion functions."""

    def test_convert_gallons_to_fluid_ounces(self):
        """Test converting gallons to fluid ounces."""
        gallon = UnitInfo(
            id=5, name="Gallon", abbreviation="gal",
            dimension="volume", to_base_factor=Decimal("128.0")
        )
        fl_oz = UnitInfo(
            id=9, name="Fluid Ounce", abbreviation="fl oz",
            dimension="volume", to_base_factor=Decimal("1.0")
        )

        result = convert_units(Decimal("2"), gallon, fl_oz)
        assert result == Decimal("256.0")

    def test_convert_pounds_to_ounces(self):
        """Test converting pounds to ounces."""
        pound = UnitInfo(
            id=1, name="Pound", abbreviation="lb",
            dimension="weight", to_base_factor=Decimal("16.0")
        )
        ounce = UnitInfo(
            id=2, name="Ounce", abbreviation="oz",
            dimension="weight", to_base_factor=Decimal("1.0")
        )

        result = convert_units(Decimal("5"), pound, ounce)
        assert result == Decimal("80.0")

    def test_convert_liters_to_milliliters(self):
        """Test converting liters to milliliters."""
        liter = UnitInfo(
            id=12, name="Liter", abbreviation="L",
            dimension="volume", to_base_factor=Decimal("33.814")
        )
        ml = UnitInfo(
            id=13, name="Milliliter", abbreviation="mL",
            dimension="volume", to_base_factor=Decimal("0.033814")
        )

        result = convert_units(Decimal("1"), liter, ml)
        # 1L = 1000mL (33.814 / 0.033814 ≈ 1000)
        assert abs(result - Decimal("1000")) < Decimal("1")

    def test_convert_different_dimensions_raises_error(self):
        """Test that converting between different dimensions raises an error."""
        gallon = UnitInfo(
            id=5, name="Gallon", abbreviation="gal",
            dimension="volume", to_base_factor=Decimal("128.0")
        )
        pound = UnitInfo(
            id=1, name="Pound", abbreviation="lb",
            dimension="weight", to_base_factor=Decimal("16.0")
        )

        with pytest.raises(ValueError, match="Cannot convert between dimensions"):
            convert_units(Decimal("1"), gallon, pound)


class TestCostCalculations:
    """Test cost calculation functions."""

    def test_calculate_cost_per_stock_unit(self):
        """Test calculating cost per stock unit from case price."""
        # $306 case / 12 bottles = $25.50 per bottle
        result = calculate_cost_per_stock_unit(
            purchase_price=Decimal("306.00"),
            stock_units_per_purchase_unit=Decimal("12")
        )
        assert result == Decimal("25.50")

    def test_calculate_cost_per_content_base(self):
        """Test calculating cost per base content unit."""
        ml = UnitInfo(
            id=13, name="Milliliter", abbreviation="mL",
            dimension="volume", to_base_factor=Decimal("0.033814")
        )

        # $25.50 per bottle / 750ml per bottle
        # = $25.50 / (750 * 0.033814 fl oz)
        # = $25.50 / 25.36 fl oz
        # ≈ $1.01 per fl oz
        result = calculate_cost_per_content_base(
            cost_per_stock_unit=Decimal("25.50"),
            stock_content_qty=Decimal("750"),
            stock_content_uom=ml
        )

        # Should be approximately $1.01 per fl oz
        assert abs(result - Decimal("1.006")) < Decimal("0.01")


class TestParseInvoiceLine:
    """Test invoice line parsing."""

    def test_parse_invoice_line_basic(self):
        """Test parsing a basic invoice line."""
        vendor_item = VendorItemInfo(
            purchase_uom_id=22,  # Case
            stock_units_per_purchase_unit=Decimal("12"),
            last_purchase_price=Decimal("306.00")
        )

        # Invoice: 2 cases @ $612 total
        result = parse_invoice_line_price(
            line_total=Decimal("612.00"),
            line_qty=Decimal("2"),
            vendor_item=vendor_item
        )

        # 2 cases * 12 bottles = 24 bottles
        # $612 / 24 = $25.50 per bottle
        assert result.cost_per_stock_unit == Decimal("25.50")

    def test_parse_invoice_line_with_content(self):
        """Test parsing invoice line with content info for per-oz pricing."""
        ml = UnitInfo(
            id=13, name="Milliliter", abbreviation="mL",
            dimension="volume", to_base_factor=Decimal("0.033814")
        )

        vendor_item = VendorItemInfo(
            purchase_uom_id=22,  # Case
            stock_units_per_purchase_unit=Decimal("12"),
            last_purchase_price=Decimal("306.00")
        )

        item = ItemInfo(
            stock_uom_id=26,  # Bottle 750ml
            stock_uom_name="Bottle 750ml",
            stock_content_qty=Decimal("750"),
            stock_content_uom_id=13
        )

        result = parse_invoice_line_price(
            line_total=Decimal("612.00"),
            line_qty=Decimal("2"),
            vendor_item=vendor_item,
            item=item,
            content_uom=ml
        )

        assert result.cost_per_stock_unit == Decimal("25.50")
        # Per fl oz: $25.50 / (750 * 0.033814) ≈ $1.01
        assert result.cost_per_content_base is not None
        assert abs(result.cost_per_content_base - Decimal("1.006")) < Decimal("0.01")


class TestVendorItemPricing:
    """Test vendor item pricing calculations."""

    def test_calculate_vendor_item_pricing_basic(self):
        """Test basic vendor item pricing calculation."""
        result = calculate_vendor_item_pricing(
            last_purchase_price=Decimal("306.00"),
            stock_units_per_purchase_unit=Decimal("12")
        )

        assert result['purchase_price'] == Decimal("306.00")
        assert result['cost_per_stock_unit'] == Decimal("25.50")

    def test_calculate_vendor_item_pricing_with_content(self):
        """Test vendor item pricing with content info."""
        result = calculate_vendor_item_pricing(
            last_purchase_price=Decimal("306.00"),
            stock_units_per_purchase_unit=Decimal("12"),
            stock_content_qty=Decimal("750"),
            stock_content_to_base=Decimal("0.033814")  # ml to fl oz
        )

        assert result['purchase_price'] == Decimal("306.00")
        assert result['cost_per_stock_unit'] == Decimal("25.50")
        assert result['cost_per_content_base'] is not None
        # ~$1.01 per fl oz
        assert abs(result['cost_per_content_base'] - Decimal("1.006")) < Decimal("0.01")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
