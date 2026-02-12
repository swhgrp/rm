"""Seed vendor_item_uoms from existing vendor item data

Revision ID: 20260212_0002
Revises: 20260212_0001
Create Date: 2026-02-12

Populates vendor_item_uoms from existing hub_vendor_items data:
- Items with units_per_case > 1: get CS (default) + EA entries
- Weight items: conversion_factor = units_per_case * size_quantity
- Items with units_per_case = 1 or NULL: get EA entry as default
Also backfills matched_uom_id on existing mapped invoice items.
"""

from alembic import op
import sqlalchemy as sa

revision = '20260212_0002'
down_revision = '20260212_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Look up standard UOM IDs
    cs_id = conn.execute(sa.text(
        "SELECT id FROM units_of_measure WHERE LOWER(abbreviation) = 'cs' LIMIT 1"
    )).scalar()
    ea_id = conn.execute(sa.text(
        "SELECT id FROM units_of_measure WHERE LOWER(abbreviation) = 'ea' LIMIT 1"
    )).scalar()
    lb_id = conn.execute(sa.text(
        "SELECT id FROM units_of_measure WHERE LOWER(abbreviation) = 'lb' LIMIT 1"
    )).scalar()

    if not cs_id or not ea_id:
        raise RuntimeError("Missing required UOM records: cs=%s, ea=%s" % (cs_id, ea_id))

    # -------------------------------------------------------
    # Step 1: Case items (units_per_case > 1) — DEFAULT is CS
    # -------------------------------------------------------

    # 1a: Non-weight items — conversion_factor = units_per_case
    conn.execute(sa.text("""
        INSERT INTO vendor_item_uoms (vendor_item_id, uom_id, conversion_factor, is_default, is_active)
        SELECT
            hvi.id,
            :cs_id,
            hvi.units_per_case::numeric,
            true,
            true
        FROM hub_vendor_items hvi
        LEFT JOIN hub_size_units hsu ON hsu.id = hvi.size_unit_id
        WHERE hvi.units_per_case IS NOT NULL
          AND hvi.units_per_case > 1
          AND (hsu.id IS NULL OR hsu.measure_type != 'weight')
        ON CONFLICT (vendor_item_id, uom_id) DO NOTHING
    """), {'cs_id': cs_id})

    # 1b: Weight items — conversion_factor = units_per_case * size_quantity
    conn.execute(sa.text("""
        INSERT INTO vendor_item_uoms (vendor_item_id, uom_id, conversion_factor, is_default, is_active)
        SELECT
            hvi.id,
            :cs_id,
            (hvi.units_per_case * COALESCE(hvi.size_quantity, 1))::numeric,
            true,
            true
        FROM hub_vendor_items hvi
        JOIN hub_size_units hsu ON hsu.id = hvi.size_unit_id
        WHERE hvi.units_per_case IS NOT NULL
          AND hvi.units_per_case > 1
          AND hsu.measure_type = 'weight'
        ON CONFLICT (vendor_item_id, uom_id) DO NOTHING
    """), {'cs_id': cs_id})

    # 1c: Add EA entry (conversion_factor=1) for all case items (non-weight)
    conn.execute(sa.text("""
        INSERT INTO vendor_item_uoms (vendor_item_id, uom_id, conversion_factor, is_default, is_active)
        SELECT
            hvi.id,
            :ea_id,
            1.0,
            false,
            true
        FROM hub_vendor_items hvi
        LEFT JOIN hub_size_units hsu ON hsu.id = hvi.size_unit_id
        WHERE hvi.units_per_case IS NOT NULL
          AND hvi.units_per_case > 1
          AND (hsu.id IS NULL OR hsu.measure_type != 'weight')
        ON CONFLICT (vendor_item_id, uom_id) DO NOTHING
    """), {'ea_id': ea_id})

    # 1d: Add LB entry (conversion_factor=1) for weight case items
    if lb_id:
        conn.execute(sa.text("""
            INSERT INTO vendor_item_uoms (vendor_item_id, uom_id, conversion_factor, is_default, is_active)
            SELECT
                hvi.id,
                :lb_id,
                1.0,
                false,
                true
            FROM hub_vendor_items hvi
            JOIN hub_size_units hsu ON hsu.id = hvi.size_unit_id
            WHERE hvi.units_per_case IS NOT NULL
              AND hvi.units_per_case > 1
              AND hsu.measure_type = 'weight'
            ON CONFLICT (vendor_item_id, uom_id) DO NOTHING
        """), {'lb_id': lb_id})

    # -------------------------------------------------------
    # Step 2: Individual items (units_per_case = 1 or NULL)
    # -------------------------------------------------------

    # 2a: Non-weight items — EA is default
    conn.execute(sa.text("""
        INSERT INTO vendor_item_uoms (vendor_item_id, uom_id, conversion_factor, is_default, is_active)
        SELECT
            hvi.id,
            :ea_id,
            1.0,
            true,
            true
        FROM hub_vendor_items hvi
        LEFT JOIN hub_size_units hsu ON hsu.id = hvi.size_unit_id
        WHERE (hvi.units_per_case IS NULL OR hvi.units_per_case <= 1)
          AND (hsu.id IS NULL OR hsu.measure_type != 'weight')
          AND NOT EXISTS (
              SELECT 1 FROM vendor_item_uoms viu WHERE viu.vendor_item_id = hvi.id
          )
        ON CONFLICT (vendor_item_id, uom_id) DO NOTHING
    """), {'ea_id': ea_id})

    # 2b: Weight items without case — LB is default
    if lb_id:
        conn.execute(sa.text("""
            INSERT INTO vendor_item_uoms (vendor_item_id, uom_id, conversion_factor, is_default, is_active)
            SELECT
                hvi.id,
                :lb_id,
                1.0,
                true,
                true
            FROM hub_vendor_items hvi
            JOIN hub_size_units hsu ON hsu.id = hvi.size_unit_id
            WHERE (hvi.units_per_case IS NULL OR hvi.units_per_case <= 1)
              AND hsu.measure_type = 'weight'
              AND NOT EXISTS (
                  SELECT 1 FROM vendor_item_uoms viu WHERE viu.vendor_item_id = hvi.id
              )
            ON CONFLICT (vendor_item_id, uom_id) DO NOTHING
        """), {'lb_id': lb_id})

    # -------------------------------------------------------
    # Step 3: Backfill matched_uom_id on existing mapped invoice items
    # -------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE hub_invoice_items hii
        SET matched_uom_id = viu.id
        FROM vendor_item_uoms viu
        WHERE hii.inventory_item_id = viu.vendor_item_id
          AND viu.is_default = true
          AND hii.is_mapped = true
          AND hii.inventory_item_id IS NOT NULL
          AND hii.matched_uom_id IS NULL
    """))


def downgrade() -> None:
    # Clear matched_uom_id backfill
    op.execute("UPDATE hub_invoice_items SET matched_uom_id = NULL")
    # Delete seeded data
    op.execute("DELETE FROM vendor_item_uoms")
