"""
Vendor Service

Handles vendor lookups, alias resolution, and vendor management.
"""
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from accounting.models.vendor import Vendor
from accounting.models.vendor_alias import VendorAlias


class VendorService:
    """Service for vendor-related operations"""

    def __init__(self, db: Session):
        self.db = db

    def resolve_vendor_name(self, vendor_name: str) -> Tuple[Optional[Vendor], bool]:
        """
        Resolve a vendor name to a canonical vendor.

        Attempts to find a vendor by:
        1. Exact match on vendor.vendor_name
        2. Case-insensitive match on vendor.vendor_name
        3. Exact match on vendor_aliases.alias_name
        4. Case-insensitive match on vendor_aliases.alias_name

        Args:
            vendor_name: The vendor name from an invoice

        Returns:
            Tuple of (Vendor or None, was_alias_match: bool)
            - Vendor: The matched vendor, or None if no match
            - was_alias_match: True if matched via alias, False if direct match
        """
        if not vendor_name:
            return None, False

        vendor_name = vendor_name.strip()

        # 1. Try exact match on vendor_name
        vendor = self.db.query(Vendor).filter(
            Vendor.vendor_name == vendor_name,
            Vendor.is_active == True
        ).first()

        if vendor:
            return vendor, False

        # 2. Try case-insensitive match on vendor_name
        vendor = self.db.query(Vendor).filter(
            func.lower(Vendor.vendor_name) == func.lower(vendor_name),
            Vendor.is_active == True
        ).first()

        if vendor:
            return vendor, False

        # 3. Try exact match on alias
        alias = self.db.query(VendorAlias).filter(
            VendorAlias.alias_name == vendor_name
        ).first()

        if alias:
            vendor = self.db.query(Vendor).filter(
                Vendor.id == alias.vendor_id,
                Vendor.is_active == True
            ).first()
            if vendor:
                return vendor, True

        # 4. Try case-insensitive match on alias
        alias = self.db.query(VendorAlias).filter(
            func.lower(VendorAlias.alias_name) == func.lower(vendor_name),
            VendorAlias.case_insensitive == True
        ).first()

        if alias:
            vendor = self.db.query(Vendor).filter(
                Vendor.id == alias.vendor_id,
                Vendor.is_active == True
            ).first()
            if vendor:
                return vendor, True

        return None, False

    def get_or_create_vendor(
        self,
        vendor_name: str,
        create_if_not_found: bool = True,
        default_payment_terms: str = "Net 30"
    ) -> Tuple[Optional[Vendor], bool, bool]:
        """
        Get a vendor by name, creating if necessary.

        Args:
            vendor_name: The vendor name to look up
            create_if_not_found: If True, create a new vendor if no match found
            default_payment_terms: Payment terms for newly created vendors

        Returns:
            Tuple of (Vendor or None, was_created: bool, was_alias_match: bool)
        """
        vendor, was_alias = self.resolve_vendor_name(vendor_name)

        if vendor:
            return vendor, False, was_alias

        if not create_if_not_found:
            return None, False, False

        # Create new vendor
        new_vendor = Vendor(
            vendor_name=vendor_name.strip(),
            payment_terms=default_payment_terms,
            is_active=True
        )
        self.db.add(new_vendor)
        self.db.flush()  # Get the ID

        return new_vendor, True, False

    def add_alias(
        self,
        alias_name: str,
        vendor_id: int,
        case_insensitive: bool = True,
        created_by: Optional[int] = None
    ) -> VendorAlias:
        """
        Add an alias for a vendor.

        Args:
            alias_name: The alias name (e.g., "Gordon Food Service Inc.")
            vendor_id: The canonical vendor ID
            case_insensitive: Whether to match case-insensitively
            created_by: User ID who created the alias

        Returns:
            The created VendorAlias
        """
        alias = VendorAlias(
            alias_name=alias_name.strip(),
            vendor_id=vendor_id,
            case_insensitive=case_insensitive,
            created_by=created_by
        )
        self.db.add(alias)
        self.db.flush()
        return alias

    def get_aliases_for_vendor(self, vendor_id: int) -> list[VendorAlias]:
        """Get all aliases for a vendor"""
        return self.db.query(VendorAlias).filter(
            VendorAlias.vendor_id == vendor_id
        ).all()

    def delete_alias(self, alias_id: int) -> bool:
        """Delete an alias by ID"""
        alias = self.db.query(VendorAlias).filter(VendorAlias.id == alias_id).first()
        if alias:
            self.db.delete(alias)
            return True
        return False
