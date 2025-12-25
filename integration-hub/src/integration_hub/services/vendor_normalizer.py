"""
Vendor Name Normalization Service

Normalizes vendor names using the Hub's vendor alias system.
Hub is the source of truth for:
- Vendors (canonical vendor records)
- Vendor aliases (maps OCR/invoice names to canonical vendors)

When processing invoices:
1. Check alias table for vendor name match
2. If found, link invoice to canonical vendor
3. If not found, suggest creating a new alias or vendor
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text, func, or_

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.vendor import Vendor
from integration_hub.models.vendor_alias import VendorAlias

logger = logging.getLogger(__name__)


def normalize_for_comparison(name: str) -> str:
    """
    Normalize a vendor name for comparison purposes.
    Lowercase, remove extra punctuation/spaces.
    """
    if not name:
        return ""
    normalized = name.lower().strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


class VendorNormalizerService:
    """Service for normalizing and managing vendor names using alias system"""

    def __init__(self, db: Session):
        self.db = db
        self._alias_cache = None
        self._vendor_cache = None

    def _get_alias_map(self) -> Dict[str, Tuple[int, str]]:
        """Get mapping of normalized alias -> (vendor_id, canonical_name)"""
        if self._alias_cache is None:
            aliases = self.db.query(
                VendorAlias, Vendor
            ).join(Vendor).filter(
                VendorAlias.is_active == True,
                Vendor.is_active == True
            ).all()

            self._alias_cache = {}
            for alias, vendor in aliases:
                self._alias_cache[alias.alias_name_normalized] = (vendor.id, vendor.name)

        return self._alias_cache

    def _get_vendor_map(self) -> Dict[int, str]:
        """Get mapping of vendor_id to canonical vendor name"""
        if self._vendor_cache is None:
            vendors = self.db.query(Vendor).filter(Vendor.is_active == True).all()
            self._vendor_cache = {v.id: v.name for v in vendors}
        return self._vendor_cache

    def resolve_vendor(self, vendor_name: str) -> Optional[Tuple[int, str]]:
        """
        Resolve a vendor name to canonical vendor using alias lookup.

        Args:
            vendor_name: Raw vendor name from invoice

        Returns:
            Tuple of (vendor_id, canonical_name) or None if not found
        """
        if not vendor_name:
            return None

        normalized = normalize_for_comparison(vendor_name)
        alias_map = self._get_alias_map()

        if normalized in alias_map:
            return alias_map[normalized]

        # Also check exact vendor name match
        vendor_map = self._get_vendor_map()
        for vid, vname in vendor_map.items():
            if normalize_for_comparison(vname) == normalized:
                return (vid, vname)

        return None

    def create_alias(
        self,
        alias_name: str,
        vendor_id: int,
        source: str = 'manual'
    ) -> Dict:
        """
        Create a new vendor alias.

        Args:
            alias_name: The alias name to create
            vendor_id: Hub vendor ID to link to
            source: Source of the alias ('manual', 'auto', 'migrated')

        Returns:
            Dict with created alias info or error
        """
        # Check vendor exists
        vendor = self.db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not vendor:
            return {'error': f'Vendor with id {vendor_id} not found'}

        normalized = normalize_for_comparison(alias_name)

        # Check if alias already exists
        existing = self.db.query(VendorAlias).filter(
            VendorAlias.alias_name_normalized == normalized
        ).first()

        if existing:
            return {
                'error': f"Alias '{alias_name}' already exists",
                'existing_vendor_id': existing.vendor_id
            }

        # Create alias
        alias = VendorAlias(
            alias_name=alias_name,
            alias_name_normalized=normalized,
            vendor_id=vendor_id,
            source=source,
            is_active=True
        )
        self.db.add(alias)
        self.db.commit()

        # Clear cache
        self._alias_cache = None

        logger.info(f"Created alias '{alias_name}' -> vendor {vendor_id} ({vendor.name})")

        return {
            'alias_id': alias.id,
            'alias_name': alias_name,
            'vendor_id': vendor_id,
            'vendor_name': vendor.name
        }

    def get_all_aliases(self) -> List[Dict]:
        """Get all vendor aliases with their canonical vendors."""
        aliases = self.db.query(
            VendorAlias, Vendor
        ).join(Vendor).filter(
            VendorAlias.is_active == True
        ).order_by(Vendor.name, VendorAlias.alias_name).all()

        return [
            {
                'alias_id': alias.id,
                'alias_name': alias.alias_name,
                'vendor_id': vendor.id,
                'vendor_name': vendor.name,
                'source': alias.source,
                'created_at': alias.created_at.isoformat() if alias.created_at else None
            }
            for alias, vendor in aliases
        ]

    def get_unlinked_vendors(self) -> List[Dict]:
        """
        Get vendor names from invoices that are not linked to any Hub vendor.

        Returns:
            List of unlinked vendor names with invoice counts
        """
        result = self.db.execute(text("""
            SELECT vendor_name, COUNT(*) as cnt
            FROM hub_invoices
            WHERE vendor_id IS NULL
            GROUP BY vendor_name
            ORDER BY cnt DESC
        """))

        return [
            {'vendor_name': row[0], 'invoice_count': row[1]}
            for row in result
        ]

    def link_invoices_by_alias(self) -> Dict:
        """
        Link unlinked invoices using the alias table.
        For each unlinked invoice, checks if vendor_name matches an alias.

        Returns:
            Dict with statistics
        """
        # Get unlinked invoices
        unlinked = self.db.query(HubInvoice).filter(
            HubInvoice.vendor_id == None
        ).all()

        stats = {
            'total_unlinked': len(unlinked),
            'linked': 0,
            'still_unlinked': 0,
            'linked_details': []
        }

        for invoice in unlinked:
            result = self.resolve_vendor(invoice.vendor_name)
            if result:
                vendor_id, canonical_name = result
                old_name = invoice.vendor_name
                invoice.vendor_id = vendor_id
                invoice.vendor_name = canonical_name

                stats['linked'] += 1
                stats['linked_details'].append({
                    'invoice_id': invoice.id,
                    'old_name': old_name,
                    'canonical_name': canonical_name,
                    'vendor_id': vendor_id
                })
            else:
                stats['still_unlinked'] += 1

        self.db.commit()

        logger.info(f"Linked {stats['linked']} invoices via alias lookup, "
                   f"{stats['still_unlinked']} still unlinked")

        return stats

    def auto_create_aliases_from_linked(self) -> Dict:
        """
        Auto-create aliases from already-linked invoices.
        For invoices that have vendor_id but vendor_name != canonical name,
        create an alias so future invoices auto-link.

        Returns:
            Dict with created aliases
        """
        # Get linked invoices where name differs from canonical
        result = self.db.execute(text("""
            SELECT DISTINCT i.vendor_name, i.vendor_id, v.name as canonical
            FROM hub_invoices i
            JOIN vendors v ON i.vendor_id = v.id
            WHERE i.vendor_name != v.name
            AND i.vendor_id IS NOT NULL
        """))

        created = []
        skipped = []

        for row in result:
            alias_name = row[0]
            vendor_id = row[1]

            result = self.create_alias(alias_name, vendor_id, source='auto')

            if 'error' in result:
                skipped.append({'alias_name': alias_name, 'reason': result['error']})
            else:
                created.append(result)

        return {
            'created_count': len(created),
            'skipped_count': len(skipped),
            'created': created,
            'skipped': skipped
        }

    def normalize_invoice_vendors(self, dry_run: bool = True) -> Dict:
        """
        Normalize vendor names on all linked invoices to match
        their linked Hub vendor's canonical name.

        Args:
            dry_run: If True, only preview changes without applying

        Returns:
            Dict with statistics and changes made
        """
        # Get invoices where vendor_name differs from canonical
        result = self.db.execute(text("""
            SELECT i.vendor_name, i.vendor_id, v.name as canonical_name, COUNT(*) as cnt
            FROM hub_invoices i
            JOIN vendors v ON i.vendor_id = v.id
            WHERE i.vendor_name != v.name
            GROUP BY i.vendor_name, i.vendor_id, v.name
            ORDER BY v.name, i.vendor_name
        """))

        changes = []
        for row in result:
            changes.append({
                'original': row[0],
                'normalized': row[2],
                'vendor_id': row[1],
                'invoice_count': row[3]
            })

        stats = {
            'dry_run': dry_run,
            'total_changes': len(changes),
            'total_invoices_affected': sum(c['invoice_count'] for c in changes),
            'changes': changes,
            'unlinked': self.get_unlinked_vendors()
        }

        if dry_run:
            return stats

        # Apply changes
        for change in changes:
            self.db.execute(
                text("""
                    UPDATE hub_invoices
                    SET vendor_name = :new_name
                    WHERE vendor_name = :old_name
                    AND vendor_id = :vendor_id
                """),
                {
                    'new_name': change['normalized'],
                    'old_name': change['original'],
                    'vendor_id': change['vendor_id']
                }
            )
            logger.info(f"Normalized '{change['original']}' -> '{change['normalized']}' "
                       f"(vendor_id={change['vendor_id']}, {change['invoice_count']} invoices)")

        self.db.commit()

        return stats

    def get_vendor_summary(self) -> List[Dict]:
        """
        Get summary of all vendors showing linked invoices and aliases.

        Returns:
            List of vendors with invoice counts, aliases, and variants
        """
        # Get vendors with their aliases and invoice counts
        vendors = self.db.query(Vendor).filter(Vendor.is_active == True).all()

        summary = []
        for v in vendors:
            # Get aliases
            aliases = self.db.query(VendorAlias).filter(
                VendorAlias.vendor_id == v.id,
                VendorAlias.is_active == True
            ).all()

            # Get invoice count and variants
            inv_result = self.db.execute(text("""
                SELECT COUNT(*) as cnt, array_agg(DISTINCT vendor_name) as variants
                FROM hub_invoices
                WHERE vendor_id = :vid
            """), {'vid': v.id}).fetchone()

            invoice_count = inv_result[0] or 0
            variants = [name for name in (inv_result[1] or []) if name and name != v.name]

            summary.append({
                'vendor_id': v.id,
                'vendor_name': v.name,
                'inventory_vendor_id': v.inventory_vendor_id,
                'invoice_count': invoice_count,
                'aliases': [a.alias_name for a in aliases],
                'alias_count': len(aliases),
                'variants': variants
            })

        # Add unlinked vendor names
        unlinked = self.get_unlinked_vendors()
        for u in unlinked:
            summary.append({
                'vendor_id': None,
                'vendor_name': u['vendor_name'],
                'inventory_vendor_id': None,
                'invoice_count': u['invoice_count'],
                'aliases': [],
                'alias_count': 0,
                'variants': [],
                'unlinked': True
            })

        return sorted(summary, key=lambda x: -x['invoice_count'])

    def suggest_vendor_links(self) -> List[Dict]:
        """
        Suggest vendor linkings for unlinked invoice vendor names.
        Uses fuzzy matching against existing Hub vendors.

        Returns:
            List of suggestions
        """
        unlinked = self.get_unlinked_vendors()
        vendors = self.db.query(Vendor).filter(Vendor.is_active == True).all()

        suggestions = []
        for u in unlinked:
            unlinked_name = normalize_for_comparison(u['vendor_name'])
            best_match = None
            best_score = 0

            for v in vendors:
                vendor_norm = normalize_for_comparison(v.name)

                # Check contains
                if vendor_norm in unlinked_name or unlinked_name in vendor_norm:
                    score = len(vendor_norm) / max(len(unlinked_name), 1)
                    if score > best_score:
                        best_score = score
                        best_match = v

            if best_match and best_score > 0.3:
                suggestions.append({
                    'unlinked_name': u['vendor_name'],
                    'invoice_count': u['invoice_count'],
                    'suggested_vendor_id': best_match.id,
                    'suggested_vendor_name': best_match.name,
                    'confidence': round(best_score, 2)
                })

        return sorted(suggestions, key=lambda x: -x['invoice_count'])


def get_vendor_normalizer(db: Session) -> VendorNormalizerService:
    """Get vendor normalizer service instance"""
    return VendorNormalizerService(db)
