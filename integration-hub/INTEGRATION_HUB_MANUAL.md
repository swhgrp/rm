# Integration Hub - User Manual

## What Is the Integration Hub?

The Integration Hub is the invoice processing center for SW Hospitality Group. It receives vendor invoices (by email or manual upload), extracts the line items, maps them to your inventory and accounting systems, and pushes the data where it needs to go.

**URL:** `https://rm.swhgrp.com/hub/`

**In short:** Invoices come in, get parsed, get mapped, and get sent to Inventory and Accounting.

---

## Navigation

The sidebar on the left provides access to everything:

| Page | What It Does |
|------|-------------|
| **Dashboard** | Overview of invoice status, quick actions, recent invoices |
| **Invoices** | Full invoice list with filtering and search |
| **Unmapped Items** | Items from invoices that haven't been linked to inventory yet |
| **Vendor Items** | Catalog of products each vendor sells |
| **Expense Items** | Items mapped to GL expense accounts only (not tracked in inventory) |
| **Vendors** | Vendor master list, aliases, and merging |
| **Settings** | Email capture, parsing rules, system configuration |

---

## How Invoices Flow Through the System

Every invoice follows this path:

```
Received → Parsed → Mapping → Ready → Sent
```

| Status | What It Means | What To Do |
|--------|--------------|------------|
| **Pending** | Invoice received, waiting to be parsed | Wait — parsing happens automatically |
| **Pending CSV** | CSV file uploaded, needs format-specific parsing | Click "Parse CSV" on the Invoices page |
| **Mapping** | Parsed successfully, but some items aren't linked to inventory yet | Go to the invoice detail or Unmapped Items to map them |
| **Ready** | All items mapped, ready to send | Click "Send" on the Invoices page |
| **Sent** | Delivered to Inventory and Accounting | Done — view for reference |
| **Error** | Send failed (missing location, GL account, etc.) | Open the invoice, fix the issue, try again |
| **Parse Failed** | Could not extract data from the PDF after multiple attempts | Re-parse manually or enter items by hand |
| **Statement** | Reference document, not a real invoice | No action needed — kept for records |
| **Duplicate** | Flagged as a possible duplicate of another invoice | Review on the Duplicates page |

---

## Dashboard

The Dashboard (`/hub/`) is your starting point. It shows:

- **Summary cards** — Total invoices, Pending Mapping, Ready to Send, Sent
- **Alerts** — Parse failures, errors, or items needing attention
- **Recent invoices** — Quick access to the 10 most recent invoices
- **Upload Invoice** button — Start a manual upload

---

## Uploading an Invoice

### Manual Upload

1. Click **Upload Invoice** on the Invoices page
2. Select your **PDF file**
3. Click **Upload & Parse**

That's it — the AI automatically extracts the vendor, invoice number, date, amounts, and all line items from the PDF. You don't need to enter any of that manually.

After parsing (usually 30-60 seconds), you're taken to a **Review page** that shows:
- The original PDF on the left
- The extracted data on the right (vendor, invoice number, date, location, line items)

On the review page:
1. **Verify** the vendor was matched correctly (if not, select the right one from the dropdown)
2. **Check** the invoice number, date, and amounts
3. **Select a location** if the system didn't auto-detect it
4. **Review the line items** — correct any quantities, prices, or descriptions the parser got wrong
5. Click **Save Invoice**

The invoice is then created in "mapping" status so you can link items to inventory.

### Email Capture (Automatic)

If email capture is configured in Settings, the system automatically:
1. Checks the configured email inbox on a schedule (default: every 5 minutes)
2. Downloads PDF attachments from new messages
3. Creates invoice records with source "email"
4. Parses them in the background
5. They appear on the Dashboard and Invoices page ready for mapping

---

## Invoices Page

The Invoices page (`/hub/invoices`) is the main worklist. It shows all invoices with tabs to filter by status:

- **Pending** — Awaiting parsing or mapping
- **Ready** — Fully mapped, waiting to be sent
- **Sent** — Already delivered to systems
- **Statements** — Reference documents
- **Errors** — Failed to send
- **Duplicates** — Possible duplicates
- **All** — Everything

### What You Can Do Here

- **Search** — Type to filter by invoice number, vendor, or amount
- **Sort** — Click column headers to sort
- **View** — Click the eye icon to open invoice detail
- **Send** — Click the send icon on "Ready" invoices to push to systems
- **Parse CSV** — For CSV-format invoices
- **Mark as Statement** — For non-invoice documents
- **Delete** — Remove an invoice (use with caution)

---

## Invoice Detail Page

Opening an invoice shows the full detail view with:

### Invoice Header
- Invoice number and vendor name
- **View PDF** / **Download PDF** buttons to see the original document
- **Re-parse Invoice** button if the parsing needs to be redone
- **Edit Invoice** to correct header fields

### Invoice Information Card
- Vendor, Location, Invoice Date, Due Date
- Subtotal, Tax, Total Amount
- Current status badge
- Source (Email or Manual)

### Line Items Table

Each parsed line item shows:

| Column | Description |
|--------|-------------|
| **Description** | Item name as it appears on the invoice |
| **Item Code** | Vendor's product code/SKU |
| **Qty** | Quantity ordered |
| **Unit** | Unit of measure (CS, EA, LB, etc.) |
| **Unit Price** | Price per unit |
| **Total** | Line total |
| **Pack Size** | How the item is packaged (e.g., "6 x 750ml bottle") |
| **GL Accounts** | Asset and COGS account numbers |
| **Status** | Mapped, UOM Needed, or Unmapped |

### Status Badges

- **Mapped** (green checkmark) — Item is linked to a vendor item with complete UOM data
- **UOM Needed** (orange warning) — Item is mapped to a vendor item, but the vendor item is missing size/container information. The item won't sync to Inventory or Accounting until the UOM is completed on the Vendor Item Detail page
- **Unmapped** (red) — Item is not linked to anything yet. Needs to be mapped

### Mapping an Item

1. Click the **Map** button on an unmapped line item
2. The mapping modal opens with:
   - Search field to find the vendor item by name, SKU, or category
   - Auto-suggestions based on the item description
   - GL account selectors (Asset, COGS, Waste)
3. Select the correct vendor item
4. GL accounts fill in automatically based on the item's category
5. Click **Save**

The mapping is "learned" — next time the same item description appears on a future invoice, it will be auto-mapped.

### Sending an Invoice

Once all items are mapped:
1. The invoice status becomes **Ready**
2. Click **Send to Systems** at the bottom of the page
3. The system calculates costs and GL postings:
   - Looks up each vendor item's UOM and conversion factor
   - Calculates cost per inventory unit
   - Creates GL journal entries
4. Pushes to **Inventory** (updates location costs) and **Accounting** (creates GL entries)
5. Status changes to **Sent**

---

## Unmapped Items Page

The Unmapped Items page (`/hub/unmapped-items`) shows a consolidated view of all invoice line items that haven't been mapped yet. Instead of showing every individual line, it groups by unique item description.

### What You See

| Column | Description |
|--------|-------------|
| **Description** | How the item appears on invoices |
| **Item Code** | Vendor product code (if parsed) |
| **Occurrences** | How many invoice lines have this same item |
| **Vendors** | Which vendors sell it |
| **Code Status** | Whether the item code is verified, in inventory, suspicious, or unknown |

### Mapping Items

**Single item:**
1. Click **Map** on any item
2. Search for the vendor item
3. Assign GL accounts
4. Save — applies to all occurrences of that item

**Bulk mapping:**
1. Check multiple items using the checkboxes
2. Click **Map Selected**
3. Choose a common vendor item or GL account
4. Apply to all selected items at once

---

## Vendor Items Page

The Vendor Items page (`/hub/vendor-items`) is the catalog of products each vendor sells. This is the **source of truth** for product data — Inventory reads from here.

### What You See

Each vendor item shows:
- **Product Name** — How the vendor names the product
- **Vendor** — Which vendor
- **SKU** — Vendor's item code
- **Category** — Inventory category
- **Purchase Unit** — What unit the vendor sells in (Case, Each, Pound, etc.)
- **Status** — Active, Needs Review, or Inactive

### Filtering

- **Search** by product name, SKU, or vendor
- **Vendor filter** dropdown to show only one vendor's products
- **Status filter** to show Active, Needs Review, or Inactive items

### Vendor Item Detail

Click on any vendor item to open its detail page (`/hub/vendor-item-detail`), which shows:

**Product Information:**
- Vendor, SKU, Product Name, Description
- Category, Pack Size

**Pricing:**
- Last Purchase Price and Previous Price
- Price change indicator (up/down)

**Purchase UOMs:**
This section is critical for accurate cost calculations. Each vendor item can have multiple purchase UOMs:

| Example | UOM | Conversion Factor | Meaning |
|---------|-----|-------------------|---------|
| Tito's Vodka | CS (Case) | 12 | 1 case = 12 bottles |
| Tito's Vodka | EA (Each) | 1 | 1 each = 1 bottle |
| Ground Beef | CS (Case) | 10 | 1 case = 10 lbs |
| Ground Beef | LB (Pound) | 1 | 1 lb = 1 lb |

The **conversion factor** tells the system how to calculate cost per inventory unit:
- Invoice says: 1 Case of Tito's @ $306
- Conversion factor for CS = 12
- Cost per bottle = $306 / 12 = **$25.50**

You can **Add**, **Edit**, or **Remove** UOMs from the detail page.

**Size & Container:**
- Size Quantity (e.g., 750)
- Size Unit (e.g., ml)
- Container (e.g., bottle)
- Units Per Case (e.g., 12)

These fields must be filled in for the item to sync to Inventory and Accounting. If they're missing, the invoice detail page will show "UOM Needed" on any line items using this vendor item.

**Inventory Link:**
- Shows which master item in Inventory this vendor item maps to
- Category assignment

---

## Expense Items Page

The Expense Items page (`/hub/expense-items`) manages items that are mapped to GL expense accounts but are **not tracked in inventory**. These are things like:

- Office supplies
- Cleaning services
- Equipment rentals
- Professional services

Each expense item has:
- Description and Item Code
- GL Expense Account number
- Vendor (if known)
- How many invoices reference it

---

## Vendors Page

The Vendors page (`/hub/vendors`) manages the master vendor list.

### Vendor Table

Each vendor shows:
- **Name** — Canonical vendor name
- **Aliases** — Alternative names (how they appear on invoices)
- **Invoice Count** — How many invoices from this vendor
- **Contact Info** — Contact person, phone, email
- **Payment Terms** — Net 30, COD, etc.
- **Sync Status** — Whether synced to Inventory and Accounting

### Adding a Vendor

1. Click **Add New Vendor**
2. Fill in: Name, Contact, Email, Phone, Address, Payment Terms
3. Optionally check "Sync to Inventory" and/or "Sync to Accounting"
4. Click **Save**

### Vendor Aliases

Vendors often appear with different names on invoices. For example, "Gordon Food Service" might appear as "GFS", "GORDON FOOD SVC", or "Gordon Food Svc Inc" on different invoices.

**Aliases** tell the system that all these names refer to the same vendor.

To manage aliases:
1. Click **Manage Aliases** on the Vendors page
2. You'll see:
   - Existing aliases and which vendor they map to
   - Unlinked invoice vendor names (names the system doesn't recognize)
3. For each unlinked name, click **Link** and select the correct vendor
4. Or click **Auto-Create from Invoices** to automatically generate aliases from existing linked invoices

### Merging Vendors

If the same vendor was accidentally created twice:
1. Check both vendors in the table
2. Click **Merge Selected**
3. Choose the primary vendor to keep
4. The other vendor's name becomes an alias
5. All invoices are reassigned to the primary vendor

---

## Settings Page

The Settings page (`/hub/settings`) controls system configuration.

### Email Invoice Capture

Configure automatic invoice receipt via email:

| Field | Description |
|-------|-------------|
| **Email Address** | The AP inbox that receives invoices |
| **IMAP Server** | Email server (e.g., `imap.gmail.com`) |
| **IMAP Port** | Usually 993 for SSL |
| **Username** | Login username |
| **Password** | App password (Gmail requires App Passwords, not your regular password) |
| **Check Interval** | How often to check for new emails (minutes) |

**Buttons:**
- **Test Connection** — Verify credentials work
- **Check Email Now** — Force an immediate check
- **Save Settings** — Save configuration

### Vendor Parsing Rules

Each vendor can have custom parsing rules to help the AI parser understand their invoice format. For example:

- Gordon Food Service: "Use Qty Ship column for quantity, not Qty Ord"
- Southern Glazer's: "Item code is in the first column, not the barcode"

These rules are set per vendor and include:
- Column name mappings
- AI parsing instructions (free-form text hints)
- Notes for internal reference

### Additional Settings Pages

- **Size Units & Containers** (`/hub/settings/size`) — Manage units of measure (EA, CS, LB, oz, etc.) and container types (bottle, can, bag, etc.)
- **Category Mappings** (`/hub/category-mappings`) — Link inventory categories to GL accounts
- **Item Codes** (`/hub/item-codes`) — Verify and manage vendor item codes

---

## Common Tasks — Step by Step

### Process a New Invoice (Manual Upload)

1. **Invoices** → Click **Upload Invoice**
2. Select the PDF file and click **Upload & Parse**
3. Wait 30-60 seconds for AI parsing
4. **Review** the extracted data — verify vendor, invoice number, date, amounts, and line items
5. **Select the location** (required for cost updates)
6. Click **Save Invoice**
7. Go to **Unmapped Items** if any items need mapping
8. Map each item to its vendor item and GL accounts
9. Once all items are mapped, go to **Invoices** → click **Send**
10. Invoice is delivered to Inventory and Accounting

### Map a New Item for the First Time

1. Go to **Unmapped Items** or open the invoice detail
2. Click **Map** on the item
3. **Search** for the vendor item by name or SKU
4. Select the correct match
5. GL accounts fill in automatically — adjust if needed
6. Click **Save**
7. Future invoices with the same item description will auto-map

### Fix a "UOM Needed" Warning

1. On the invoice detail page, note which items show the orange "UOM Needed" badge
2. Click on the vendor item name to open its detail page
3. In the **Purchase UOMs** section, verify UOMs are set up with correct conversion factors
4. In the **Size & Container** section, fill in:
   - **Size Quantity** (e.g., 750 for a 750ml bottle)
   - **Size Unit** (e.g., ml)
   - **Container** (e.g., bottle)
   - **Units Per Case** (e.g., 12 for a 12-pack)
5. Save the vendor item
6. Return to the invoice — the badge should now show green "Mapped"

### Add a Vendor Alias

1. Go to **Vendors** → click **Manage Aliases**
2. Scroll to "Unlinked Invoice Vendor Names"
3. Find the name that the system doesn't recognize
4. Click **Link** and select the correct vendor from the dropdown
5. Future invoices with that name will automatically link to the vendor

### Handle a Duplicate Invoice

1. Go to **Invoices** → click the **Duplicates** tab
2. Review each group of potential duplicates
3. Compare invoice numbers, dates, and amounts
4. Click **Keep & Discard** to keep the correct one and remove the duplicate
5. Or click **Keep All** if both are legitimate (e.g., different delivery dates)

### Re-Parse an Invoice

If the AI parser got something wrong (wrong quantities, prices, or item descriptions):

1. Open the invoice detail page
2. Click **Re-parse Invoice**
3. The system re-extracts data from the original PDF
4. Review the updated line items

**Note:** Re-parsing creates new item records and removes old ones. Any manual corrections or mappings on the previous items will be lost. Items that were auto-mapped will be re-mapped automatically.

### Mark a Document as Statement

Statements and non-invoice documents don't need to go through the mapping and send process:

1. On the **Invoices** page or **Dashboard**, find the document
2. Click the **Mark as Statement** button
3. The document is kept for reference but won't be sent to any system

---

## Understanding Cost Calculations

When an invoice is sent to systems, the Hub calculates costs like this:

### Standard Items (Case Pricing)

```
Invoice line:  2 CS of Chicken Wings @ $45.00/CS
Vendor item:   CS conversion factor = 6 (6 bags per case)

Cost per bag = $45.00 / 6 = $7.50
Total cost   = 2 cases × $45.00 = $90.00
```

### Catch-Weight Items (Variable Weight)

Some items (fresh meat, seafood) are priced per pound with variable weight:

```
Invoice line:  50.1 LB of Beef Sirloin @ $10.02/LB
Vendor item:   LB conversion factor = 1

Cost per lb  = $10.02
Total cost   = 50.1 × $10.02 = $502.00
```

### Per-Unit Items

Some vendors price by the individual unit:

```
Invoice line:  12 EA of Wine Glasses @ $3.50/EA
Vendor item:   EA conversion factor = 1

Cost per each = $3.50
Total cost    = 12 × $3.50 = $42.00
```

The conversion factor on the vendor item's UOM determines how costs are calculated. If it's wrong, costs will be wrong — so it's important to verify UOM setup when adding new vendor items.

---

## Troubleshooting

### Invoice Stuck in "Pending"
- Parsing may still be in progress — wait a few minutes
- If it stays pending, click **Re-parse** on the invoice detail page
- Check that OCR is configured in Settings if using scanned PDFs

### Vendor Shows "Unmatched" on Invoice
- The vendor name from the invoice doesn't match any vendor in the system
- Go to **Vendors** → **Manage Aliases** → link the unrecognized name to the correct vendor

### Wrong Prices After Sending to Inventory
- Check the vendor item's UOM conversion factor — an incorrect factor will produce wrong costs
- Verify the correct UOM was matched (CS vs EA vs LB)
- Open the vendor item detail page and review the Purchase UOMs section

### "UOM Needed" on Many Items
- This means vendor items are missing size/container data
- These items won't sync until the data is filled in
- Open each vendor item and complete the Size & Container fields

### Email Invoices Not Arriving
- Go to **Settings** → **Test Connection** to verify credentials
- For Gmail, make sure you're using an App Password (not your regular password)
- Check the interval — emails are checked every N minutes, not instantly
- Click **Check Email Now** to force an immediate check

### Duplicate Invoice Detected
- Go to the **Duplicates** tab on the Invoices page
- Review both invoices to determine which is the duplicate
- Use **Keep & Discard** or **Keep All** as appropriate
