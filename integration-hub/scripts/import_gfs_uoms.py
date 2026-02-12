"""
Import GFS (Gordon Food Service) purchase UOMs from CSV export.

Reads the CSV, matches to existing vendor items by vendor_sku,
and creates/replaces vendor_item_uoms entries with correct conversion factors.

Handles multiple CSV formats:
  - SW Grill:  Item Number, Item Description, Unit size, Pack size, Pack UOM, Case price UOM, Net Weight
  - Seaside:   Item Number, Item Description, Unit size, Pack size, Pack UOM, Case price, Case price UOM, Unit price UOM
  - Okee:      Item Number, Item Description, Unit size, Pack size, Pack UOM, Catch weight, Case price, Case price UOM, Unit price, Unit price UOM

Logic:
  - Case-priced items (Case price UOM = "/Case"):
      CS → conversion_factor = pack_size, is_default=True
      EA → conversion_factor = 1, is_default=False
  - Weight-priced items (Case price UOM = "lb"):
      LB → conversion_factor = 1, is_default=False
      CS → conversion_factor = net_weight, is_default=True
  - Single-unit items (pack_size empty or 1 with no meaningful unit size):
      EA → conversion_factor = 1, is_default=True
"""
import csv
import sys
import os
import re

# Add the src directory to path
sys.path.insert(0, '/app/src')

from integration_hub.db.database import SessionLocal
from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.models.vendor_item_uom import VendorItemUOM
from integration_hub.models.unit_of_measure import UnitOfMeasure

# UOM abbreviation → units_of_measure.id mapping (from DB query above)
UOM_IDS = {
    'ea': 1,
    'dz': 2,
    'cs': 3,
    'bx': 4,
    'bg': 5,
    'pk': 6,
    'btl': 7,
    'can': 8,
    'keg': 9,
    'oz': 11,
    'lb': 12,
    'g': 13,
    'kg': 14,
    'fl oz': 15,
    'pt': 17,
    'qt': 18,
    'gal': 19,
    'L': 20,
    'mL': 21,
}

# Weight unit abbreviations in GFS CSVs
WEIGHT_UNITS = {'LB', 'LBS', 'LBA', 'OZ'}


def parse_unit_size(raw):
    """Parse unit size string like '5.0 LB' → (5.0, 'LB')"""
    if not raw:
        return None, None
    match = re.match(r'([\d.]+)\s*(\S+)', raw.strip())
    if match:
        return float(match.group(1)), match.group(2).upper()
    return None, None


def calculate_net_weight(unit_size_qty, unit_size_uom, pack_size):
    """Calculate net weight in lbs from unit size and pack size."""
    if not unit_size_qty or not pack_size:
        return None
    if unit_size_uom in ('LB', 'LBS', 'LBA'):
        return unit_size_qty * pack_size
    if unit_size_uom == 'OZ':
        return (unit_size_qty * pack_size) / 16.0
    return None


def parse_csv(filepath):
    """Parse any GFS CSV format and return structured rows."""
    rows = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames

        has_net_weight = 'Net Weight' in headers
        has_catch_weight = 'Catch weight' in headers

        for row in reader:
            item_number = row['Item Number'].strip()
            description = row['Item Description'].strip()
            unit_size_raw = row.get('Unit size', '').strip()
            pack_size_raw = row.get('Pack size', '').strip()
            case_price_uom = row.get('Case price UOM', '').strip()

            # Parse pack size
            pack_size = None
            if pack_size_raw:
                try:
                    pack_size = int(pack_size_raw)
                except ValueError:
                    try:
                        pack_size = float(pack_size_raw)
                    except ValueError:
                        pass

            # Parse unit size
            unit_size_qty, unit_size_uom = parse_unit_size(unit_size_raw)

            # Get net weight — from column if available, else calculate
            net_weight = None
            if has_net_weight:
                nw_raw = row.get('Net Weight', '').strip()
                if nw_raw:
                    try:
                        net_weight = float(nw_raw)
                    except ValueError:
                        pass

            if net_weight is None:
                net_weight = calculate_net_weight(unit_size_qty, unit_size_uom, pack_size)

            # Detect weight-priced items from catch weight column too
            if has_catch_weight and row.get('Catch weight', '').strip().upper() == 'Y':
                case_price_uom = 'lb'

            rows.append({
                'item_number': item_number,
                'description': description,
                'unit_size_qty': unit_size_qty,
                'unit_size_uom': unit_size_uom,
                'pack_size': pack_size,
                'case_price_uom': case_price_uom,
                'net_weight': net_weight,
            })
    return rows


def determine_uoms(row):
    """
    Determine the correct vendor_item_uom entries for a CSV row.
    Returns list of dicts: [{uom_id, conversion_factor, is_default}, ...]
    """
    pack_size = row['pack_size']
    case_price_uom = row['case_price_uom']
    net_weight = row['net_weight']

    uoms = []

    if case_price_uom == 'lb':
        # Weight-priced item: invoice shows per-lb pricing
        # CS: conversion_factor = net_weight (lbs in a case)
        # LB: conversion_factor = 1
        cs_cf = net_weight if net_weight and net_weight > 0 else (pack_size or 1)
        uoms.append({'uom_id': UOM_IDS['cs'], 'conversion_factor': cs_cf, 'is_default': True})
        uoms.append({'uom_id': UOM_IDS['lb'], 'conversion_factor': 1, 'is_default': False})

    elif pack_size and pack_size > 0:
        # Case-priced item with a pack size
        # CS: conversion_factor = pack_size
        # EA: conversion_factor = 1
        uoms.append({'uom_id': UOM_IDS['cs'], 'conversion_factor': pack_size, 'is_default': True})
        if pack_size > 1:
            uoms.append({'uom_id': UOM_IDS['ea'], 'conversion_factor': 1, 'is_default': False})

    else:
        # Single unit item (no pack size)
        # EA: conversion_factor = 1
        uoms.append({'uom_id': UOM_IDS['ea'], 'conversion_factor': 1, 'is_default': True})

    return uoms


def run_import(csv_filepath):
    db = SessionLocal()
    try:
        rows = parse_csv(csv_filepath)
        print(f"Parsed {len(rows)} rows from {os.path.basename(csv_filepath)}")

        stats = {
            'matched': 0,
            'not_found': 0,
            'updated': 0,
            'created_uoms': 0,
            'deleted_uoms': 0,
            'skipped_same': 0,
            'also_updated_vendor_item': 0,
        }
        not_found_skus = []

        for row in rows:
            sku = row['item_number']

            # Find vendor item by SKU
            vendor_item = db.query(HubVendorItem).filter(
                HubVendorItem.vendor_sku == sku
            ).first()

            if not vendor_item:
                stats['not_found'] += 1
                not_found_skus.append(sku)
                continue

            stats['matched'] += 1

            # Determine correct UOMs
            new_uoms = determine_uoms(row)

            # Get existing UOMs for this vendor item
            existing_uoms = db.query(VendorItemUOM).filter(
                VendorItemUOM.vendor_item_id == vendor_item.id
            ).all()

            # Build a map of existing: uom_id → VendorItemUOM
            existing_map = {u.uom_id: u for u in existing_uoms}

            # Track which UOM IDs we want to keep
            desired_uom_ids = {u['uom_id'] for u in new_uoms}

            # Deactivate UOMs that shouldn't exist
            for eu in existing_uoms:
                if eu.uom_id not in desired_uom_ids:
                    if eu.is_active:
                        eu.is_active = False
                        stats['deleted_uoms'] += 1

            # Create or update desired UOMs
            changed = False
            for nu in new_uoms:
                existing = existing_map.get(nu['uom_id'])
                if existing:
                    # Update if different
                    if (float(existing.conversion_factor or 0) != float(nu['conversion_factor'])
                            or existing.is_default != nu['is_default']
                            or not existing.is_active):
                        existing.conversion_factor = nu['conversion_factor']
                        existing.is_default = nu['is_default']
                        existing.is_active = True
                        changed = True
                    else:
                        stats['skipped_same'] += 1
                else:
                    # Create new
                    new_entry = VendorItemUOM(
                        vendor_item_id=vendor_item.id,
                        uom_id=nu['uom_id'],
                        conversion_factor=nu['conversion_factor'],
                        is_default=nu['is_default'],
                        is_active=True,
                    )
                    db.add(new_entry)
                    stats['created_uoms'] += 1
                    changed = True

            if changed:
                stats['updated'] += 1

            # Also update vendor item's units_per_case if NULL
            if row['pack_size'] and not vendor_item.units_per_case:
                vendor_item.units_per_case = row['pack_size']
                stats['also_updated_vendor_item'] += 1

        db.commit()

        print(f"\n--- Import Results ---")
        print(f"CSV rows:           {len(rows)}")
        print(f"Matched to items:   {stats['matched']}")
        print(f"Not found:          {stats['not_found']}")
        print(f"Items updated:      {stats['updated']}")
        print(f"UOM entries created:{stats['created_uoms']}")
        print(f"UOM entries removed:{stats['deleted_uoms']}")
        print(f"Already correct:    {stats['skipped_same']}")
        print(f"Vendor items fixed: {stats['also_updated_vendor_item']}")

        if not_found_skus:
            print(f"\nNot found SKUs ({len(not_found_skus)}): {', '.join(not_found_skus[:20])}")
            if len(not_found_skus) > 20:
                print(f"  ... and {len(not_found_skus) - 20} more")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python import_gfs_uoms.py <csv_file> [csv_file2] ...")
        sys.exit(1)

    for csv_file in sys.argv[1:]:
        print(f"\n{'='*60}")
        print(f"Processing: {csv_file}")
        print(f"{'='*60}")
        run_import(csv_file)
