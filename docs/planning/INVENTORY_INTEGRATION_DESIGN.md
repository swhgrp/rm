# Inventory-to-Accounting Integration Design

**Created:** 2025-10-19
**Status:** In Progress
**Priority:** Tier 1 - Critical

---

## 📋 Requirements Summary

### **Business Requirements**
- Automate COGS journal entries (eliminate manual work)
- Track inventory by category: Food, Beverage, Alcohol, Supplies
- Daily batch COGS posting (end of day)
- Weighted average cost method
- Waste tracking with automated accounting
- Clover POS integration for detailed sales data
- Multi-location support (6 locations)

### **Technical Requirements**
- Bidirectional communication between Inventory and Accounting systems
- Real-time inventory valuation
- Automated journal entry generation
- Error handling and reconciliation
- Audit trail for all transactions

---

## 🏗️ System Architecture

### **Integration Points**

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Clover POS    │────────▶│  Inventory       │◀───────▶│   Accounting    │
│                 │  Sales  │  System          │ Txns    │   System        │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                     │
                                     │ Triggers
                                     ▼
                            ┌──────────────────┐
                            │ Journal Entry    │
                            │ Generator        │
                            └──────────────────┘
```

### **Data Flow**

1. **Purchase Flow:**
   ```
   Invoice Created → InventoryTransaction (PURCHASE) → Accounting Journal Entry
   Dr. Inventory (Asset)
     Cr. Accounts Payable
   ```

2. **Daily COGS Flow:**
   ```
   End of Day Batch → Calculate COGS → Accounting Journal Entry
   Dr. COGS (Expense)
     Cr. Inventory (Asset)
   ```

3. **Waste Flow:**
   ```
   Waste Recorded → InventoryTransaction (WASTE) → Accounting Journal Entry
   Dr. Waste Expense
     Cr. Inventory (Asset)
   ```

4. **Clover Sales Flow:**
   ```
   Clover API → Daily Sales Summary → Accounting Journal Entry
   Dr. Cash/Credit Card Receivable
   Dr. Sales Tax Payable
     Cr. Sales Revenue (by category)
   ```

---

## 📊 Chart of Accounts Mapping

### **Inventory Categories → GL Accounts**

| Inventory Category | Asset Account | COGS Account | Waste Account |
|-------------------|---------------|--------------|---------------|
| **Food** | 1200 - Inventory - Food | 5100 - COGS - Food | 6500 - Waste - Food |
| **Beverage** | 1210 - Inventory - Beverage | 5110 - COGS - Beverage | 6510 - Waste - Beverage |
| **Alcohol** | 1220 - Inventory - Alcohol | 5120 - COGS - Alcohol | 6520 - Waste - Alcohol |
| **Supplies** | 1230 - Inventory - Supplies | 5130 - COGS - Supplies | 6530 - Waste - Supplies |

### **Sales Revenue Accounts**

| Sales Category | GL Account |
|---------------|------------|
| **Food Sales** | 4000 - Food Revenue |
| **Beverage Sales** | 4010 - Beverage Revenue |
| **Alcohol Sales** | 4020 - Alcohol Revenue |
| **Merchandise** | 4030 - Merchandise Revenue |

### **Other Accounts**

| Purpose | GL Account |
|---------|------------|
| **Accounts Payable** | 2000 - Accounts Payable |
| **Cash** | 1010 - Cash - Operating |
| **Credit Card Receivable** | 1120 - Credit Card Receivable |
| **Sales Tax Payable** | 2100 - Sales Tax Payable |

---

## 🔄 Transaction Type Mapping

### **1. Purchase/Receiving (Invoice Processing)**

**Trigger:** Invoice status changes to APPROVED in inventory system
**Frequency:** Real-time (as invoices are approved)

**Inventory Transaction:**
```python
TransactionType.PURCHASE
- master_item_id
- location_id
- quantity_change (positive)
- unit_cost
- total_cost
- invoice_id (reference)
```

**Journal Entry:**
```
Date: Invoice date
Description: "Inventory Purchase - [Vendor Name] - Invoice #[num]"
Location: [Location from invoice]

Dr. Inventory - [Category] (Asset)        $XXX.XX
  Cr. Accounts Payable - [Vendor]         $XXX.XX
```

---

### **2. Daily COGS Calculation**

**Trigger:** Daily batch job (runs at end of business day)
**Frequency:** Daily at 11:59 PM

**Process:**
1. Query all POS_SALE inventory transactions for the day
2. Group by location and category
3. Calculate total cost using weighted average
4. Generate one journal entry per location

**Journal Entry:**
```
Date: Business date
Description: "Daily COGS - [Location] - [Date]"
Location: [Location]

Dr. COGS - Food (Expense)                 $XXX.XX
Dr. COGS - Beverage (Expense)             $XXX.XX
Dr. COGS - Alcohol (Expense)              $XXX.XX
  Cr. Inventory - Food (Asset)            $XXX.XX
  Cr. Inventory - Beverage (Asset)        $XXX.XX
  Cr. Inventory - Alcohol (Asset)         $XXX.XX
```

---

### **3. Waste Recording**

**Trigger:** Waste record created in inventory system
**Frequency:** Real-time (as waste is recorded)

**Inventory Transaction:**
```python
TransactionType.WASTE
- master_item_id
- location_id
- quantity_change (negative)
- unit_cost
- total_cost
- waste_id (reference)
- reason (spoiled, damaged, etc.)
```

**Journal Entry:**
```
Date: Waste date
Description: "Waste - [Reason] - [Item Name]"
Location: [Location from waste record]

Dr. Waste Expense - [Category]            $XXX.XX
  Cr. Inventory - [Category] (Asset)      $XXX.XX
```

---

### **4. Clover Sales Integration**

**Trigger:** Daily batch job OR real-time webhook
**Frequency:** Daily (can be enhanced to real-time later)

**Data Captured:**
- Total sales by category (Food, Beverage, Alcohol)
- Payment methods (Cash, Credit Card, Gift Card)
- Tax collected
- Tips
- Discounts
- Location

**Journal Entry:**
```
Date: Business date
Description: "Daily Sales - [Location] - [Date]"
Location: [Location]

Dr. Cash (if cash sales)                  $XXX.XX
Dr. Credit Card Receivable                $XXX.XX
Dr. Sales Tax Payable (negative = liability increase)  $XXX.XX
  Cr. Food Revenue                        $XXX.XX
  Cr. Beverage Revenue                    $XXX.XX
  Cr. Alcohol Revenue                     $XXX.XX
  Cr. Tip Revenue (or Tip Payable)        $XXX.XX
```

---

### **5. Transfers Between Locations**

**Trigger:** Transfer approved in inventory system
**Frequency:** Real-time

**Inventory Transactions:**
```python
# Location A (sending)
TransactionType.TRANSFER_OUT
- quantity_change (negative)
- location_id = Location A

# Location B (receiving)
TransactionType.TRANSFER_IN
- quantity_change (positive)
- location_id = Location B
```

**Journal Entry:**
```
Date: Transfer date
Description: "Inter-location Transfer - [Item] - Location A → Location B"

Dr. Inventory - [Category] @ Location B   $XXX.XX
  Cr. Inventory - [Category] @ Location A $XXX.XX
```

**Note:** Both lines tagged with respective area_id in accounting system

---

## 💾 Database Schema Changes

### **Accounting System**

**New Table: `inventory_sync_log`**
```sql
CREATE TABLE inventory_sync_log (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(50) NOT NULL,  -- 'purchase', 'cogs', 'waste', 'sales', 'transfer'
    inventory_transaction_id INTEGER,
    invoice_id INTEGER,
    waste_id INTEGER,
    pos_sale_id INTEGER,
    journal_entry_id INTEGER REFERENCES journal_entries(id),
    status VARCHAR(20) NOT NULL,  -- 'pending', 'success', 'error'
    error_message TEXT,
    sync_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_inventory_sync_type ON inventory_sync_log(sync_type);
CREATE INDEX idx_inventory_sync_status ON inventory_sync_log(status);
CREATE INDEX idx_inventory_sync_journal ON inventory_sync_log(journal_entry_id);
```

**Purpose:** Track all inventory-to-accounting synchronizations for audit and reconciliation

---

### **Inventory System**

**New Column: `master_items.accounting_posted`**
```sql
ALTER TABLE master_items
ADD COLUMN accounting_category VARCHAR(50);  -- 'Food', 'Beverage', 'Alcohol', 'Supplies'

UPDATE master_items
SET accounting_category = category
WHERE accounting_category IS NULL;
```

**New Column: `inventory_transactions.journal_entry_posted`**
```sql
ALTER TABLE inventory_transactions
ADD COLUMN journal_entry_posted BOOLEAN DEFAULT FALSE,
ADD COLUMN journal_entry_id INTEGER,
ADD COLUMN journal_entry_date TIMESTAMP WITH TIME ZONE;

CREATE INDEX idx_inventory_txn_posted ON inventory_transactions(journal_entry_posted);
```

---

## 🔧 Implementation Components

### **Component 1: Weighted Average Cost Calculator**

**Location:** `/opt/restaurant-system/inventory/src/restaurant_inventory/services/costing.py`

```python
class WeightedAverageCostService:
    """
    Calculates weighted average cost for inventory items
    """

    def calculate_weighted_average(self, master_item_id: int, location_id: int):
        """
        Calculate weighted average cost based on purchase history
        """
        # Query recent purchases
        # Calculate: Sum(qty * cost) / Sum(qty)
        # Update master_item.current_cost
        pass

    def get_current_cost(self, master_item_id: int, location_id: int):
        """
        Get current weighted average cost for an item at a location
        """
        pass
```

---

### **Component 2: Journal Entry Generator Service**

**Location:** `/opt/restaurant-system/accounting/src/accounting/services/inventory_sync.py`

```python
class InventorySyncService:
    """
    Generates accounting journal entries from inventory transactions
    """

    async def process_purchase(self, invoice_id: int):
        """Process invoice and create AP journal entry"""
        pass

    async def process_daily_cogs(self, business_date: date, location_id: int):
        """Generate daily COGS journal entry"""
        pass

    async def process_waste(self, waste_id: int):
        """Process waste and create expense journal entry"""
        pass

    async def process_daily_sales(self, business_date: date, location_id: int):
        """Process Clover sales and create revenue journal entry"""
        pass

    async def process_transfer(self, transfer_id: int):
        """Process inter-location transfer"""
        pass
```

---

### **Component 3: Integration API Endpoints**

**Inventory System Endpoints:**
```
POST /inventory/api/accounting/trigger-purchase/{invoice_id}
POST /inventory/api/accounting/trigger-waste/{waste_id}
POST /inventory/api/accounting/trigger-transfer/{transfer_id}
GET  /inventory/api/accounting/cogs-data/{date}/{location_id}
```

**Accounting System Endpoints:**
```
POST /accounting/api/inventory-sync/purchase
POST /accounting/api/inventory-sync/cogs
POST /accounting/api/inventory-sync/waste
POST /accounting/api/inventory-sync/sales
POST /accounting/api/inventory-sync/transfer
GET  /accounting/api/inventory-sync/status/{sync_log_id}
```

---

### **Component 4: Batch Processor**

**Location:** `/opt/restaurant-system/accounting/src/accounting/services/batch_processor.py`

```python
class BatchProcessor:
    """
    Handles end-of-day batch processing
    """

    async def run_daily_cogs(self, business_date: date):
        """
        Run COGS posting for all locations
        """
        # For each location:
        #   1. Get COGS data from inventory system
        #   2. Generate journal entry
        #   3. Mark transactions as posted
        #   4. Log sync status
        pass

    async def run_daily_sales(self, business_date: date):
        """
        Run sales posting for all locations
        """
        pass
```

---

## 📅 Implementation Phases

### **Phase 1: Foundation (Days 1-2)**
- ✅ Design integration architecture
- Create database schema changes
- Build weighted average cost calculator
- Create inventory_sync_log table
- Build basic API structure

### **Phase 2: Purchase Integration (Day 2)**
- Implement purchase journal entry generation
- Create API endpoints for invoice posting
- Test with sample invoices
- Handle multi-line invoices

### **Phase 3: COGS Integration (Day 3)**
- Implement daily COGS calculation
- Build batch processor
- Create COGS journal entry generator
- Test with sample sales data

### **Phase 4: Waste & Transfers (Day 4)**
- Implement waste journal entry generation
- Implement transfer journal entry generation
- Test waste scenarios
- Test inter-location transfers

### **Phase 5: Clover Sales Integration (Day 4-5)**
- Research Clover API
- Build Clover data fetcher
- Implement sales journal entry generation
- Test with sample sales data

### **Phase 6: Testing & Documentation (Day 5)**
- End-to-end integration testing
- Create sample data scenarios
- Write user documentation
- Create admin guide for troubleshooting

---

## 🧪 Testing Strategy

### **Test Scenarios**

1. **Purchase Test:**
   - Create sample invoice with 3 items (Food, Beverage, Alcohol)
   - Approve invoice
   - Verify journal entry created
   - Verify AP balance increased
   - Verify inventory value increased

2. **COGS Test:**
   - Record sample POS sales
   - Run daily COGS batch
   - Verify journal entry created
   - Verify COGS expense recorded
   - Verify inventory value decreased

3. **Waste Test:**
   - Record waste (spoiled food)
   - Verify journal entry created
   - Verify waste expense recorded
   - Verify inventory value decreased

4. **Transfer Test:**
   - Transfer item from Location A to Location B
   - Verify journal entry created
   - Verify Location A inventory decreased
   - Verify Location B inventory increased

5. **Multi-Location Test:**
   - Run COGS for multiple locations
   - Verify separate journal entries per location
   - Verify location tagging on journal lines

---

## 🔐 Security & Access Control

- Integration API endpoints require authentication
- Use service account for batch processing
- Log all integration activities
- Implement retry logic for failed transactions
- Alert on repeated failures

---

## 📊 Reporting & Reconciliation

### **Daily Reconciliation Report**
- Inventory value by category and location
- COGS by category and location
- Waste by reason code
- Failed sync transactions

### **Month-End Reconciliation**
- Compare inventory system value to GL balance
- Identify and resolve discrepancies
- Generate variance report

---

## ⚠️ Error Handling

### **Retry Logic**
- Failed transactions logged to `inventory_sync_log`
- Automatic retry (3 attempts with exponential backoff)
- Email alert on persistent failures

### **Common Errors**
- Missing GL accounts → Create default accounts on first run
- Duplicate posting → Check sync_log before posting
- Cost calculation errors → Use default cost method
- Network errors → Queue for retry

---

## 🚀 Deployment Plan

1. Create database migrations
2. Deploy accounting service updates
3. Deploy inventory service updates
4. Run initial account setup script
5. Test with sample data
6. Enable real-time triggers
7. Schedule daily batch jobs
8. Monitor for 1 week
9. Go live with real data

---

## 📝 Configuration

**Environment Variables:**
```bash
# Accounting System
INVENTORY_API_URL=http://inventory-app:8000
INVENTORY_API_KEY=<secret>
ENABLE_INVENTORY_SYNC=true
COGS_BATCH_TIME=23:59
SALES_BATCH_TIME=23:55

# Inventory System
ACCOUNTING_API_URL=http://accounting-app:8000
ACCOUNTING_API_KEY=<secret>
```

---

## 📚 Next Steps

1. ✅ Get approval on design
2. Create database migrations
3. Build weighted average cost calculator
4. Implement purchase integration
5. Implement COGS batch processing
6. Implement waste integration
7. Implement Clover sales integration
8. End-to-end testing
9. Documentation
10. Go live

---

**Status:** Ready for implementation
**Estimated Completion:** 5 days
**Risk Level:** Medium (new integration, multiple systems)
