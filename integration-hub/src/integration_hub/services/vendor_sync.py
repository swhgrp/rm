"""
Vendor sync service - fetches vendors from Inventory and Accounting systems
and pushes new vendors to both systems
"""

import asyncio
import httpx
import logging
import os
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from integration_hub.models.vendor import Vendor

logger = logging.getLogger(__name__)

# Internal API key for Hub-to-system communication - MUST be set via environment
HUB_INTERNAL_API_KEY = os.getenv("HUB_INTERNAL_API_KEY")
if not HUB_INTERNAL_API_KEY:
    raise ValueError("HUB_INTERNAL_API_KEY environment variable must be set")


class VendorSyncService:
    """Service for syncing vendors across systems"""

    def __init__(self):
        self.inventory_api_url = os.getenv("INVENTORY_API_URL", "http://inventory-app:8000/api")
        self.accounting_api_url = os.getenv("ACCOUNTING_API_URL", "http://accounting-app:8000/api")
        self.hub_api_headers = {"X-Hub-API-Key": HUB_INTERNAL_API_KEY}
        self.client = httpx.AsyncClient(timeout=30.0)

    async def fetch_inventory_vendors(self) -> List[Dict]:
        """Fetch all vendors from Inventory system"""
        try:
            response = await self.client.get(
                f"{self.inventory_api_url}/vendors/_hub/sync",
                headers=self.hub_api_headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching inventory vendors: {e}")
            return []

    async def fetch_accounting_vendors(self) -> List[Dict]:
        """Fetch all vendors from Accounting system"""
        try:
            response = await self.client.get(
                f"{self.accounting_api_url}/vendors/_hub/sync",
                headers=self.hub_api_headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching accounting vendors: {e}")
            return []

    async def sync_vendors_to_hub(self, db: Session) -> Dict:
        """
        Fetch vendors from both systems and sync to Hub database
        Returns summary of sync operation
        """
        inventory_vendors, accounting_vendors = await asyncio.gather(
            self.fetch_inventory_vendors(),
            self.fetch_accounting_vendors(),
            return_exceptions=True
        )

        if isinstance(inventory_vendors, Exception):
            inventory_vendors = []
        if isinstance(accounting_vendors, Exception):
            accounting_vendors = []

        # Track sync results
        created = 0
        updated = 0
        errors = []

        # Import VendorAlias for alias matching
        from integration_hub.models.vendor_alias import VendorAlias

        # Sync inventory vendors
        for inv_vendor in inventory_vendors:
            try:
                vendor_name = inv_vendor.get("name")

                # Skip inactive vendors - they were likely deactivated during a merge
                if not inv_vendor.get("is_active", True):
                    continue

                # Try to find existing vendor by inventory ID
                vendor = db.query(Vendor).filter(
                    Vendor.inventory_vendor_id == inv_vendor.get("id")
                ).first()

                # If not found by ID, try to match by name (case-insensitive)
                if not vendor and vendor_name:
                    from sqlalchemy import func
                    vendor = db.query(Vendor).filter(
                        func.lower(Vendor.name) == func.lower(vendor_name)
                    ).first()

                # If still not found, check if name matches an alias (merged vendor)
                if not vendor and vendor_name:
                    from sqlalchemy import func
                    alias = db.query(VendorAlias).filter(
                        func.lower(VendorAlias.alias_name) == func.lower(vendor_name),
                        VendorAlias.is_active == True
                    ).first()
                    if alias:
                        vendor = db.query(Vendor).filter(Vendor.id == alias.vendor_id).first()

                if vendor:
                    # Update existing vendor
                    # Store inventory ID if not already set
                    if not vendor.inventory_vendor_id:
                        vendor.inventory_vendor_id = inv_vendor.get("id")

                    # Update fields from inventory (only if not already set or if inventory has better data)
                    if inv_vendor.get("name"):
                        vendor.name = inv_vendor.get("name")
                    if inv_vendor.get("contact_name"):
                        vendor.contact_name = inv_vendor.get("contact_name")
                    if inv_vendor.get("email"):
                        vendor.email = inv_vendor.get("email")
                    if inv_vendor.get("phone"):
                        vendor.phone = inv_vendor.get("phone")
                    if inv_vendor.get("address"):
                        vendor.address = inv_vendor.get("address")
                    vendor.is_active = inv_vendor.get("is_active", True)
                    updated += 1
                else:
                    # Create new vendor
                    vendor = Vendor(
                        name=vendor_name,
                        contact_name=inv_vendor.get("contact_name"),
                        email=inv_vendor.get("email"),
                        phone=inv_vendor.get("phone"),
                        address=inv_vendor.get("address"),
                        is_active=inv_vendor.get("is_active", True),
                        inventory_vendor_id=inv_vendor.get("id")
                    )
                    db.add(vendor)
                    created += 1

            except Exception as e:
                errors.append(f"Error syncing inventory vendor {inv_vendor.get('name')}: {str(e)}")

        # Flush inventory vendors to make them visible to accounting vendor queries
        db.flush()

        # Sync accounting vendors
        for acc_vendor in accounting_vendors:
            try:
                vendor_name = acc_vendor.get("name")

                # Skip inactive vendors - they were likely deactivated during a merge
                if not acc_vendor.get("is_active", True):
                    continue

                # Try to find by accounting ID first
                vendor = db.query(Vendor).filter(
                    Vendor.accounting_vendor_id == acc_vendor.get("id")
                ).first()

                # If not found by ID, try to match by name (case-insensitive)
                if not vendor and vendor_name:
                    from sqlalchemy import func
                    vendor = db.query(Vendor).filter(
                        func.lower(Vendor.name) == func.lower(vendor_name)
                    ).first()

                # If still not found, check if name matches an alias (merged vendor)
                if not vendor and vendor_name:
                    from sqlalchemy import func
                    alias = db.query(VendorAlias).filter(
                        func.lower(VendorAlias.alias_name) == func.lower(vendor_name),
                        VendorAlias.is_active == True
                    ).first()
                    if alias:
                        vendor = db.query(Vendor).filter(Vendor.id == alias.vendor_id).first()

                if vendor:
                    # Update existing vendor - this merges accounting data with existing inventory data
                    # Store accounting ID if not already set
                    if not vendor.accounting_vendor_id:
                        vendor.accounting_vendor_id = acc_vendor.get("id")

                    # Update fields from accounting - accounting is source of truth for tax/payment/address
                    if acc_vendor.get("tax_id"):
                        vendor.tax_id = acc_vendor.get("tax_id")
                    if acc_vendor.get("payment_terms"):
                        vendor.payment_terms = acc_vendor.get("payment_terms")
                    # Accounting is source of truth for address fields - always update if provided
                    if acc_vendor.get("address"):
                        vendor.address = acc_vendor.get("address")
                    if acc_vendor.get("city"):
                        vendor.city = acc_vendor.get("city")
                    if acc_vendor.get("state"):
                        vendor.state = acc_vendor.get("state")
                    if acc_vendor.get("zip_code"):
                        vendor.zip_code = acc_vendor.get("zip_code")

                    # Update contact info if accounting has it and inventory doesn't
                    if acc_vendor.get("contact_name") and not vendor.contact_name:
                        vendor.contact_name = acc_vendor.get("contact_name")
                    if acc_vendor.get("email") and not vendor.email:
                        vendor.email = acc_vendor.get("email")
                    if acc_vendor.get("phone") and not vendor.phone:
                        vendor.phone = acc_vendor.get("phone")

                    updated += 1
                else:
                    # Create new vendor (exists in accounting but not in inventory)
                    vendor = Vendor(
                        name=vendor_name,
                        contact_name=acc_vendor.get("contact_name"),
                        email=acc_vendor.get("email"),
                        phone=acc_vendor.get("phone"),
                        address=acc_vendor.get("address"),
                        city=acc_vendor.get("city"),
                        state=acc_vendor.get("state"),
                        zip_code=acc_vendor.get("zip_code"),
                        tax_id=acc_vendor.get("tax_id"),
                        payment_terms=acc_vendor.get("payment_terms"),
                        is_active=acc_vendor.get("is_active", True),
                        accounting_vendor_id=acc_vendor.get("id")
                    )
                    db.add(vendor)
                    created += 1

            except Exception as e:
                errors.append(f"Error syncing accounting vendor {acc_vendor.get('name')}: {str(e)}")

        # Commit the merged vendors before auto-pushing
        db.commit()

        # Auto-push vendors to systems where they're missing
        pushed_to_inventory = 0
        pushed_to_accounting = 0

        # Get all vendors from Hub to check for missing system IDs
        all_hub_vendors = db.query(Vendor).filter(Vendor.is_active == True).all()

        for hub_vendor in all_hub_vendors:
            # If vendor doesn't exist in Inventory, push it there
            if not hub_vendor.inventory_vendor_id:
                try:
                    result = await self.push_vendor_to_inventory(hub_vendor)
                    if result.get("success"):
                        hub_vendor.inventory_vendor_id = result.get("vendor_id")
                        pushed_to_inventory += 1
                        db.commit()
                except Exception as e:
                    errors.append(f"Error pushing {hub_vendor.name} to Inventory: {str(e)}")

            # If vendor doesn't exist in Accounting, push it there
            if not hub_vendor.accounting_vendor_id:
                try:
                    result = await self.push_vendor_to_accounting(hub_vendor)
                    if result.get("success"):
                        hub_vendor.accounting_vendor_id = result.get("vendor_id")
                        pushed_to_accounting += 1
                        db.commit()
                except Exception as e:
                    errors.append(f"Error pushing {hub_vendor.name} to Accounting: {str(e)}")

        return {
            "success": True,
            "created": created,
            "updated": updated,
            "errors": errors,
            "inventory_vendors_fetched": len(inventory_vendors),
            "accounting_vendors_fetched": len(accounting_vendors),
            "pushed_to_inventory": pushed_to_inventory,
            "pushed_to_accounting": pushed_to_accounting
        }

    async def push_vendor_to_inventory(self, vendor: Vendor) -> Dict:
        """Push a vendor to Inventory system"""
        try:
            payload = {
                "name": vendor.name,
                "contact_name": vendor.contact_name or "",
                "email": vendor.email or "",
                "phone": vendor.phone or "",
                "address": vendor.address or "",
                "is_active": vendor.is_active
            }

            response = await self.client.post(
                f"{self.inventory_api_url}/vendors/_hub/receive",
                json=payload,
                headers=self.hub_api_headers
            )
            response.raise_for_status()
            result = response.json()

            return {
                "success": True,
                "vendor_id": result.get("vendor_id")
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def push_vendor_to_accounting(self, vendor: Vendor) -> Dict:
        """Push a vendor to Accounting system"""
        try:
            payload = {
                "name": vendor.name,
                "contact_name": vendor.contact_name or "",
                "email": vendor.email or "",
                "phone": vendor.phone or "",
                "address": vendor.address or "",
                "city": vendor.city or "",
                "state": vendor.state or "",
                "zip_code": vendor.zip_code or "",
                "tax_id": vendor.tax_id or "",
                "payment_terms": vendor.payment_terms or "Net 30",
                "is_active": vendor.is_active
            }

            response = await self.client.post(
                f"{self.accounting_api_url}/vendors/_hub/receive",
                json=payload,
                headers=self.hub_api_headers
            )
            response.raise_for_status()
            result = response.json()

            return {
                "success": True,
                "vendor_id": result.get("vendor_id")
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def delete_vendor_from_inventory(self, vendor_id: int) -> Dict:
        """Delete a vendor from Inventory system (used during merge)"""
        try:
            response = await self.client.delete(
                f"{self.inventory_api_url}/vendors/_hub/delete/{vendor_id}",
                headers=self.hub_api_headers
            )
            response.raise_for_status()
            return {"success": True}
        except Exception as e:
            logger.error(f"Error deleting vendor {vendor_id} from inventory: {e}")
            return {"success": False, "error": str(e)}

    async def delete_vendor_from_accounting(self, vendor_id: int) -> Dict:
        """Delete a vendor from Accounting system (used during merge)"""
        try:
            response = await self.client.delete(
                f"{self.accounting_api_url}/vendors/_hub/delete/{vendor_id}",
                headers=self.hub_api_headers
            )
            response.raise_for_status()
            return {"success": True}
        except Exception as e:
            logger.error(f"Error deleting vendor {vendor_id} from accounting: {e}")
            return {"success": False, "error": str(e)}

    async def merge_vendor_in_inventory(self, source_id: int, target_id: int) -> Dict:
        """Merge one vendor into another in Inventory system"""
        try:
            response = await self.client.post(
                f"{self.inventory_api_url}/vendors/_hub/merge-into",
                json={"source_vendor_id": source_id, "target_vendor_id": target_id},
                headers=self.hub_api_headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error merging vendor {source_id} into {target_id} in inventory: {e}")
            return {"success": False, "error": str(e)}

    async def merge_vendor_in_accounting(self, source_id: int, target_id: int) -> Dict:
        """Merge one vendor into another in Accounting system"""
        try:
            response = await self.client.post(
                f"{self.accounting_api_url}/vendors/_hub/merge-into",
                json={"source_vendor_id": source_id, "target_vendor_id": target_id},
                headers=self.hub_api_headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error merging vendor {source_id} into {target_id} in accounting: {e}")
            return {"success": False, "error": str(e)}

    async def push_aliases_to_systems(self, db: Session) -> Dict:
        """
        Push Hub's alias state to Inventory and Accounting systems.
        For each alias in Hub, find the corresponding vendor in external systems
        and merge it into the canonical vendor.
        """
        from integration_hub.models.vendor_alias import VendorAlias
        from integration_hub.models.vendor import Vendor

        results = {
            "success": True,
            "inventory_merges": [],
            "accounting_merges": [],
            "errors": []
        }

        # Get all active aliases
        aliases = db.query(VendorAlias).filter(VendorAlias.is_active == True).all()

        for alias in aliases:
            # Get the canonical vendor this alias points to
            canonical_vendor = db.query(Vendor).filter(Vendor.id == alias.vendor_id).first()
            if not canonical_vendor:
                continue

            # Fetch current vendors from both systems
            inventory_vendors = await self.fetch_inventory_vendors()
            accounting_vendors = await self.fetch_accounting_vendors()

            # Find vendor in Inventory that matches the alias name
            for inv_vendor in inventory_vendors:
                if inv_vendor.get("name", "").lower() == alias.alias_name.lower():
                    inv_source_id = inv_vendor.get("id")
                    inv_target_id = canonical_vendor.inventory_vendor_id

                    if inv_source_id and inv_target_id and inv_source_id != inv_target_id:
                        result = await self.merge_vendor_in_inventory(inv_source_id, inv_target_id)
                        if result.get("success"):
                            results["inventory_merges"].append({
                                "alias": alias.alias_name,
                                "merged_into": canonical_vendor.name,
                                "source_id": inv_source_id,
                                "target_id": inv_target_id
                            })
                        else:
                            results["errors"].append(
                                f"Inventory: Failed to merge {alias.alias_name} - {result.get('error')}"
                            )
                    break

            # Find vendor in Accounting that matches the alias name
            for acc_vendor in accounting_vendors:
                if acc_vendor.get("name", "").lower() == alias.alias_name.lower():
                    acc_source_id = acc_vendor.get("id")
                    acc_target_id = canonical_vendor.accounting_vendor_id

                    if acc_source_id and acc_target_id and acc_source_id != acc_target_id:
                        result = await self.merge_vendor_in_accounting(acc_source_id, acc_target_id)
                        if result.get("success"):
                            results["accounting_merges"].append({
                                "alias": alias.alias_name,
                                "merged_into": canonical_vendor.name,
                                "source_id": acc_source_id,
                                "target_id": acc_target_id,
                                "bills_reassigned": result.get("bills_reassigned", 0)
                            })
                        else:
                            results["errors"].append(
                                f"Accounting: Failed to merge {alias.alias_name} - {result.get('error')}"
                            )
                    break

        if results["errors"]:
            results["success"] = False

        return results

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Dependency for FastAPI
_vendor_sync_service = None


def get_vendor_sync_service() -> VendorSyncService:
    """Get vendor sync service instance"""
    global _vendor_sync_service
    if _vendor_sync_service is None:
        _vendor_sync_service = VendorSyncService()
    return _vendor_sync_service


import asyncio
