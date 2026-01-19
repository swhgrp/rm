"""
Reporting Service

Provides analytics and reporting for Hub data:
- Invoice statistics
- Vendor spend analysis
- Mapping success rates
- Price change trends
- Sync status overview
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, cast, Float, Integer, case

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.models.price_history import PriceHistory

logger = logging.getLogger(__name__)


class ReportingService:
    """Service for generating reports and analytics"""

    def __init__(self, db: Session):
        self.db = db

    def get_dashboard_summary(self, days: int = 30) -> Dict:
        """
        Get summary dashboard data.

        Args:
            days: Number of days to look back for trend data

        Returns:
            Dict with dashboard metrics
        """
        cutoff_date = date.today() - timedelta(days=days)

        # Total invoices
        total_invoices = self.db.query(func.count(HubInvoice.id)).scalar() or 0

        # Recent invoices (last N days)
        recent_invoices = self.db.query(func.count(HubInvoice.id)).filter(
            HubInvoice.invoice_date >= cutoff_date
        ).scalar() or 0

        # Total spend
        total_spend = self.db.query(func.sum(HubInvoice.total_amount)).scalar() or 0

        # Recent spend
        recent_spend = self.db.query(func.sum(HubInvoice.total_amount)).filter(
            HubInvoice.invoice_date >= cutoff_date
        ).scalar() or 0

        # Invoice status breakdown
        status_counts = self.db.query(
            HubInvoice.status,
            func.count(HubInvoice.id)
        ).group_by(HubInvoice.status).all()

        by_status = {status: count for status, count in status_counts}

        # Sync status
        sent_to_inventory = self.db.query(func.count(HubInvoice.id)).filter(
            HubInvoice.sent_to_inventory == True
        ).scalar() or 0

        sent_to_accounting = self.db.query(func.count(HubInvoice.id)).filter(
            HubInvoice.sent_to_accounting == True
        ).scalar() or 0

        # Mapping rates
        total_items = self.db.query(func.count(HubInvoiceItem.id)).scalar() or 0
        mapped_items = self.db.query(func.count(HubInvoiceItem.id)).filter(
            HubInvoiceItem.is_mapped == True
        ).scalar() or 0

        mapping_rate = (mapped_items / total_items * 100) if total_items > 0 else 0

        # Vendor items
        total_vendor_items = self.db.query(func.count(HubVendorItem.id)).filter(
            HubVendorItem.is_active == True
        ).scalar() or 0

        # Price changes in period
        price_changes = self.db.query(func.count(PriceHistory.id)).filter(
            PriceHistory.recorded_at >= cutoff_date
        ).scalar() or 0

        significant_price_changes = self.db.query(func.count(PriceHistory.id)).filter(
            and_(
                PriceHistory.recorded_at >= cutoff_date,
                func.abs(PriceHistory.price_change_pct) >= 5.0
            )
        ).scalar() or 0

        return {
            'period_days': days,
            'invoices': {
                'total': total_invoices,
                'recent': recent_invoices,
                'by_status': by_status
            },
            'spend': {
                'total': float(total_spend),
                'recent': float(recent_spend)
            },
            'sync': {
                'sent_to_inventory': sent_to_inventory,
                'sent_to_accounting': sent_to_accounting,
                'pending': total_invoices - sent_to_inventory
            },
            'mapping': {
                'total_items': total_items,
                'mapped_items': mapped_items,
                'mapping_rate': round(mapping_rate, 1)
            },
            'vendor_items': {
                'total_active': total_vendor_items
            },
            'price_tracking': {
                'changes_in_period': price_changes,
                'significant_changes': significant_price_changes
            }
        }

    def get_vendor_spend_report(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 20
    ) -> Dict:
        """
        Get vendor spend breakdown.

        Args:
            start_date: Start of period (defaults to 30 days ago)
            end_date: End of period (defaults to today)
            limit: Number of vendors to return

        Returns:
            Dict with vendor spend data
        """
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        # Query spend by vendor
        vendor_spend = self.db.query(
            HubInvoice.vendor_name,
            func.count(HubInvoice.id).label('invoice_count'),
            func.sum(HubInvoice.total_amount).label('total_spend'),
            func.avg(HubInvoice.total_amount).label('avg_invoice')
        ).filter(
            and_(
                HubInvoice.invoice_date >= start_date,
                HubInvoice.invoice_date <= end_date,
                or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None)
            )
        ).group_by(
            HubInvoice.vendor_name
        ).order_by(
            func.sum(HubInvoice.total_amount).desc()
        ).limit(limit).all()

        total_spend = sum(float(v.total_spend or 0) for v in vendor_spend)

        vendors = []
        for v in vendor_spend:
            spend = float(v.total_spend or 0)
            pct = (spend / total_spend * 100) if total_spend > 0 else 0
            vendors.append({
                'vendor_name': v.vendor_name,
                'invoice_count': v.invoice_count,
                'total_spend': spend,
                'avg_invoice': float(v.avg_invoice or 0),
                'percentage': round(pct, 1)
            })

        return {
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'total_spend': float(total_spend),
            'vendor_count': len(vendors),
            'vendors': vendors
        }

    def get_daily_invoice_trend(self, days: int = 30) -> Dict:
        """
        Get daily invoice counts and amounts.

        Args:
            days: Number of days to include

        Returns:
            Dict with daily trend data
        """
        cutoff_date = date.today() - timedelta(days=days)

        daily_data = self.db.query(
            HubInvoice.invoice_date,
            func.count(HubInvoice.id).label('count'),
            func.sum(HubInvoice.total_amount).label('amount')
        ).filter(
            and_(
                HubInvoice.invoice_date >= cutoff_date,
                or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None)
            )
        ).group_by(
            HubInvoice.invoice_date
        ).order_by(
            HubInvoice.invoice_date
        ).all()

        trend = []
        for row in daily_data:
            trend.append({
                'date': row.invoice_date.isoformat() if row.invoice_date else None,
                'count': row.count,
                'amount': float(row.amount or 0)
            })

        return {
            'period_days': days,
            'daily_data': trend,
            'total_days': len(trend),
            'avg_daily_count': sum(d['count'] for d in trend) / len(trend) if trend else 0,
            'avg_daily_amount': sum(d['amount'] for d in trend) / len(trend) if trend else 0
        }

    def get_mapping_report(self) -> Dict:
        """
        Get detailed mapping statistics.

        Returns:
            Dict with mapping breakdown
        """
        # Overall counts
        total_items = self.db.query(func.count(HubInvoiceItem.id)).scalar() or 0
        mapped_items = self.db.query(func.count(HubInvoiceItem.id)).filter(
            HubInvoiceItem.is_mapped == True
        ).scalar() or 0
        unmapped_items = total_items - mapped_items

        # By mapping method
        method_counts = self.db.query(
            HubInvoiceItem.mapping_method,
            func.count(HubInvoiceItem.id)
        ).filter(
            HubInvoiceItem.is_mapped == True
        ).group_by(
            HubInvoiceItem.mapping_method
        ).all()

        by_method = {method or 'unknown': count for method, count in method_counts}

        # Unmapped by vendor
        unmapped_by_vendor = self.db.query(
            HubInvoice.vendor_name,
            func.count(HubInvoiceItem.id).label('count')
        ).join(
            HubInvoiceItem
        ).filter(
            or_(HubInvoiceItem.is_mapped == False, HubInvoiceItem.is_mapped == None)
        ).group_by(
            HubInvoice.vendor_name
        ).order_by(
            func.count(HubInvoiceItem.id).desc()
        ).limit(10).all()

        # Mapping rate by vendor
        vendor_mapping = self.db.query(
            HubInvoice.vendor_name,
            func.count(HubInvoiceItem.id).label('total'),
            func.sum(case((HubInvoiceItem.is_mapped == True, 1), else_=0)).label('mapped')
        ).join(
            HubInvoiceItem
        ).group_by(
            HubInvoice.vendor_name
        ).having(
            func.count(HubInvoiceItem.id) >= 10  # Only vendors with 10+ items
        ).all()

        vendor_rates = []
        for v in vendor_mapping:
            rate = (v.mapped / v.total * 100) if v.total > 0 else 0
            vendor_rates.append({
                'vendor_name': v.vendor_name,
                'total_items': v.total,
                'mapped_items': v.mapped,
                'mapping_rate': round(rate, 1)
            })

        # Sort by mapping rate
        vendor_rates.sort(key=lambda x: x['mapping_rate'], reverse=True)

        return {
            'overall': {
                'total_items': total_items,
                'mapped_items': mapped_items,
                'unmapped_items': unmapped_items,
                'mapping_rate': round((mapped_items / total_items * 100) if total_items > 0 else 0, 1)
            },
            'by_method': by_method,
            'unmapped_by_vendor': [
                {'vendor_name': v.vendor_name, 'count': v.count}
                for v in unmapped_by_vendor
            ],
            'vendor_mapping_rates': vendor_rates[:10]  # Top 10
        }

    def get_price_change_report(self, days: int = 30, min_change_pct: float = 5.0) -> Dict:
        """
        Get price change analysis.

        Args:
            days: Number of days to look back
            min_change_pct: Minimum percentage change to consider significant

        Returns:
            Dict with price change analysis
        """
        cutoff_date = get_now() - timedelta(days=days)

        # All price changes in period
        total_changes = self.db.query(func.count(PriceHistory.id)).filter(
            PriceHistory.recorded_at >= cutoff_date
        ).scalar() or 0

        # Significant changes
        significant = self.db.query(func.count(PriceHistory.id)).filter(
            and_(
                PriceHistory.recorded_at >= cutoff_date,
                func.abs(PriceHistory.price_change_pct) >= min_change_pct
            )
        ).scalar() or 0

        # Price increases vs decreases
        increases = self.db.query(func.count(PriceHistory.id)).filter(
            and_(
                PriceHistory.recorded_at >= cutoff_date,
                PriceHistory.price_change > 0
            )
        ).scalar() or 0

        decreases = self.db.query(func.count(PriceHistory.id)).filter(
            and_(
                PriceHistory.recorded_at >= cutoff_date,
                PriceHistory.price_change < 0
            )
        ).scalar() or 0

        # Average change percentage
        avg_change = self.db.query(
            func.avg(PriceHistory.price_change_pct)
        ).filter(
            PriceHistory.recorded_at >= cutoff_date
        ).scalar() or 0

        # Top price increases
        top_increases = self.db.query(
            PriceHistory,
            HubVendorItem.vendor_product_name
        ).join(
            HubVendorItem
        ).filter(
            and_(
                PriceHistory.recorded_at >= cutoff_date,
                PriceHistory.price_change_pct >= min_change_pct
            )
        ).order_by(
            PriceHistory.price_change_pct.desc()
        ).limit(10).all()

        top_increases_list = []
        for ph, product_name in top_increases:
            top_increases_list.append({
                'product_name': product_name,
                'old_price': float(ph.old_price) if ph.old_price else None,
                'new_price': float(ph.new_price),
                'change_pct': float(ph.price_change_pct) if ph.price_change_pct else 0,
                'invoice_number': ph.invoice_number,
                'recorded_at': ph.recorded_at.isoformat() if ph.recorded_at else None
            })

        # Items with most price volatility
        volatile_items = self.db.query(
            HubVendorItem.vendor_product_name,
            func.count(PriceHistory.id).label('change_count'),
            func.avg(func.abs(PriceHistory.price_change_pct)).label('avg_volatility')
        ).join(
            PriceHistory
        ).filter(
            PriceHistory.recorded_at >= cutoff_date
        ).group_by(
            HubVendorItem.id, HubVendorItem.vendor_product_name
        ).having(
            func.count(PriceHistory.id) >= 2
        ).order_by(
            func.avg(func.abs(PriceHistory.price_change_pct)).desc()
        ).limit(10).all()

        volatile_list = []
        for v in volatile_items:
            volatile_list.append({
                'product_name': v.vendor_product_name,
                'change_count': v.change_count,
                'avg_volatility': round(float(v.avg_volatility or 0), 1)
            })

        return {
            'period_days': days,
            'min_change_pct': min_change_pct,
            'summary': {
                'total_changes': total_changes,
                'significant_changes': significant,
                'increases': increases,
                'decreases': decreases,
                'unchanged': total_changes - increases - decreases,
                'avg_change_pct': round(float(avg_change), 2)
            },
            'top_increases': top_increases_list,
            'volatile_items': volatile_list
        }

    def get_sync_status_report(self) -> Dict:
        """
        Get detailed sync status breakdown.

        Returns:
            Dict with sync status data
        """
        total = self.db.query(func.count(HubInvoice.id)).filter(
            or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None)
        ).scalar() or 0

        # Sync combinations
        both_sent = self.db.query(func.count(HubInvoice.id)).filter(
            and_(
                HubInvoice.sent_to_inventory == True,
                HubInvoice.sent_to_accounting == True,
                or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None)
            )
        ).scalar() or 0

        inventory_only = self.db.query(func.count(HubInvoice.id)).filter(
            and_(
                HubInvoice.sent_to_inventory == True,
                or_(HubInvoice.sent_to_accounting == False, HubInvoice.sent_to_accounting == None),
                or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None)
            )
        ).scalar() or 0

        accounting_only = self.db.query(func.count(HubInvoice.id)).filter(
            and_(
                or_(HubInvoice.sent_to_inventory == False, HubInvoice.sent_to_inventory == None),
                HubInvoice.sent_to_accounting == True,
                or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None)
            )
        ).scalar() or 0

        neither = total - both_sent - inventory_only - accounting_only

        # With errors
        with_inventory_error = self.db.query(func.count(HubInvoice.id)).filter(
            and_(
                HubInvoice.inventory_error != None,
                or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None)
            )
        ).scalar() or 0

        with_accounting_error = self.db.query(func.count(HubInvoice.id)).filter(
            and_(
                HubInvoice.accounting_error != None,
                or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None)
            )
        ).scalar() or 0

        # Statements
        statements = self.db.query(func.count(HubInvoice.id)).filter(
            HubInvoice.is_statement == True
        ).scalar() or 0

        return {
            'total_invoices': total,
            'statements': statements,
            'sync_status': {
                'both_sent': both_sent,
                'inventory_only': inventory_only,
                'accounting_only': accounting_only,
                'neither': neither
            },
            'errors': {
                'inventory_errors': with_inventory_error,
                'accounting_errors': with_accounting_error
            },
            'percentages': {
                'fully_synced': round((both_sent / total * 100) if total > 0 else 0, 1),
                'pending': round((neither / total * 100) if total > 0 else 0, 1)
            }
        }

    def get_vendor_spend_by_location(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        vendor_name: Optional[str] = None,
        location_id: Optional[int] = None,
        limit: int = 50
    ) -> Dict:
        """
        Get vendor spend breakdown by location.

        Args:
            start_date: Start of period (defaults to 30 days ago)
            end_date: End of period (defaults to today)
            vendor_name: Filter by specific vendor
            location_id: Filter by specific location
            limit: Max results to return

        Returns:
            Dict with vendor-location spend data
        """
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        # Base query conditions
        conditions = [
            HubInvoice.invoice_date >= start_date,
            HubInvoice.invoice_date <= end_date,
            or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None),
            HubInvoice.location_id != None  # Only invoices with assigned location
        ]

        if vendor_name:
            conditions.append(HubInvoice.vendor_name.ilike(f"%{vendor_name}%"))
        if location_id:
            conditions.append(HubInvoice.location_id == location_id)

        # Query spend by vendor and location
        vendor_location_spend = self.db.query(
            HubInvoice.vendor_name,
            HubInvoice.location_id,
            HubInvoice.location_name,
            func.count(HubInvoice.id).label('invoice_count'),
            func.sum(HubInvoice.total_amount).label('total_spend'),
            func.avg(HubInvoice.total_amount).label('avg_invoice'),
            func.min(HubInvoice.invoice_date).label('first_invoice'),
            func.max(HubInvoice.invoice_date).label('last_invoice')
        ).filter(
            and_(*conditions)
        ).group_by(
            HubInvoice.vendor_name,
            HubInvoice.location_id,
            HubInvoice.location_name
        ).order_by(
            func.sum(HubInvoice.total_amount).desc()
        ).limit(limit).all()

        # Calculate totals
        total_spend = sum(float(v.total_spend or 0) for v in vendor_location_spend)

        results = []
        for v in vendor_location_spend:
            spend = float(v.total_spend or 0)
            pct = (spend / total_spend * 100) if total_spend > 0 else 0
            results.append({
                'vendor_name': v.vendor_name,
                'location_id': v.location_id,
                'location_name': v.location_name or f"Location {v.location_id}",
                'invoice_count': v.invoice_count,
                'total_spend': spend,
                'avg_invoice': round(float(v.avg_invoice or 0), 2),
                'percentage': round(pct, 1),
                'first_invoice': v.first_invoice.isoformat() if v.first_invoice else None,
                'last_invoice': v.last_invoice.isoformat() if v.last_invoice else None
            })

        # Group by vendor for cross-location comparison
        vendor_totals = {}
        for r in results:
            vn = r['vendor_name']
            if vn not in vendor_totals:
                vendor_totals[vn] = {
                    'total_spend': 0,
                    'locations': [],
                    'location_count': 0
                }
            vendor_totals[vn]['total_spend'] += r['total_spend']
            vendor_totals[vn]['locations'].append({
                'location_id': r['location_id'],
                'location_name': r['location_name'],
                'spend': r['total_spend']
            })
            vendor_totals[vn]['location_count'] += 1

        return {
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'filters': {
                'vendor_name': vendor_name,
                'location_id': location_id
            },
            'total_spend': total_spend,
            'result_count': len(results),
            'data': results,
            'vendor_summary': [
                {
                    'vendor_name': k,
                    'total_spend': v['total_spend'],
                    'location_count': v['location_count'],
                    'locations': v['locations']
                }
                for k, v in sorted(vendor_totals.items(), key=lambda x: -x[1]['total_spend'])
            ]
        }

    def get_location_spend_summary(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict:
        """
        Get overall spend summary per location.

        Args:
            start_date: Start of period (defaults to 30 days ago)
            end_date: End of period (defaults to today)

        Returns:
            Dict with location spend summaries
        """
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        # Query spend by location
        location_spend = self.db.query(
            HubInvoice.location_id,
            HubInvoice.location_name,
            func.count(HubInvoice.id).label('invoice_count'),
            func.sum(HubInvoice.total_amount).label('total_spend'),
            func.avg(HubInvoice.total_amount).label('avg_invoice'),
            func.count(func.distinct(HubInvoice.vendor_name)).label('vendor_count')
        ).filter(
            and_(
                HubInvoice.invoice_date >= start_date,
                HubInvoice.invoice_date <= end_date,
                or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None),
                HubInvoice.location_id != None
            )
        ).group_by(
            HubInvoice.location_id,
            HubInvoice.location_name
        ).order_by(
            func.sum(HubInvoice.total_amount).desc()
        ).all()

        total_spend = sum(float(l.total_spend or 0) for l in location_spend)

        locations = []
        for l in location_spend:
            spend = float(l.total_spend or 0)
            pct = (spend / total_spend * 100) if total_spend > 0 else 0
            locations.append({
                'location_id': l.location_id,
                'location_name': l.location_name or f"Location {l.location_id}",
                'invoice_count': l.invoice_count,
                'total_spend': spend,
                'avg_invoice': round(float(l.avg_invoice or 0), 2),
                'vendor_count': l.vendor_count,
                'percentage': round(pct, 1)
            })

        return {
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'total_spend': total_spend,
            'location_count': len(locations),
            'locations': locations
        }

    def get_vendor_location_matrix(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        top_vendors: int = 10
    ) -> Dict:
        """
        Get vendor-location spend matrix.

        Args:
            start_date: Start of period (defaults to 30 days ago)
            end_date: End of period (defaults to today)
            top_vendors: Number of top vendors to include

        Returns:
            Dict with matrix data for visualization
        """
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        # Get top vendors by total spend
        top_vendor_names = self.db.query(
            HubInvoice.vendor_name,
            func.sum(HubInvoice.total_amount).label('total')
        ).filter(
            and_(
                HubInvoice.invoice_date >= start_date,
                HubInvoice.invoice_date <= end_date,
                or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None)
            )
        ).group_by(
            HubInvoice.vendor_name
        ).order_by(
            func.sum(HubInvoice.total_amount).desc()
        ).limit(top_vendors).all()

        vendor_names = [v.vendor_name for v in top_vendor_names]

        # Get all locations with invoices
        locations = self.db.query(
            HubInvoice.location_id,
            HubInvoice.location_name
        ).filter(
            and_(
                HubInvoice.invoice_date >= start_date,
                HubInvoice.invoice_date <= end_date,
                or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None),
                HubInvoice.location_id != None
            )
        ).distinct().all()

        location_map = {l.location_id: l.location_name or f"Location {l.location_id}" for l in locations}

        # Get spend matrix data
        matrix_data = self.db.query(
            HubInvoice.vendor_name,
            HubInvoice.location_id,
            func.sum(HubInvoice.total_amount).label('spend')
        ).filter(
            and_(
                HubInvoice.invoice_date >= start_date,
                HubInvoice.invoice_date <= end_date,
                or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None),
                HubInvoice.vendor_name.in_(vendor_names),
                HubInvoice.location_id != None
            )
        ).group_by(
            HubInvoice.vendor_name,
            HubInvoice.location_id
        ).all()

        # Build matrix
        matrix = {}
        for row in matrix_data:
            if row.vendor_name not in matrix:
                matrix[row.vendor_name] = {}
            matrix[row.vendor_name][row.location_id] = float(row.spend or 0)

        # Format for output
        rows = []
        for vendor_name in vendor_names:
            row = {
                'vendor_name': vendor_name,
                'locations': {}
            }
            vendor_total = 0
            for loc_id in location_map.keys():
                spend = matrix.get(vendor_name, {}).get(loc_id, 0)
                row['locations'][loc_id] = spend
                vendor_total += spend
            row['total'] = vendor_total
            rows.append(row)

        # Calculate location totals
        location_totals = {}
        for loc_id in location_map.keys():
            location_totals[loc_id] = sum(
                matrix.get(vn, {}).get(loc_id, 0) for vn in vendor_names
            )

        return {
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'locations': [
                {'id': loc_id, 'name': loc_name}
                for loc_id, loc_name in location_map.items()
            ],
            'vendors': vendor_names,
            'matrix': rows,
            'location_totals': location_totals,
            'grand_total': sum(location_totals.values())
        }


def get_reporting_service(db: Session) -> ReportingService:
    """Get reporting service instance"""
    return ReportingService(db)
