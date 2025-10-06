"""
Reports API endpoints
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel
from decimal import Decimal

from restaurant_inventory.core.deps import get_db, get_current_user
from restaurant_inventory.models.user import User
from restaurant_inventory.models.count_session import CountSession, CountSessionItem, CountStatus
from restaurant_inventory.models.inventory import Inventory
from restaurant_inventory.models.invoice import Invoice, InvoiceItem
from restaurant_inventory.models.vendor import Vendor
from restaurant_inventory.models.transfer import Transfer
from restaurant_inventory.models.item import MasterItem
from restaurant_inventory.models.location import Location

router = APIRouter()


# Pydantic schemas
class VarianceReportItem(BaseModel):
    item_name: str
    category: Optional[str]
    storage_area_name: Optional[str]
    expected_quantity: float
    actual_quantity: float
    variance: float
    unit: str
    unit_cost: Optional[float]
    expected_value: Optional[float]
    actual_value: Optional[float]
    variance_value: Optional[float]
    count_date: Optional[datetime]
    count_session_id: int
    count_session_name: Optional[str]

    class Config:
        from_attributes = True


@router.get("/variance", response_model=List[VarianceReportItem])
async def get_variance_report(
    location_id: Optional[int] = Query(None),
    storage_area_id: Optional[int] = Query(None),
    begin_session_id: Optional[int] = Query(None),
    end_session_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get variance report comparing two count sessions (beginning vs ending)
    Shows the difference between the two counts for each item
    """
    from sqlalchemy.orm import joinedload

    # If both sessions specified, compare them
    if begin_session_id and end_session_id:
        # Get items from beginning session
        begin_items = db.query(CountSessionItem).join(
            CountSession, CountSessionItem.session_id == CountSession.id
        ).options(
            joinedload(CountSessionItem.master_item),
            joinedload(CountSessionItem.storage_area)
        ).filter(
            CountSession.id == begin_session_id,
            CountSession.status == CountStatus.APPROVED
        )

        if storage_area_id:
            begin_items = begin_items.filter(CountSessionItem.storage_area_id == storage_area_id)

        begin_items = begin_items.all()

        # Get items from ending session
        end_items_query = db.query(CountSessionItem).filter(
            CountSessionItem.session_id == end_session_id
        )

        if storage_area_id:
            end_items_query = end_items_query.filter(CountSessionItem.storage_area_id == storage_area_id)

        end_items = end_items_query.all()

        # Create lookup for ending quantities
        end_lookup = {}
        for item in end_items:
            key = (item.master_item_id, item.storage_area_id)
            end_lookup[key] = float(item.counted_quantity) if item.counted_quantity is not None else 0

        # Get session names
        begin_session = db.query(CountSession).filter(CountSession.id == begin_session_id).first()
        end_session = db.query(CountSession).filter(CountSession.id == end_session_id).first()

        # Build results comparing begin to end
        results = []
        for begin_item in begin_items:
            if begin_item.counted_quantity is not None:
                key = (begin_item.master_item_id, begin_item.storage_area_id)
                expected_qty = float(begin_item.counted_quantity)
                actual_qty = end_lookup.get(key, 0)
                variance = actual_qty - expected_qty

                # Get unit cost from inventory or master item
                inventory = db.query(Inventory).filter(
                    Inventory.master_item_id == begin_item.master_item_id,
                    Inventory.storage_area_id == begin_item.storage_area_id
                ).first()

                unit_cost = None
                if inventory and inventory.unit_cost:
                    unit_cost = float(inventory.unit_cost)
                elif begin_item.master_item and begin_item.master_item.current_cost:
                    unit_cost = float(begin_item.master_item.current_cost)

                # Calculate values
                expected_value = (expected_qty * unit_cost) if unit_cost else None
                actual_value = (actual_qty * unit_cost) if unit_cost else None
                variance_value = (variance * unit_cost) if unit_cost else None

                results.append(VarianceReportItem(
                    item_name=begin_item.master_item.name if begin_item.master_item else "Unknown",
                    category=begin_item.master_item.category if begin_item.master_item else None,
                    storage_area_name=begin_item.storage_area.name if begin_item.storage_area else None,
                    expected_quantity=expected_qty,
                    actual_quantity=actual_qty,
                    variance=variance,
                    unit=begin_item.master_item.unit_of_measure if begin_item.master_item else "",
                    unit_cost=unit_cost,
                    expected_value=expected_value,
                    actual_value=actual_value,
                    variance_value=variance_value,
                    count_date=end_session.approved_at if end_session else None,
                    count_session_id=end_session_id,
                    count_session_name=f"{begin_session.name if begin_session else 'Unknown'} → {end_session.name if end_session else 'Unknown'}"
                ))

        return results
    else:
        # No sessions specified - return empty
        return []


class UsageReportItem(BaseModel):
    item_name: str
    category: Optional[str]
    storage_area_name: Optional[str]
    beginning_quantity: float
    ending_quantity: float
    usage: float
    unit: str
    unit_cost: Optional[float]
    total_usage_cost: Optional[float]

    class Config:
        from_attributes = True


@router.get("/usage", response_model=List[UsageReportItem])
async def get_usage_report(
    location_id: Optional[int] = Query(None),
    storage_area_id: Optional[int] = Query(None),
    begin_session_id: Optional[int] = Query(None),
    end_session_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get usage report showing consumption between two count sessions
    Formula: Beginning Quantity - Ending Quantity = Usage
    """
    from sqlalchemy import func
    from restaurant_inventory.models.storage_area import StorageArea
    from restaurant_inventory.models.item import MasterItem

    # Get the specified sessions or use the first/last approved sessions
    if begin_session_id and end_session_id:
        beginning_session = db.query(CountSession).filter(
            CountSession.id == begin_session_id,
            CountSession.status == CountStatus.APPROVED
        ).first()
        ending_session = db.query(CountSession).filter(
            CountSession.id == end_session_id,
            CountSession.status == CountStatus.APPROVED
        ).first()

        if not beginning_session or not ending_session:
            return []
    else:
        # Find the first (beginning) and last (ending) approved count sessions
        query = db.query(CountSession).filter(
            CountSession.status == CountStatus.APPROVED
        )

        if location_id:
            query = query.filter(CountSession.location_id == location_id)

        sessions = query.order_by(CountSession.approved_at).all()

        if len(sessions) < 2:
            return []  # Need at least 2 count sessions to calculate usage

        beginning_session = sessions[0]
        ending_session = sessions[-1]

    # Get items from both sessions
    beginning_items_query = db.query(CountSessionItem).filter(
        CountSessionItem.session_id == beginning_session.id
    )
    ending_items_query = db.query(CountSessionItem).filter(
        CountSessionItem.session_id == ending_session.id
    )

    if storage_area_id:
        beginning_items_query = beginning_items_query.filter(CountSessionItem.storage_area_id == storage_area_id)
        ending_items_query = ending_items_query.filter(CountSessionItem.storage_area_id == storage_area_id)

    beginning_items = beginning_items_query.all()
    ending_items = ending_items_query.all()

    # Create lookup for ending quantities
    ending_lookup = {}
    for item in ending_items:
        key = (item.master_item_id, item.storage_area_id)
        ending_lookup[key] = float(item.counted_quantity) if item.counted_quantity is not None else 0

    # Calculate usage
    results = []
    for begin_item in beginning_items:
        if begin_item.counted_quantity is not None:
            key = (begin_item.master_item_id, begin_item.storage_area_id)
            beginning_qty = float(begin_item.counted_quantity)
            ending_qty = ending_lookup.get(key, 0)
            usage = beginning_qty - ending_qty

            # Get unit cost from inventory
            inventory = db.query(Inventory).filter(
                Inventory.master_item_id == begin_item.master_item_id,
                Inventory.storage_area_id == begin_item.storage_area_id
            ).first()

            unit_cost = float(inventory.unit_cost) if inventory and inventory.unit_cost else None
            total_cost = (usage * unit_cost) if unit_cost else None

            results.append(UsageReportItem(
                item_name=begin_item.master_item.name if begin_item.master_item else "Unknown",
                category=begin_item.master_item.category if begin_item.master_item else None,
                storage_area_name=begin_item.storage_area.name if begin_item.storage_area else None,
                beginning_quantity=beginning_qty,
                ending_quantity=ending_qty,
                usage=usage,
                unit=begin_item.master_item.unit_of_measure if begin_item.master_item else "",
                unit_cost=unit_cost,
                total_usage_cost=total_cost
            ))

    return results


class CostReportItem(BaseModel):
    storage_area_name: str
    total_items: int
    total_quantity: float
    total_value: float

    class Config:
        from_attributes = True


@router.get("/cost", response_model=List[CostReportItem])
async def get_cost_report(
    location_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get cost report showing inventory value by storage area
    """
    from sqlalchemy import func
    from restaurant_inventory.models.storage_area import StorageArea

    # Build query
    query = db.query(
        StorageArea.name.label('storage_area_name'),
        func.count(Inventory.id).label('total_items'),
        func.sum(Inventory.current_quantity).label('total_quantity'),
        func.sum(Inventory.total_value).label('total_value')
    ).join(
        Inventory, StorageArea.id == Inventory.storage_area_id
    ).group_by(StorageArea.id, StorageArea.name)

    if location_id:
        query = query.filter(StorageArea.location_id == location_id)

    results = query.all()

    return [
        CostReportItem(
            storage_area_name=r.storage_area_name,
            total_items=r.total_items or 0,
            total_quantity=float(r.total_quantity or 0),
            total_value=float(r.total_value or 0)
        )
        for r in results
    ]


class CostVarianceItem(BaseModel):
    """Track cost changes for items over time"""
    item_id: int
    item_name: str
    category: Optional[str]
    vendor_name: Optional[str]
    unit: str
    earliest_cost: float
    earliest_date: datetime
    latest_cost: float
    latest_date: datetime
    cost_change: float
    percent_change: float
    invoice_count: int

    class Config:
        from_attributes = True


@router.get("/cost-variance", response_model=List[CostVarianceItem])
async def get_cost_variance_report(
    start_date: Optional[date] = Query(None, description="Start date for analysis"),
    end_date: Optional[date] = Query(None, description="End date for analysis"),
    vendor_id: Optional[int] = Query(None, description="Filter by vendor"),
    category: Optional[str] = Query(None, description="Filter by category"),
    min_percent_change: Optional[float] = Query(None, description="Minimum % change to show"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cost Variance Tracker - Identifies changes in product costs over time
    Helps inform when to adjust menu prices
    """

    # Build subquery to get earliest and latest invoice items for each master item
    from sqlalchemy import case

    # Get all invoice items with their dates
    query = db.query(
        InvoiceItem.master_item_id,
        MasterItem.name.label('item_name'),
        MasterItem.category,
        Vendor.name.label('vendor_name'),
        MasterItem.unit_of_measure.label('unit'),
        func.min(InvoiceItem.unit_price).label('min_cost'),
        func.max(InvoiceItem.unit_price).label('max_cost'),
        func.count(InvoiceItem.id).label('invoice_count')
    ).join(
        Invoice, InvoiceItem.invoice_id == Invoice.id
    ).join(
        MasterItem, InvoiceItem.master_item_id == MasterItem.id
    ).outerjoin(
        Vendor, Invoice.vendor_id == Vendor.id
    )

    # Apply filters
    if start_date:
        query = query.filter(Invoice.invoice_date >= start_date)
    if end_date:
        query = query.filter(Invoice.invoice_date <= end_date)
    if vendor_id:
        query = query.filter(Invoice.vendor_id == vendor_id)
    if category:
        query = query.filter(MasterItem.category == category)

    query = query.group_by(
        InvoiceItem.master_item_id,
        MasterItem.name,
        MasterItem.category,
        Vendor.name,
        MasterItem.unit_of_measure
    )

    results = query.all()

    # Now get earliest and latest dates for each item
    variance_items = []
    for r in results:
        # Get earliest invoice item for this master item
        earliest = db.query(
            InvoiceItem.unit_price,
            Invoice.invoice_date
        ).join(
            Invoice, InvoiceItem.invoice_id == Invoice.id
        ).filter(
            InvoiceItem.master_item_id == r.master_item_id
        )

        if start_date:
            earliest = earliest.filter(Invoice.invoice_date >= start_date)
        if end_date:
            earliest = earliest.filter(Invoice.invoice_date <= end_date)
        if vendor_id:
            earliest = earliest.filter(Invoice.vendor_id == vendor_id)

        earliest = earliest.order_by(Invoice.invoice_date.asc()).first()

        # Get latest invoice item for this master item
        latest = db.query(
            InvoiceItem.unit_price,
            Invoice.invoice_date
        ).join(
            Invoice, InvoiceItem.invoice_id == Invoice.id
        ).filter(
            InvoiceItem.master_item_id == r.master_item_id
        )

        if start_date:
            latest = latest.filter(Invoice.invoice_date >= start_date)
        if end_date:
            latest = latest.filter(Invoice.invoice_date <= end_date)
        if vendor_id:
            latest = latest.filter(Invoice.vendor_id == vendor_id)

        latest = latest.order_by(Invoice.invoice_date.desc()).first()

        if earliest and latest:
            earliest_cost = float(earliest.unit_price)
            latest_cost = float(latest.unit_price)
            cost_change = latest_cost - earliest_cost
            percent_change = ((cost_change / earliest_cost) * 100) if earliest_cost != 0 else 0

            # Apply min percent change filter
            if min_percent_change is not None and abs(percent_change) < abs(min_percent_change):
                continue

            variance_items.append(CostVarianceItem(
                item_id=r.master_item_id,
                item_name=r.item_name,
                category=r.category,
                vendor_name=r.vendor_name,
                unit=r.unit or '',
                earliest_cost=earliest_cost,
                earliest_date=earliest.invoice_date,
                latest_cost=latest_cost,
                latest_date=latest.invoice_date,
                cost_change=cost_change,
                percent_change=round(percent_change, 2),
                invoice_count=r.invoice_count
            ))

    # Sort by percent change (largest changes first)
    variance_items.sort(key=lambda x: abs(x.percent_change), reverse=True)

    return variance_items


class VendorSpendItem(BaseModel):
    """Vendor spending summary"""
    vendor_id: Optional[int]
    vendor_name: str
    invoice_count: int
    total_spent: float
    avg_invoice_amount: float
    earliest_invoice: Optional[datetime]
    latest_invoice: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/vendor-spend", response_model=List[VendorSpendItem])
async def get_vendor_spend_report(
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Spend by Vendor Report - Shows amount spent by vendor within date range
    """

    query = db.query(
        Vendor.id.label('vendor_id'),
        Vendor.name.label('vendor_name'),
        func.count(Invoice.id).label('invoice_count'),
        func.sum(Invoice.total).label('total_spent'),
        func.avg(Invoice.total).label('avg_invoice_amount'),
        func.min(Invoice.invoice_date).label('earliest_invoice'),
        func.max(Invoice.invoice_date).label('latest_invoice')
    ).outerjoin(
        Invoice, Vendor.id == Invoice.vendor_id
    )

    # Apply date filters
    if start_date:
        query = query.filter(Invoice.invoice_date >= start_date)
    if end_date:
        query = query.filter(Invoice.invoice_date <= end_date)

    query = query.group_by(Vendor.id, Vendor.name).order_by(desc('total_spent'))

    results = query.all()

    return [
        VendorSpendItem(
            vendor_id=r.vendor_id,
            vendor_name=r.vendor_name,
            invoice_count=r.invoice_count or 0,
            total_spent=float(r.total_spent or 0),
            avg_invoice_amount=float(r.avg_invoice_amount or 0),
            earliest_invoice=r.earliest_invoice,
            latest_invoice=r.latest_invoice
        )
        for r in results
        if r.total_spent and r.total_spent > 0  # Only show vendors with actual spending
    ]


class TransferHistoryItem(BaseModel):
    """Transfer history record"""
    transfer_id: int
    transfer_date: datetime
    from_location_name: str
    to_location_name: str
    item_name: str
    category: Optional[str]
    quantity: float
    unit: str
    unit_cost: Optional[float]
    total_value: Optional[float]
    notes: Optional[str]
    created_by_name: Optional[str]

    class Config:
        from_attributes = True


@router.get("/transfers", response_model=List[TransferHistoryItem])
async def get_transfers_report(
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    from_location_id: Optional[int] = Query(None, description="Filter by source location"),
    to_location_id: Optional[int] = Query(None, description="Filter by destination location"),
    item_id: Optional[int] = Query(None, description="Filter by item"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Transfer History Report - Shows inventory transfers between locations
    """
    from restaurant_inventory.models.user import User as UserModel

    query = db.query(
        Transfer.id.label('transfer_id'),
        Transfer.transfer_date,
        Location.name.label('from_location_name'),
        func.coalesce(Location.name, 'Unknown').label('to_location_name'),
        MasterItem.name.label('item_name'),
        MasterItem.category,
        Transfer.quantity,
        MasterItem.unit_of_measure.label('unit'),
        Transfer.unit_cost,
        Transfer.total_value,
        Transfer.notes,
        UserModel.username.label('created_by_name')
    ).join(
        Location, Transfer.from_location_id == Location.id
    ).outerjoin(
        MasterItem, Transfer.master_item_id == MasterItem.id
    ).outerjoin(
        UserModel, Transfer.created_by_id == UserModel.id
    )

    # Apply filters
    if start_date:
        query = query.filter(Transfer.transfer_date >= start_date)
    if end_date:
        query = query.filter(Transfer.transfer_date <= end_date)
    if from_location_id:
        query = query.filter(Transfer.from_location_id == from_location_id)
    if to_location_id:
        query = query.filter(Transfer.to_location_id == to_location_id)
    if item_id:
        query = query.filter(Transfer.master_item_id == item_id)

    query = query.order_by(Transfer.transfer_date.desc())

    results = query.all()

    # Get to_location names separately (since it's a separate query)
    transfer_items = []
    for r in results:
        # Get the to_location name
        to_location = db.query(Location).filter(Location.id == Transfer.to_location_id).first() if hasattr(Transfer, 'to_location_id') else None
        to_location_name = to_location.name if to_location else 'Unknown'

        transfer_items.append(TransferHistoryItem(
            transfer_id=r.transfer_id,
            transfer_date=r.transfer_date,
            from_location_name=r.from_location_name,
            to_location_name=to_location_name,
            item_name=r.item_name or 'Unknown',
            category=r.category,
            quantity=float(r.quantity),
            unit=r.unit or '',
            unit_cost=float(r.unit_cost) if r.unit_cost else None,
            total_value=float(r.total_value) if r.total_value else None,
            notes=r.notes,
            created_by_name=r.created_by_name
        ))

    return transfer_items
