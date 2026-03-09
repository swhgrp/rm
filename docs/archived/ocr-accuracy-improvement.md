# OCR Accuracy Improvement Project

**Created:** November 29, 2025
**Status:** In Progress - Paused
**Priority:** High

---

## Problem Statement

Invoice item codes frequently have OCR errors when parsed from PDF invoices. Common issues include:
- Single digit errors (e.g., `104471` instead of `100471`)
- Digit transpositions
- Common OCR confusions: 0↔O, 1↔l↔I, 5↔S, 8↔B, 6↔G

This causes:
1. Items not auto-mapping to existing vendor items
2. Manual correction work on the Item Codes page
3. Potential duplicate vendor items with wrong codes

---

## Solution Architecture

### 1. Fuzzy Matching Against Existing Vendor Items

Use the existing vendor items in the inventory system as the source of truth. When parsing invoices:

1. **OCR the code** with OpenAI Vision
2. **Exact match** against existing vendor items → use that code
3. **Fuzzy match** (1-2 characters off) + verify with description/price → auto-correct
4. **No match** → flag as new item for review

### 2. OCR Similarity Scoring

The fuzzy matching script calculates similarity considering common OCR confusions:

```python
# Common OCR confusions
ocr_similar = {
    '0': ['O', 'o', 'Q', 'D'],
    '1': ['l', 'I', 'i', '|', '7'],
    '5': ['S', 's'],
    '8': ['B', '3'],
    '6': ['G', 'b'],
    '2': ['Z', 'z'],
    '9': ['g', 'q'],
}
```

### 3. Confidence Levels

| Confidence | Score Range | Action |
|------------|-------------|--------|
| Exact/Near-exact | ≥95% | Auto-correct |
| High | 80-95% | Auto-correct, flag for review |
| Medium | 60-80% | Manual review required |
| No match | <60% | New item or wrong vendor |

---

## Implementation

### Scripts Created

**Location:** `/opt/restaurant-system/integration-hub/scripts/fuzzy_match_report.py`

**Purpose:** Analyzes unmapped invoice items against existing vendor items and generates a match report.

**Usage:**
```bash
cat /opt/restaurant-system/integration-hub/scripts/fuzzy_match_report.py | docker exec -i integration-hub python
```

**Features:**
- Connects to both inventory and hub databases
- Calculates OCR-aware similarity scores
- Groups by vendor for better matching
- Outputs categorized report with confidence levels

### Database Tables Involved

**Hub Database (integration_hub_db):**
- `hub_invoice_items` - Parsed invoice line items
- `hub_invoices` - Invoice headers with vendor info

**Inventory Database (inventory_db):**
- `vendor_items` - Verified vendor item codes (source of truth)
- `vendors` - Vendor information

---

## Analysis Results (Nov 29, 2025)

### Summary

| Category | Count | % of Total |
|----------|-------|------------|
| Total unmapped items | 356 | 100% |
| Exact/Near-exact matches | 67 | 19% |
| High confidence matches | 1 | 0.3% |
| Medium confidence matches | 26 | 7% |
| No match found | 262 | 74% |

### Invoice Rows Impact

- **91 invoice rows** can be auto-corrected (exact + high confidence)
- **484 total unmapped rows** in the system

### OCR Error Examples Found

| Invoice Code | Correct Code | Item | Error Type |
|--------------|--------------|------|------------|
| 104471 | 100471 | Grape Juice | Single digit |
| 141441 | 141341 | Honey | Digit swap |
| 434013 | 431013 | Garlic | Single digit |
| 1017400 | 101740 | Caribbean Veg | Extra digit |
| 264442 | 264142 | Brioche Buns | Single digit |

### No Match - By Vendor

Most unmatched items are from vendors not yet in the inventory system:

| Vendor | Unmapped Items | Notes |
|--------|----------------|-------|
| Gold Coast Beverage | ~50+ | Beer/beverages |
| Southern Glazier's | ~30+ | Liquor/wine |
| Gordon Food Service | ~50 | May need price list update |

---

## Next Steps

### Immediate (Ready to Execute)

1. **Auto-correct 67 exact matches**
   - Run script to update hub_invoice_items with correct vendor item mappings
   - Update item_code to match vendor_sku

2. **Review 26 medium confidence matches**
   - Present to user for approval/rejection
   - Learn from decisions to improve algorithm

### Short-term

3. **Import missing vendor items**
   - Get price lists for Gold Coast Beverage and Southern Glazier's
   - Import into inventory vendor_items table
   - Re-run matching

4. **Enhance auto-mapper**
   - Add fuzzy matching to `auto_mapper.py` for future invoices
   - Use same OCR similarity algorithm

### Long-term

5. **OCR confidence scoring in parser**
   - Request confidence scores from OpenAI Vision
   - Store per-field confidence
   - Flag low-confidence extractions for review

6. **Vendor-specific code patterns**
   - Define expected code formats per vendor
   - Validate against patterns during parsing

---

## Files Modified

### Nov 29, 2025 Session

| File | Change |
|------|--------|
| `inventory/src/restaurant_inventory/api/api_v1/endpoints/count_sessions.py` | Fixed delete cascade, inventory_type saving |
| `inventory/src/restaurant_inventory/api/api_v1/endpoints/items.py` | Added count_unit_2/3 fields and factors |
| `inventory/src/restaurant_inventory/schemas/item.py` | Added count_unit_2_factor, count_unit_3_factor |
| `inventory/src/restaurant_inventory/templates/count_session_new.html` | Updated unit dropdown and conversion logic |
| `integration-hub/scripts/fuzzy_match_report.py` | **NEW** - Fuzzy matching analysis script |

---

## Related Documentation

- [Invoice Parser](../integration-hub/src/integration_hub/services/invoice_parser.py) - Current OCR implementation
- [Auto Mapper](../integration-hub/src/integration_hub/services/auto_mapper.py) - Current mapping logic
- [Item Codes Page](../integration-hub/src/integration_hub/templates/item_codes.html) - Manual correction UI
