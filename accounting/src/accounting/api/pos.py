"""
POS Integration API Endpoints
Handles POS configuration, syncing, and category mappings
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.pos import POSConfiguration, POSDailySalesCache, POSCategoryGLMapping
from accounting.schemas.pos import (
    POSConfigurationCreate,
    POSConfigurationUpdate,
    POSConfigurationResponse,
    POSDailySalesCacheResponse,
    POSCategoryGLMappingCreate,
    POSCategoryGLMappingUpdate,
    POSCategoryGLMappingResponse,
    POSDiscountGLMappingCreate,
    POSDiscountGLMappingUpdate,
    POSDiscountGLMappingResponse,
    POSPaymentGLMappingCreate,
    POSPaymentGLMappingUpdate,
    POSPaymentGLMappingResponse,
    POSSyncRequest,
    POSSyncResponse,
    POSConnectionTestResponse
)
from accounting.services.pos_sync_service import POSSyncService
from accounting.core.clover_client import CloverAPIClient
from accounting.api.auth import require_auth

router = APIRouter(prefix="/api/pos", tags=["POS Integration"])


# ==================== POS Configuration Endpoints ====================

@router.get("/configurations", response_model=List[POSConfigurationResponse])
def list_pos_configurations(
    area_id: Optional[int] = Query(None, description="Filter by area/location ID"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """List all POS configurations"""
    query = db.query(POSConfiguration)

    if area_id:
        query = query.filter(POSConfiguration.area_id == area_id)

    return query.all()


@router.get("/configurations/{area_id}", response_model=POSConfigurationResponse)
def get_pos_configuration(
    area_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Get POS configuration for a specific location"""
    config = db.query(POSConfiguration).filter(
        POSConfiguration.area_id == area_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    return config


@router.post("/configurations", response_model=POSConfigurationResponse)
def create_pos_configuration(
    config_data: POSConfigurationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Create POS configuration for a location"""
    # Check if configuration already exists
    existing = db.query(POSConfiguration).filter(
        POSConfiguration.area_id == config_data.area_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"POS configuration already exists for area {config_data.area_id}"
        )

    # Create new configuration
    config = POSConfiguration(**config_data.dict())
    db.add(config)
    db.commit()
    db.refresh(config)

    return config


@router.put("/configurations/{area_id}", response_model=POSConfigurationResponse)
def update_pos_configuration(
    area_id: int,
    config_data: POSConfigurationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update POS configuration"""
    config = db.query(POSConfiguration).filter(
        POSConfiguration.area_id == area_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    # Update fields
    for field, value in config_data.dict(exclude_unset=True).items():
        setattr(config, field, value)

    db.commit()
    db.refresh(config)

    return config


@router.delete("/configurations/{area_id}")
def delete_pos_configuration(
    area_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete POS configuration"""
    config = db.query(POSConfiguration).filter(
        POSConfiguration.area_id == area_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    db.delete(config)
    db.commit()

    return {"message": "POS configuration deleted successfully"}


@router.post("/configurations/{area_id}/test", response_model=POSConnectionTestResponse)
async def test_pos_connection(
    area_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Test POS API connection"""
    config = db.query(POSConfiguration).filter(
        POSConfiguration.area_id == area_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    if config.provider == "clover":
        client = CloverAPIClient(
            merchant_id=config.merchant_id,
            access_token=config.access_token,
            environment=config.api_environment
        )

        success = await client.test_connection()

        return POSConnectionTestResponse(
            success=success,
            message="Connection successful" if success else "Connection failed",
            provider=config.provider,
            merchant_id=config.merchant_id
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Provider {config.provider} not yet supported"
        )


# ==================== POS Sync Endpoints ====================

@router.post("/sync/{area_id}", response_model=POSSyncResponse)
async def sync_pos_sales(
    area_id: int,
    sync_request: POSSyncRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Sync sales from POS system and auto-create Daily Sales Summary entries"""
    service = POSSyncService(db)

    try:
        result = await service.sync_location(
            area_id=area_id,
            start_date=sync_request.start_date,
            end_date=sync_request.end_date,
            user_id=user.id  # Pass user ID to auto-create DSS
        )

        return POSSyncResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/daily-sales-cache")
def list_daily_sales_cache(
    area_id: Optional[int] = Query(None, description="Filter by area ID"),
    start_date: Optional[date] = Query(None, description="Filter from date"),
    end_date: Optional[date] = Query(None, description="Filter to date"),
    limit: int = Query(50, le=1000, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """List cached daily sales from POS with pagination"""
    service = POSSyncService(db)
    results = service.get_sales_summary(
        area_id=area_id,
        start_date=start_date,
        end_date=end_date
    )

    total_count = len(results)
    paginated_results = results[offset:offset + limit]

    return {
        "items": paginated_results,
        "total": total_count,
        "limit": limit,
        "offset": offset
    }


@router.get("/daily-sales-cache/{sale_date}", response_model=POSDailySalesCacheResponse)
async def get_daily_sales_cache(
    area_id: int,
    sale_date: date,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Get cached POS sales for a specific day"""
    service = POSSyncService(db)
    cache = await service.get_daily_sales_cache(area_id=area_id, sale_date=sale_date)

    if not cache:
        raise HTTPException(
            status_code=404,
            detail=f"No POS sales cache found for area {area_id} on {sale_date}"
        )

    return cache


# ==================== Category GL Mapping Endpoints ====================

@router.get("/category-mappings", response_model=List[POSCategoryGLMappingResponse])
def list_category_mappings(
    area_id: Optional[int] = Query(None, description="Filter by area ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """List POS category to GL account mappings"""
    query = db.query(POSCategoryGLMapping)

    if area_id is not None:
        query = query.filter(POSCategoryGLMapping.area_id == area_id)
    if is_active is not None:
        query = query.filter(POSCategoryGLMapping.is_active == is_active)

    return query.all()


@router.post("/category-mappings", response_model=POSCategoryGLMappingResponse)
def create_category_mapping(
    mapping_data: POSCategoryGLMappingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Create POS category to GL account mapping"""
    # Check for duplicate
    existing = db.query(POSCategoryGLMapping).filter(
        POSCategoryGLMapping.area_id == mapping_data.area_id,
        POSCategoryGLMapping.pos_category == mapping_data.pos_category
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Mapping already exists for category '{mapping_data.pos_category}'"
        )

    mapping = POSCategoryGLMapping(**mapping_data.dict())
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    return mapping


@router.put("/category-mappings/{mapping_id}", response_model=POSCategoryGLMappingResponse)
def update_category_mapping(
    mapping_id: int,
    mapping_data: POSCategoryGLMappingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update category mapping"""
    mapping = db.query(POSCategoryGLMapping).filter(
        POSCategoryGLMapping.id == mapping_id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    for field, value in mapping_data.dict(exclude_unset=True).items():
        setattr(mapping, field, value)

    db.commit()
    db.refresh(mapping)

    return mapping


@router.delete("/category-mappings/{mapping_id}")
def delete_category_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete category mapping"""
    mapping = db.query(POSCategoryGLMapping).filter(
        POSCategoryGLMapping.id == mapping_id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    db.delete(mapping)
    db.commit()

    return {"message": "Category mapping deleted successfully"}


# ==================== Discount Mapping Endpoints ====================

@router.get("/discount-mappings", response_model=List[POSDiscountGLMappingResponse])
def list_discount_mappings(
    area_id: int = Query(..., description="Filter by area/location ID"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """List discount mappings for an area"""
    from accounting.models.pos import POSDiscountGLMapping

    mappings = db.query(POSDiscountGLMapping).filter(
        POSDiscountGLMapping.area_id == area_id
    ).all()

    return mappings


@router.post("/discount-mappings", response_model=POSDiscountGLMappingResponse)
def create_discount_mapping(
    mapping_data: POSDiscountGLMappingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Create a new discount mapping"""
    from accounting.models.pos import POSDiscountGLMapping

    # Check for duplicate
    existing = db.query(POSDiscountGLMapping).filter(
        POSDiscountGLMapping.area_id == mapping_data.area_id,
        POSDiscountGLMapping.pos_discount_name == mapping_data.pos_discount_name
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Mapping for discount '{mapping_data.pos_discount_name}' already exists"
        )

    mapping = POSDiscountGLMapping(**mapping_data.model_dump())
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    return mapping


@router.put("/discount-mappings/{mapping_id}", response_model=POSDiscountGLMappingResponse)
def update_discount_mapping(
    mapping_id: int,
    mapping_data: POSDiscountGLMappingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update discount mapping"""
    from accounting.models.pos import POSDiscountGLMapping

    mapping = db.query(POSDiscountGLMapping).filter(
        POSDiscountGLMapping.id == mapping_id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    update_data = mapping_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(mapping, field, value)

    db.commit()
    db.refresh(mapping)

    return mapping


@router.delete("/discount-mappings/{mapping_id}")
def delete_discount_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete discount mapping"""
    from accounting.models.pos import POSDiscountGLMapping

    mapping = db.query(POSDiscountGLMapping).filter(
        POSDiscountGLMapping.id == mapping_id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    db.delete(mapping)
    db.commit()

    return {"message": "Discount mapping deleted successfully"}


# ==================== Payment Mapping Endpoints ====================

@router.get("/payment-mappings", response_model=List[POSPaymentGLMappingResponse])
def list_payment_mappings(
    area_id: int = Query(..., description="Filter by area/location ID"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """List payment mappings for an area"""
    from accounting.models.pos import POSPaymentGLMapping

    mappings = db.query(POSPaymentGLMapping).filter(
        POSPaymentGLMapping.area_id == area_id
    ).all()

    return mappings


@router.post("/payment-mappings", response_model=POSPaymentGLMappingResponse)
def create_payment_mapping(
    mapping_data: POSPaymentGLMappingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Create a new payment mapping"""
    from accounting.models.pos import POSPaymentGLMapping

    # Check for duplicate
    existing = db.query(POSPaymentGLMapping).filter(
        POSPaymentGLMapping.area_id == mapping_data.area_id,
        POSPaymentGLMapping.pos_payment_type == mapping_data.pos_payment_type
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Mapping for payment type '{mapping_data.pos_payment_type}' already exists"
        )

    mapping = POSPaymentGLMapping(**mapping_data.model_dump())
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    return mapping


@router.put("/payment-mappings/{mapping_id}", response_model=POSPaymentGLMappingResponse)
def update_payment_mapping(
    mapping_id: int,
    mapping_data: POSPaymentGLMappingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update payment mapping"""
    from accounting.models.pos import POSPaymentGLMapping

    mapping = db.query(POSPaymentGLMapping).filter(
        POSPaymentGLMapping.id == mapping_id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    update_data = mapping_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(mapping, field, value)

    db.commit()
    db.refresh(mapping)

    return mapping


@router.delete("/payment-mappings/{mapping_id}")
def delete_payment_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete payment mapping"""
    from accounting.models.pos import POSPaymentGLMapping

    mapping = db.query(POSPaymentGLMapping).filter(
        POSPaymentGLMapping.id == mapping_id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    db.delete(mapping)
    db.commit()

    return {"message": "Payment mapping deleted successfully"}


# Clover Item and Category Fetch Endpoints

@router.get("/clover-items/{area_id}")
async def get_clover_items(
    area_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Fetch items from Clover POS for mapping"""
    # Get POS configuration
    config = db.query(POSConfiguration).filter(
        POSConfiguration.area_id == area_id,
        POSConfiguration.is_active == True
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="No active POS configuration found")

    if config.provider != "clover":
        raise HTTPException(status_code=400, detail="Only Clover POS is currently supported")

    # Initialize Clover client
    from accounting.core.clover_client import CloverAPIClient

    client = CloverAPIClient(
        merchant_id=config.merchant_id,
        access_token=config.access_token,
        environment=config.api_environment
    )

    try:
        # Fetch items and categories
        items_response = await client.get_items(limit=1000)
        categories_response = await client.get_categories(limit=100)

        items = items_response.get("elements", [])
        categories = categories_response.get("elements", [])

        # Build category lookup
        category_map = {cat["id"]: cat["name"] for cat in categories}

        # Process items to include category names
        processed_items = []
        for item in items:
            # Get category names for this item
            item_categories = []
            if item.get("categories") and item["categories"].get("elements"):
                for cat in item["categories"]["elements"]:
                    cat_name = category_map.get(cat["id"], "Unknown")
                    if cat_name not in item_categories:
                        item_categories.append(cat_name)

            processed_items.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "price": item.get("price", 0) / 100 if item.get("price") else 0,  # Convert from cents
                "categories": item_categories,
                "sku": item.get("sku", ""),
                "hidden": item.get("hidden", False)
            })

        return {
            "items": processed_items,
            "categories": [{"id": cat["id"], "name": cat["name"]} for cat in categories],
            "total_items": len(processed_items),
            "total_categories": len(categories)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Clover data: {str(e)}")


@router.get("/clover-categories/{area_id}")
async def get_clover_categories(
    area_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Fetch categories from Clover POS"""
    # Get POS configuration
    config = db.query(POSConfiguration).filter(
        POSConfiguration.area_id == area_id,
        POSConfiguration.is_active == True
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="No active POS configuration found")

    if config.provider != "clover":
        raise HTTPException(status_code=400, detail="Only Clover POS is currently supported")

    # Initialize Clover client
    from accounting.core.clover_client import CloverAPIClient

    client = CloverAPIClient(
        merchant_id=config.merchant_id,
        access_token=config.access_token,
        environment=config.api_environment
    )

    try:
        categories_response = await client.get_categories(limit=100)
        categories = categories_response.get("elements", [])

        return {
            "categories": [
                {
                    "id": cat["id"],
                    "name": cat["name"],
                    "sortOrder": cat.get("sortOrder", 0)
                }
                for cat in categories
            ],
            "total": len(categories)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Clover categories: {str(e)}")


@router.get("/clover-discounts/{area_id}")
async def get_clover_discounts(
    area_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Fetch unique discount names from recent Clover orders"""
    # Get POS configuration
    config = db.query(POSConfiguration).filter(
        POSConfiguration.area_id == area_id,
        POSConfiguration.is_active == True
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="No active POS configuration found")

    if config.provider != "clover":
        raise HTTPException(status_code=400, detail="Only Clover POS is currently supported")

    # Initialize Clover client
    from accounting.core.clover_client import CloverAPIClient
    from datetime import datetime, timedelta

    client = CloverAPIClient(
        merchant_id=config.merchant_id,
        access_token=config.access_token,
        environment=config.api_environment
    )

    try:
        # Fetch recent orders (last 30 days) to get discount names
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)

        orders_response = await client.get_orders(
            start_date=start_date,
            end_date=end_date,
            limit=1000
        )
        orders = orders_response.get("elements", [])

        # Collect unique discount names
        discount_names = set()
        for order in orders:
            # Order-level discounts
            if order.get("discounts") and order["discounts"].get("elements"):
                for discount in order["discounts"]["elements"]:
                    discount_name = discount.get("name")
                    if discount_name:
                        discount_names.add(discount_name)

            # Line item discounts
            if order.get("lineItems") and order["lineItems"].get("elements"):
                for item in order["lineItems"]["elements"]:
                    if item.get("discounts") and item["discounts"].get("elements"):
                        for discount in item["discounts"]["elements"]:
                            discount_name = discount.get("name")
                            if discount_name:
                                discount_names.add(discount_name)

        return {
            "discounts": sorted(list(discount_names)),
            "total": len(discount_names)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Clover discounts: {str(e)}")


@router.get("/clover-payment-types/{area_id}")
async def get_clover_payment_types(
    area_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Fetch unique payment types from recent Clover orders"""
    # Get POS configuration
    config = db.query(POSConfiguration).filter(
        POSConfiguration.area_id == area_id,
        POSConfiguration.is_active == True
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="No active POS configuration found")

    if config.provider != "clover":
        raise HTTPException(status_code=400, detail="Only Clover POS is currently supported")

    # Initialize Clover client
    from accounting.core.clover_client import CloverAPIClient
    from datetime import datetime, timedelta

    client = CloverAPIClient(
        merchant_id=config.merchant_id,
        access_token=config.access_token,
        environment=config.api_environment
    )

    try:
        # Fetch recent orders (last 30 days) to get payment types
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)

        orders_response = await client.get_orders(
            start_date=start_date,
            end_date=end_date,
            limit=1000
        )
        orders = orders_response.get("elements", [])

        # Collect unique payment types (using same logic as sync service)
        payment_types = set()

        for order in orders:
            if order.get("payments") and order["payments"].get("elements"):
                for payment in order["payments"]["elements"]:
                    if payment.get("result") == "SUCCESS":
                        # Get tender label (Clover uses: "Cash", "Credit Card", "Debit Card", etc.)
                        tender = payment.get("tender", {})
                        tender_label = tender.get("label", "").upper() if tender else ""

                        # Determine payment type name (same logic as sync service)
                        if tender_label == "CASH":
                            payment_types.add("CASH")
                        elif tender_label in ["CREDIT CARD", "DEBIT CARD"]:
                            # Combine credit and debit cards into CARD
                            payment_types.add("CARD")
                        elif tender_label in ["GIFT CARD"]:
                            payment_types.add("GIFT_CARD")
                        elif tender_label:
                            # Use the tender label for any other payment types
                            key = tender_label.replace(" ", "_")
                            payment_types.add(key)
                        else:
                            payment_types.add("CASH")

        return {
            "payment_types": sorted(list(payment_types)),
            "total": len(payment_types)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Clover payment types: {str(e)}")


@router.post("/import-to-dss/{area_id}/{sale_date}")
def import_pos_to_daily_sales(
    area_id: int,
    sale_date: date,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Import POS cached sales data to Daily Sales Summary"""
    from accounting.models.daily_sales_summary import DailySalesSummary
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
    def get_now(): return datetime.now(_ET)

    # Get cached POS sales for this date
    cached_sale = db.query(POSDailySalesCache).filter(
        POSDailySalesCache.area_id == area_id,
        POSDailySalesCache.sale_date == sale_date
    ).first()

    if not cached_sale:
        raise HTTPException(
            status_code=404,
            detail=f"No cached POS sales found for {sale_date}"
        )

    # Check if already imported
    existing_dss = db.query(DailySalesSummary).filter(
        DailySalesSummary.area_id == area_id,
        DailySalesSummary.business_date == sale_date,
        DailySalesSummary.imported_from_pos == True
    ).first()

    if existing_dss:
        raise HTTPException(
            status_code=400,
            detail=f"Daily Sales Summary already exists for {sale_date} (ID: {existing_dss.id})"
        )

    # Calculate expected cash deposit (cash payment method only, excluding tips)
    expected_cash = Decimal('0')
    if cached_sale.payment_methods and 'CASH' in cached_sale.payment_methods:
        expected_cash = Decimal(str(cached_sale.payment_methods['CASH']))

    # Create Daily Sales Summary
    dss = DailySalesSummary(
        business_date=sale_date,
        area_id=area_id,
        pos_system=cached_sale.provider,
        gross_sales=cached_sale.gross_sales,
        discounts=cached_sale.total_discounts,
        refunds=0,  # Clover refunds would need separate handling
        net_sales=cached_sale.total_sales,
        tax_collected=cached_sale.total_tax,
        tips=cached_sale.total_tips,
        total_collected=cached_sale.gross_sales,
        payment_breakdown=cached_sale.payment_methods,
        discount_breakdown=cached_sale.discounts,
        category_breakdown=cached_sale.categories,
        expected_cash_deposit=expected_cash,  # Set expected cash for manager reconciliation
        status='draft',
        imported_from='clover_pos',
        imported_from_pos=True,
        imported_at=get_now(),
        pos_sync_date=cached_sale.synced_at,
        pos_transaction_count=cached_sale.transaction_count,
        created_by=user.id,
        notes=f'Imported from Clover POS. {cached_sale.transaction_count} transactions.'
    )

    db.add(dss)
    db.commit()
    db.refresh(dss)

    return {
        "success": True,
        "dss_id": dss.id,
        "business_date": str(dss.business_date),
        "net_sales": float(dss.net_sales),
        "tax_collected": float(dss.tax_collected),
        "tips": float(dss.tips),
        "total_collected": float(dss.total_collected),
        "message": f"Successfully imported sales for {sale_date}. DSS ID: {dss.id}"
    }
