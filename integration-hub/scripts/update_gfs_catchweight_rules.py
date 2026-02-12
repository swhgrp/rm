"""
Update GFS vendor parsing rules to handle catch-weight items.

Catch-weight items (fresh meat, seafood) have variable weight per shipment.
The invoice shows per-lb price and actual weight, not a fixed case price.
"""
import sys
sys.path.insert(0, "/app/src")

from integration_hub.db.database import SessionLocal
from integration_hub.models.vendor_parsing_rule import VendorParsingRule

NEW_AI_INSTRUCTIONS = """For Gordon Food Service invoices:
- Use "Qty Ship" column for quantity (NOT "Qty Ord" or pack size numbers)
- "Qty Ord" is quantity ordered, "Qty Ship" is quantity actually shipped
- Pack Size like "2x5 LB" or "6x5 LB" means packaging (bags per case), NOT quantity
- Item Code is in the first column, NOT the UPC barcode
- Unit Price is the CASE price (for standard items)

CRITICAL - DO NOT confuse these with quantity:
- Pack size numbers: "2x5 LB" means 2 bags of 5lb = NOT quantity
- Product specs: "80/20" or "75/25" is lean/fat ratio for beef = NOT quantity
- Counts in description: "8#" or "8 oz" is item size = NOT quantity

The ONLY valid quantity source is the "Qty Ship" column, which is typically 1-10 cases.

*** CATCH-WEIGHT ITEMS (CRITICAL) ***
Some GFS items are CATCH-WEIGHT (variable weight) — mostly fresh/frozen meat, seafood, and produce.
These are priced PER POUND, not per case, and the actual weight varies per shipment.

How to detect catch-weight items:
- Look for "WEIGHT:" or "TOTAL WEIGHT:" followed by a decimal number (e.g., "WEIGHT: 50.100") in the item's extended description or below the main description line
- The Spec column may show "J" for catch-weight items
- Group codes like "MT" (Meat) or "SF" (Seafood) are common but not definitive

For catch-weight items, extract differently:
- quantity: Use the WEIGHT value (e.g., 50.100), NOT Qty Ship
- unit: "LB" (always pounds for catch-weight)
- unit_price: The per-pound price from the Unit Price column (e.g., $10.02/lb)
- line_total: Should equal weight x per-lb price (e.g., 50.100 x $10.02 = $502.00)

Example catch-weight line:
  Item: 649601 "Angus Srln Btm Flap" | Qty Ship: 1 | WEIGHT: 50.100 | Unit Price: $10.02 | Ext: $502.00
  -> quantity: 50.1, unit: "LB", unit_price: 10.02, line_total: 502.00

Example normal (non-catch-weight) line:
  Item: 136753 "Lids, Plastic, Clear" | Qty Ship: 1 | Unit Price: $54.82 | Ext: $54.82
  -> quantity: 1, unit: "CS", unit_price: 54.82, line_total: 54.82

If you see a WEIGHT value for an item, ALWAYS use it as the quantity with unit "LB"."""

NEW_NOTES = (
    "Gordon invoices have Qty Ord, Qty Ship, and Pack Size columns. "
    "Always use Qty Ship for standard items. "
    "Watch out for product specs being confused with qty. "
    "Catch-weight items (meat/seafood) have WEIGHT values - use weight as qty with LB unit and per-lb price."
)


def main():
    db = SessionLocal()
    try:
        rule = db.query(VendorParsingRule).filter(
            VendorParsingRule.vendor_id == 5
        ).first()

        if not rule:
            print("ERROR: No parsing rule found for vendor_id=5 (GFS)")
            return

        print(f"Found rule ID {rule.id} for vendor_id {rule.vendor_id}")
        print(f"Old ai_instructions length: {len(rule.ai_instructions or '')}")

        rule.ai_instructions = NEW_AI_INSTRUCTIONS
        rule.notes = NEW_NOTES

        db.commit()
        db.refresh(rule)

        print(f"New ai_instructions length: {len(rule.ai_instructions)}")
        print(f"Contains CATCH-WEIGHT: {'CATCH-WEIGHT' in rule.ai_instructions}")
        print("SUCCESS: GFS parsing rules updated with catch-weight detection")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
