# Integration Hub Item Mapping Simplification

## Overview

This document records the simplification of the Integration Hub's item mapping system, making the Inventory system the single source of truth for vendor items.

## Date: December 2024

---

## Problem Statement

The original Integration Hub had multiple overlapping mapping tables and complex logic:
- `invoice_item_mapping` - stored individual item mappings
- `item_code_mapping` - stored SKU-to-vendor-item mappings
- `item_gl_mapping` - stored direct GL account mappings
- `category_gl_mapping` - stored category-to-GL mappings

This led to:
1. Duplicate data between Hub and Inventory
2. Items mapped to categories only (without vendor items)
3. Confusion about source of truth
4. Complex auto-mapping logic with multiple fallback paths

---

## New Simplified Design

### Principles

1. **Inventory is the source of truth** for all vendor items
2. **Hub only stores expense mappings** (non-inventory items like propane, uniforms, etc.)
3. **Auto-mapper does SKU lookup only** against Inventory API
4. **New vendor items are created in Inventory**, not Hub

### Mapping Flow

```
Invoice Item Received
        |
        v
   Has item_code?
   /           \
  Yes           No
   |             |
   v             v
Match vendor_sku    Check expense_mappings
in Inventory API    by item_description
   |                    |
   v                    v
Found?              Found?
/    \              /    \
Yes   No           Yes   No
 |     |            |     |
 |     +------------+-----+
 |                  |
 v                  v
MAPPED           UNMAPPED
(vendor_item)    (manual review)
```

---

## Database Changes

### New Table: `expense_mappings`

```sql
CREATE TABLE expense_mappings (
    id SERIAL PRIMARY KEY,
    item_description TEXT NOT NULL UNIQUE,
    gl_expense_account INT NOT NULL,
    gl_account_name VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

This table stores mappings for expense items (non-inventory items that go directly to GL accounts).

### Migrated Data

30 existing expense mappings were migrated from the old `invoice_item_mapping` table where `is_expense_item = true`.

### Tables Deprecated

These tables have been renamed with `_deprecated` suffix (data preserved for reference):
- `invoice_item_mapping_deprecated` - replaced by Inventory vendor_items + expense_mappings
- `item_code_mapping_deprecated` - replaced by Inventory vendor_items.vendor_sku
- `item_gl_mapping_deprecated` - replaced by category_gl_mapping

### Tables Kept

- `category_gl_mapping` - Maps inventory categories to GL accounts
- `expense_mappings` - Maps expense item descriptions to GL accounts

---

## Code Changes

### 1. `auto_mapper.py` - Simplified

**Location:** `/opt/restaurant-system/integration-hub/src/integration_hub/services/auto_mapper.py`

The auto-mapper was completely rewritten with simplified logic:

```python
class AutoMapperService:
    def map_item(self, item: HubInvoiceItem) -> Dict:
        # 1. Try SKU match against inventory
        if item.item_code:
            vendor_item = self.match_by_sku(item.item_code)
            if vendor_item:
                category = vendor_item.get('master_item_category')
                gl_accounts = self.get_gl_accounts_for_category(category)
                return {
                    'mapped': True,
                    'method': 'sku_match',
                    'vendor_item_id': vendor_item['id'],
                    ...
                }

        # 2. Try expense mapping
        expense = self.match_by_expense_mapping(item.item_description)
        if expense:
            return {
                'mapped': True,
                'method': 'expense_mapping',
                'is_expense': True,
                ...
            }

        # 3. No match found
        return {'mapped': False, 'reason': 'no_sku_match'}
```

Key methods:
- `fetch_vendor_items_from_inventory()` - Gets all vendor items from Inventory API
- `match_by_sku()` - Matches item_code against vendor_items.vendor_sku
- `match_by_expense_mapping()` - Checks expense_mappings table
- `get_gl_accounts_for_category()` - Gets GL accounts from category_gl_mapping

### 2. Inventory API - Added Category

**Location:** `/opt/restaurant-system/inventory/src/restaurant_inventory/api/api_v1/endpoints/vendor_items.py`

The `/_hub/sync` endpoint now includes `master_item_category`:

```python
item_list.append({
    "id": vi.id,
    "vendor_id": vi.vendor_id,
    "vendor_name": vi.vendor.name,
    "vendor_sku": vi.vendor_sku,
    "vendor_product_name": vi.vendor_product_name,
    "master_item_id": vi.master_item_id,
    "master_item_name": vi.master_item.name,
    "master_item_category": vi.master_item.category,  # NEW
    "pack_size": vi.pack_size,
    "unit_price": float(vi.unit_price),
    "is_active": vi.is_active,
    "is_preferred": vi.is_preferred
})
```

### 3. Map-by-Description API - Updated

**Location:** `/opt/restaurant-system/integration-hub/src/integration_hub/main.py`

The endpoint now saves expense mappings to the new `expense_mappings` table:

```python
@app.post("/api/items/map-by-description")
async def map_items_by_description(...):
    if is_expense_item:
        # Save to expense_mappings for future auto-mapping
        existing = db.execute(sql_text(
            "SELECT id FROM expense_mappings WHERE item_description = :desc"
        ), {"desc": item_description}).fetchone()

        if existing:
            db.execute(sql_text("""
                UPDATE expense_mappings
                SET gl_expense_account = :gl_account, updated_at = NOW()
                WHERE item_description = :desc
            """), {...})
        else:
            db.execute(sql_text("""
                INSERT INTO expense_mappings (item_description, gl_expense_account)
                VALUES (:desc, :gl_account)
            """), {...})
```

---

## How Items Are Now Mapped

### Inventory Items (Food, Supplies, etc.)

1. Invoice arrives with line items
2. Auto-mapper looks up `item_code` against Inventory `vendor_items.vendor_sku`
3. If found:
   - `inventory_item_id` = vendor_item.id
   - `inventory_category` = vendor_item.master_item_category
   - GL accounts from `category_gl_mapping`
4. If not found: Item goes to unmapped queue for manual mapping

### Expense Items (Propane, Uniforms, etc.)

1. Invoice arrives with line items
2. Auto-mapper checks `expense_mappings` by item_description
3. If found:
   - `is_expense` = true
   - GL account from expense_mappings
4. If not found: Item goes to unmapped queue for manual mapping

### Manual Mapping (Unmapped Queue)

When mapping manually:
- **Inventory items**: Select vendor item from Inventory (creates in Inventory if new)
- **Expense items**: Select GL account (saves to `expense_mappings` for future auto-mapping)

---

## Completed Work

1. **Created expense_mappings table** - Migrated 30 expense mappings
2. **Simplified auto_mapper.py** - SKU lookup only against inventory API
3. **Updated map-by-description API** - Saves expense mappings to new table
4. **Added category to inventory API** - `/_hub/sync` now includes `master_item_category`
5. **Updated unmapped_items.html** - Simplified UI, category comes from vendor item selection
6. **Updated mapped_items.html** - Shows vendor_item from inventory with category
7. **Deprecated old mapping tables** - Renamed with `_deprecated` suffix

---

## Category to GL Account Mapping

The `category_gl_mapping` table maps inventory categories to GL accounts:

| Category | Asset Account | COGS Account | Waste Account |
|----------|--------------|--------------|---------------|
| Food - Produce | 14100 | 51100 | 54100 |
| Food - Protein | 14100 | 51100 | 54100 |
| Food - Dairy | 14100 | 51100 | 54100 |
| Beverage - Alcohol | 14200 | 51200 | 54200 |
| Beverage - NA | 14200 | 51200 | 54200 |
| Supplies - Paper | 14300 | 51300 | 54300 |
| Supplies - Cleaning | 14300 | 51300 | 54300 |
| Smallwares | 14400 | 51400 | 54400 |

---

## Location Reference

| Internal ID | Store ID | Name |
|-------------|----------|------|
| 1 | 200 | McKinney |
| 2 | 300 | Arlington |
| 3 | 400 | Dallas |
| 4 | 500 | Fort Worth |
| 5 | 600 | Plano |
| 6 | 700 | Frisco |
