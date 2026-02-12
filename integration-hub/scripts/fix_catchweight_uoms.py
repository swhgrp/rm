"""
Fix UOMs for catch-weight vendor items.

Catch-weight items are priced per LB with variable weight per shipment.
For these items, LB should be the default UOM (cf=1), not CS.

This script:
1. Identifies known catch-weight GFS items (SKU 649601 and similar)
2. Swaps their default UOM to LB
3. Fixes purchase_unit_abbr to 'lb'
"""
import sys
sys.path.insert(0, "/app/src")

from integration_hub.db.database import SessionLocal
from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.models.vendor_item_uom import VendorItemUOM
from integration_hub.models.unit_of_measure import UnitOfMeasure
from sqlalchemy import text

# Known catch-weight SKUs for GFS (vendor_id=5)
# These are variable-weight items priced per pound
CATCHWEIGHT_SKUS = [
    "649601",  # Beef Bottom Sirloin Butt, Whole, USDA Choice Angus, Flap, Boneless
]


def main():
    db = SessionLocal()
    try:
        # Get LB UOM id
        lb_uom = db.query(UnitOfMeasure).filter(
            UnitOfMeasure.abbreviation == "lb"
        ).first()
        if not lb_uom:
            print("ERROR: LB UOM not found")
            return
        print(f"LB UOM id: {lb_uom.id}")

        fixed_count = 0

        for sku in CATCHWEIGHT_SKUS:
            # Find all vendor items with this SKU for GFS
            items = db.query(HubVendorItem).filter(
                HubVendorItem.vendor_id == 5,
                HubVendorItem.vendor_sku == sku
            ).all()

            for vi in items:
                print(f"\nVI:{vi.id} SKU:{vi.vendor_sku} | {vi.vendor_product_name}")
                print(f"  Current: purchase_unit_abbr={vi.purchase_unit_abbr}, units_per_case={vi.units_per_case}")

                # Get current UOMs
                uoms = db.query(VendorItemUOM).filter(
                    VendorItemUOM.vendor_item_id == vi.id,
                    VendorItemUOM.is_active == True
                ).all()

                lb_entry = None
                cs_entry = None
                for u in uoms:
                    uom_obj = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == u.uom_id).first()
                    abbr = uom_obj.abbreviation if uom_obj else "?"
                    print(f"  UOM:{u.id} = {abbr}(cf={u.conversion_factor}) default={u.is_default}")
                    if abbr == "lb":
                        lb_entry = u
                    elif abbr == "cs":
                        cs_entry = u

                # Fix: Set LB as default, CS as non-default
                if lb_entry and cs_entry:
                    if cs_entry.is_default and not lb_entry.is_default:
                        cs_entry.is_default = False
                        lb_entry.is_default = True
                        print(f"  -> Swapped: LB is now default, CS is non-default")
                    elif lb_entry.is_default:
                        print(f"  -> LB already default, no change needed")
                elif lb_entry and not cs_entry:
                    lb_entry.is_default = True
                    print(f"  -> Set LB as default (no CS entry)")
                elif not lb_entry:
                    # Create LB entry
                    new_lb = VendorItemUOM(
                        vendor_item_id=vi.id,
                        uom_id=lb_uom.id,
                        conversion_factor=1.0,
                        is_default=True,
                        is_active=True
                    )
                    db.add(new_lb)
                    if cs_entry:
                        cs_entry.is_default = False
                    print(f"  -> Created LB UOM entry as default")

                # Fix purchase_unit_abbr
                if vi.purchase_unit_abbr != "lb":
                    old = vi.purchase_unit_abbr
                    vi.purchase_unit_abbr = "lb"
                    # Also update purchase_unit_id to LB
                    vi.purchase_unit_id = lb_uom.id
                    vi.purchase_unit_name = "Pound"
                    print(f"  -> Fixed purchase_unit_abbr: {old} -> lb")

                fixed_count += 1

        db.commit()
        print(f"\nDone. Fixed {fixed_count} vendor items.")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
