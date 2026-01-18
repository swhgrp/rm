"""Consolidate UOM - Add fields to master_item_count_units

Add individual_weight_oz, individual_volume_oz, notes, and is_active columns
to master_item_count_units table to support consolidation of item_unit_conversions.

Also migrates data from item_unit_conversions to master_item_count_units.

Revision ID: 20260117_0001
Revises: 20260105_0001
Create Date: 2026-01-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text
import logging

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision = '20260117_0001'
down_revision = '20260105_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to master_item_count_units
    # These support the consolidation of item_unit_conversions functionality

    # Individual unit specifications (from ItemUnitConversion)
    op.add_column(
        'master_item_count_units',
        sa.Column('individual_weight_oz', sa.Numeric(10, 4), nullable=True)
    )
    op.add_column(
        'master_item_count_units',
        sa.Column('individual_volume_oz', sa.Numeric(10, 4), nullable=True)
    )

    # Notes field for contextual information
    op.add_column(
        'master_item_count_units',
        sa.Column('notes', sa.Text(), nullable=True)
    )

    # Soft delete support (consistent with item_unit_conversions)
    op.add_column(
        'master_item_count_units',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true')
    )

    # Migrate data from item_unit_conversions to master_item_count_units
    # This preserves all conversion data including individual specs and notes
    migrate_item_unit_conversions()


def migrate_item_unit_conversions():
    """
    Migrate ItemUnitConversion records to MasterItemCountUnit.

    For each conversion, we determine which unit to add as a count unit:
    - If from_unit matches item's primary count unit: add to_unit as secondary
    - If to_unit matches item's primary count unit: add from_unit as secondary
    - Copy individual_weight_oz, individual_volume_oz, notes

    The conversion_to_primary is calculated based on the relationship:
    - If adding to_unit: conversion_to_primary = 1/conversion_factor
      (e.g., 1 patty = 1/8 lb = 0.125 lb)
    - If adding from_unit: conversion_to_primary = conversion_factor
      (e.g., 1 lb = 8 patties, so lb->primary factor = 8)
    """
    conn = op.get_bind()

    # Get all active item_unit_conversions
    conversions = conn.execute(text("""
        SELECT iuc.id, iuc.master_item_id,
               iuc.from_unit_id, iuc.from_unit_name, iuc.from_unit_abbr,
               iuc.to_unit_id, iuc.to_unit_name, iuc.to_unit_abbr,
               iuc.conversion_factor,
               iuc.individual_weight_oz, iuc.individual_volume_oz, iuc.notes
        FROM item_unit_conversions iuc
        WHERE iuc.is_active = true
    """)).fetchall()

    if not conversions:
        logger.info("No item_unit_conversions to migrate")
        return

    logger.info(f"Migrating {len(conversions)} item_unit_conversions")
    migrated = 0
    skipped = 0

    for conv in conversions:
        item_id = conv.master_item_id

        # Find the primary count unit for this item
        primary = conn.execute(text("""
            SELECT uom_id, uom_name FROM master_item_count_units
            WHERE master_item_id = :item_id AND is_primary = true
        """), {"item_id": item_id}).fetchone()

        if not primary:
            logger.warning(f"Item {item_id} has no primary count unit, skipping conversion {conv.id}")
            skipped += 1
            continue

        # Determine which unit to add and calculate conversion factor
        # The goal: add the "container" unit (usually to_unit like Bottle, Can, Case)
        # with a conversion_to_primary that expresses how many primary units it contains

        if conv.from_unit_id == primary.uom_id:
            # from_unit is primary (e.g., Fluid Ounce)
            # to_unit is the container (e.g., Bottle)
            # conversion_factor = 33.814 means 1 fl oz = 33.814 bottles? No, that's backwards
            # Actually: conversion_factor means "1 from_unit = X to_units"
            # So if from=Pound, to=Each, factor=8: 1 lb = 8 each
            # We want to add "Each" with conversion_to_primary = 1/8 = 0.125 (each to pounds)
            add_unit_id = conv.to_unit_id
            add_unit_name = conv.to_unit_name
            add_unit_abbr = conv.to_unit_abbr
            # 1 to_unit = 1/conversion_factor from_units
            conversion_to_primary = 1.0 / float(conv.conversion_factor) if conv.conversion_factor else 1.0
        elif conv.to_unit_id == primary.uom_id:
            # to_unit is primary (e.g., Each)
            # from_unit is the container (e.g., Pound, Case)
            # conversion_factor = 8 means 1 pound = 8 each
            # We want to add "Pound" with conversion_to_primary = 8
            add_unit_id = conv.from_unit_id
            add_unit_name = conv.from_unit_name
            add_unit_abbr = conv.from_unit_abbr
            conversion_to_primary = float(conv.conversion_factor) if conv.conversion_factor else 1.0
        else:
            # Neither unit matches primary - complex case, skip for manual review
            logger.warning(
                f"Conversion {conv.id} ({conv.from_unit_name}->{conv.to_unit_name}) "
                f"doesn't involve primary unit ({primary.uom_name}), skipping"
            )
            skipped += 1
            continue

        # Check if this unit already exists as a count unit for this item
        existing = conn.execute(text("""
            SELECT id FROM master_item_count_units
            WHERE master_item_id = :item_id AND uom_id = :uom_id
        """), {"item_id": item_id, "uom_id": add_unit_id}).fetchone()

        if existing:
            # Update existing with individual specs and notes
            conn.execute(text("""
                UPDATE master_item_count_units
                SET individual_weight_oz = COALESCE(individual_weight_oz, :weight),
                    individual_volume_oz = COALESCE(individual_volume_oz, :volume),
                    notes = COALESCE(notes, :notes)
                WHERE id = :id
            """), {
                "id": existing.id,
                "weight": conv.individual_weight_oz,
                "volume": conv.individual_volume_oz,
                "notes": conv.notes
            })
            logger.info(f"Updated existing count unit {existing.id} with specs from conversion {conv.id}")
        else:
            # Get next display_order
            max_order = conn.execute(text("""
                SELECT COALESCE(MAX(display_order), 0) + 1
                FROM master_item_count_units WHERE master_item_id = :item_id
            """), {"item_id": item_id}).scalar()

            # Create new count unit
            conn.execute(text("""
                INSERT INTO master_item_count_units
                (master_item_id, uom_id, uom_name, uom_abbreviation,
                 is_primary, conversion_to_primary, display_order,
                 individual_weight_oz, individual_volume_oz, notes, is_active)
                VALUES (:item_id, :uom_id, :uom_name, :uom_abbr,
                        false, :conv_factor, :order,
                        :weight, :volume, :notes, true)
            """), {
                "item_id": item_id,
                "uom_id": add_unit_id,
                "uom_name": add_unit_name,
                "uom_abbr": add_unit_abbr,
                "conv_factor": conversion_to_primary,
                "order": max_order,
                "weight": conv.individual_weight_oz,
                "volume": conv.individual_volume_oz,
                "notes": conv.notes
            })
            logger.info(
                f"Created count unit {add_unit_name} for item {item_id} "
                f"from conversion {conv.id} (factor={conversion_to_primary})"
            )

        migrated += 1

    logger.info(f"Migration complete: {migrated} migrated, {skipped} skipped")


def downgrade() -> None:
    op.drop_column('master_item_count_units', 'is_active')
    op.drop_column('master_item_count_units', 'notes')
    op.drop_column('master_item_count_units', 'individual_volume_oz')
    op.drop_column('master_item_count_units', 'individual_weight_oz')

    # Note: We don't delete the migrated count units on downgrade
    # as they may have been modified. The item_unit_conversions table
    # still contains the original data.
