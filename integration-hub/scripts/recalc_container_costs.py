#!/usr/bin/env python3
"""
Recalculate weighted average costs for container items that had wrong pack_to_primary_factor.

For affected master items (where primary count unit is a container like Can 16oz),
replays all invoice history using the corrected factor (units_per_case) and
recalculates weighted average costs at each location.

Run AFTER fix_container_pack_factors.py.

Usage:
    docker compose exec integration-hub python scripts/recalc_container_costs.py --dry-run
    docker compose exec integration-hub python scripts/recalc_container_costs.py
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import text, create_engine
from integration_hub.db.database import SessionLocal

# Container-type UOM prefixes in Inventory
CONTAINER_PREFIXES = ('Can', 'Bottle', 'Keg', 'Tub', 'Jar')


def get_inventory_engine():
    inventory_db_url = os.environ.get(
        'INVENTORY_DATABASE_URL',
        'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
    )
    return create_engine(inventory_db_url)


def main():
    parser = argparse.ArgumentParser(description='Recalculate weighted averages for container items')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    args = parser.parse_args()

    db = SessionLocal()
    inv_engine = get_inventory_engine()

    print("=" * 80)
    print("Recalculate Weighted Average Costs for Container Items")
    print("=" * 80)
    if args.dry_run:
        print("[DRY RUN MODE]")
    print()

    # Find affected master items: those with container-type primary count units
    with inv_engine.connect() as inv_conn:
        container_masters = inv_conn.execute(text("""
            SELECT cu.master_item_id, cu.uom_name, mi.name
            FROM master_item_count_units cu
            JOIN master_items mi ON mi.id = cu.master_item_id
            WHERE cu.is_primary = true AND cu.is_active = true
        """)).fetchall()

    affected_master_ids = {}
    for mid, uom_name, item_name in container_masters:
        if any(uom_name.startswith(prefix) for prefix in CONTAINER_PREFIXES):
            affected_master_ids[mid] = {'uom_name': uom_name, 'item_name': item_name}

    print(f"Found {len(affected_master_ids)} master items with container primary units\n")

    # Get all locations
    with inv_engine.connect() as inv_conn:
        locations = inv_conn.execute(text(
            "SELECT id, name FROM locations WHERE is_active = true ORDER BY id"
        )).fetchall()
    location_map = {loc[0]: loc[1] for loc in locations}

    total_updated = 0
    total_seeded = 0
    total_unchanged = 0

    for mid, info in sorted(affected_master_ids.items()):
        uom_name = info['uom_name']
        item_name = info['item_name']
        print(f"\n{'─' * 70}")
        print(f"Master Item #{mid}: {item_name} (primary: {uom_name})")
        print(f"{'─' * 70}")

        # Get all vendor items for this master item with their units_per_case
        vendor_items = db.execute(text("""
            SELECT id, vendor_product_name, units_per_case
            FROM hub_vendor_items
            WHERE inventory_master_item_id = :mid AND is_active = true
        """), {"mid": mid}).fetchall()

        if not vendor_items:
            print("  No vendor items found, skipping")
            continue

        # Build vendor item factor map (corrected: units_per_case for containers)
        vi_factors = {}
        for vi_id, vi_name, upc in vendor_items:
            vi_factors[vi_id] = float(upc or 1)

        # Get best vendor item cost for seeding (lowest cost)
        best_seed_cost = None
        for vi_id, vi_name, upc in vendor_items:
            vi = db.execute(text("""
                SELECT case_cost, units_per_case, last_purchase_price
                FROM hub_vendor_items WHERE id = :id
            """), {"id": vi_id}).fetchone()
            if vi and vi[0] and vi[1]:
                unit_cost = float(vi[0]) / float(vi[1])
                if best_seed_cost is None or unit_cost < best_seed_cost:
                    best_seed_cost = unit_cost

        # Process each location
        for loc_id, loc_name in sorted(location_map.items()):
            # Get all invoice items for this master item at this location
            invoice_items = db.execute(text("""
                SELECT ii.unit_price, ii.quantity, ii.inventory_item_id,
                       i.invoice_date, i.id as invoice_id, i.invoice_number
                FROM hub_invoice_items ii
                JOIN hub_vendor_items vi ON ii.inventory_item_id = vi.id
                JOIN hub_invoices i ON ii.invoice_id = i.id
                WHERE vi.inventory_master_item_id = :mid
                  AND i.location_id = :lid
                  AND ii.is_mapped = true
                  AND ii.unit_price IS NOT NULL
                  AND ii.quantity IS NOT NULL
                ORDER BY i.invoice_date, i.id
            """), {"mid": mid, "lid": loc_id}).fetchall()

            # Get current cost record
            with inv_engine.connect() as inv_conn:
                current = inv_conn.execute(text("""
                    SELECT id, current_weighted_avg_cost, total_qty_on_hand,
                           last_purchase_cost, last_purchase_qty
                    FROM master_item_location_costs
                    WHERE master_item_id = :mid AND location_id = :lid
                """), {"mid": mid, "lid": loc_id}).fetchone()

            if not current:
                continue  # No cost record exists

            cost_id, old_avg, old_qty, old_last_cost, old_last_qty = current
            old_avg = float(old_avg or 0)

            if invoice_items:
                # Replay weighted average with corrected factors
                total_value = 0.0
                total_qty = 0.0
                last_cost = None
                last_qty = None
                last_date = None
                last_vendor_id = None

                for unit_price, quantity, vi_id, inv_date, inv_id, inv_num in invoice_items:
                    unit_price = float(unit_price or 0)
                    quantity = float(quantity or 0)
                    if unit_price <= 0 or quantity <= 0:
                        continue

                    cf = vi_factors.get(vi_id, 1.0)
                    cost_per_primary = unit_price / cf
                    qty_in_primary = quantity * cf

                    total_value += cost_per_primary * qty_in_primary
                    total_qty += qty_in_primary
                    last_cost = cost_per_primary
                    last_qty = qty_in_primary
                    last_date = inv_date

                    # Get vendor_id for last invoice
                    vi_row = db.execute(text(
                        "SELECT vendor_id FROM hub_vendor_items WHERE id = :id"
                    ), {"id": vi_id}).fetchone()
                    if vi_row:
                        last_vendor_id = vi_row[0]

                if total_qty > 0:
                    new_avg = total_value / total_qty
                else:
                    new_avg = old_avg
                    total_unchanged += 1
                    continue

                # Check if there's a meaningful change
                if abs(new_avg - old_avg) < 0.001:
                    total_unchanged += 1
                    continue

                print(f"  {loc_name}: ${old_avg:.4f} → ${new_avg:.4f} "
                      f"(qty: {float(old_qty or 0):.0f} → {total_qty:.0f}, "
                      f"{len(invoice_items)} invoices)")

                if not args.dry_run:
                    with inv_engine.connect() as inv_conn:
                        inv_conn.execute(text("""
                            UPDATE master_item_location_costs
                            SET current_weighted_avg_cost = :avg,
                                total_qty_on_hand = :qty,
                                last_purchase_cost = :last_cost,
                                last_purchase_qty = :last_qty,
                                last_purchase_date = :last_date,
                                last_vendor_id = :vendor_id,
                                last_updated = NOW()
                            WHERE id = :id
                        """), {
                            "avg": round(new_avg, 4),
                            "qty": round(total_qty, 4),
                            "last_cost": round(last_cost, 4) if last_cost else None,
                            "last_qty": round(last_qty, 4) if last_qty else None,
                            "last_date": last_date,
                            "vendor_id": last_vendor_id,
                            "id": cost_id,
                        })

                        # Delete old history and recreate from scratch
                        inv_conn.execute(text("""
                            DELETE FROM master_item_location_cost_history
                            WHERE master_item_id = :mid AND location_id = :lid
                        """), {"mid": mid, "lid": loc_id})

                        # Rebuild history entries
                        running_qty = 0.0
                        running_value = 0.0
                        for unit_price, quantity, vi_id, inv_date, inv_id, inv_num in invoice_items:
                            unit_price = float(unit_price or 0)
                            quantity = float(quantity or 0)
                            if unit_price <= 0 or quantity <= 0:
                                continue

                            cf = vi_factors.get(vi_id, 1.0)
                            cpp = unit_price / cf
                            qip = quantity * cf

                            prev_cost = running_value / running_qty if running_qty > 0 else None
                            prev_qty = running_qty if running_qty > 0 else None

                            running_value += cpp * qip
                            running_qty += qip
                            new_cost_at_point = running_value / running_qty

                            event_type = 'initial' if prev_cost is None else 'purchase'

                            inv_conn.execute(text("""
                                INSERT INTO master_item_location_cost_history
                                (location_cost_id, master_item_id, location_id, event_type,
                                 old_cost, old_qty, change_qty, change_cost_per_unit,
                                 new_cost, new_qty, vendor_id, invoice_id, notes, created_at)
                                VALUES (:cost_id, :mid, :lid, :event_type,
                                        :old_cost, :old_qty, :change_qty, :change_cost,
                                        :new_cost, :new_qty, :vendor_id, :invoice_id, :notes, :inv_date)
                            """), {
                                "cost_id": cost_id,
                                "mid": mid,
                                "lid": loc_id,
                                "event_type": event_type,
                                "old_cost": round(prev_cost, 4) if prev_cost else None,
                                "old_qty": round(prev_qty, 4) if prev_qty else None,
                                "change_qty": round(qip, 4),
                                "change_cost": round(cpp, 4),
                                "new_cost": round(new_cost_at_point, 4),
                                "new_qty": round(running_qty, 4),
                                "vendor_id": last_vendor_id,
                                "invoice_id": inv_id,
                                "notes": f"Recalculated - Invoice {inv_num}",
                                "inv_date": inv_date,
                            })

                        inv_conn.commit()

                total_updated += 1

            else:
                # No invoices — seeded only. Recalculate from vendor item pricing.
                if best_seed_cost and abs(best_seed_cost - old_avg) > 0.001:
                    print(f"  {loc_name} (seeded): ${old_avg:.4f} → ${best_seed_cost:.4f}")

                    if not args.dry_run:
                        with inv_engine.connect() as inv_conn:
                            inv_conn.execute(text("""
                                UPDATE master_item_location_costs
                                SET current_weighted_avg_cost = :cost, last_updated = NOW()
                                WHERE id = :id
                            """), {"cost": round(best_seed_cost, 4), "id": cost_id})
                            inv_conn.commit()

                    total_seeded += 1
                else:
                    total_unchanged += 1

    print()
    print("=" * 80)
    print(f"Results:")
    print(f"  Recalculated from invoices: {total_updated}")
    print(f"  Recalculated seeded costs:  {total_seeded}")
    print(f"  Unchanged:                  {total_unchanged}")
    print("=" * 80)

    if args.dry_run and (total_updated + total_seeded) > 0:
        print(f"\nRun without --dry-run to apply changes.")

    db.close()


if __name__ == '__main__':
    main()
