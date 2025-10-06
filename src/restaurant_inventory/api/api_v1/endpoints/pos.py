"""
POS Integration API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date

from restaurant_inventory.core.deps import get_db, get_current_user, require_manager_or_admin
from restaurant_inventory.models.user import User
from restaurant_inventory.models.pos_sale import POSConfiguration
from restaurant_inventory.schemas.pos import (
    POSConfigurationCreate,
    POSConfigurationUpdate,
    POSConfigurationResponse,
    POSConnectionTest,
    POSSyncRequest
)
from restaurant_inventory.core.clover_client import CloverAPIClient
from restaurant_inventory.core.audit import log_audit_event

router = APIRouter()


@router.get("/configurations", response_model=List[POSConfigurationResponse])
async def get_pos_configurations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all POS configurations"""
    configs = db.query(POSConfiguration).all()

    # Mask sensitive data
    for config in configs:
        config.api_key = "****" if config.api_key else None
        config.access_token = "****" if config.access_token else None

    return configs


@router.get("/configurations/{location_id}", response_model=POSConfigurationResponse)
async def get_pos_configuration(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get POS configuration for a specific location"""
    config = db.query(POSConfiguration).filter(
        POSConfiguration.location_id == location_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    # Mask sensitive data
    config.api_key = "****" if config.api_key else None
    config.access_token = "****" if config.access_token else None

    return config


@router.post("/configurations", response_model=POSConfigurationResponse, status_code=status.HTTP_201_CREATED)
async def create_pos_configuration(
    config: POSConfigurationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create POS configuration for a location"""

    # Check if configuration already exists for this location
    existing = db.query(POSConfiguration).filter(
        POSConfiguration.location_id == config.location_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="POS configuration already exists for this location"
        )

    # Create configuration
    db_config = POSConfiguration(**config.dict())
    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    # Audit log
    log_audit_event(
        db=db,
        user=current_user,
        action="create",
        entity_type="pos_configuration",
        entity_id=db_config.id
    )

    # Mask sensitive data in response
    db_config.api_key = "****" if db_config.api_key else None
    db_config.access_token = "****" if db_config.access_token else None

    return db_config


@router.put("/configurations/{location_id}", response_model=POSConfigurationResponse)
async def update_pos_configuration(
    location_id: int,
    config_update: POSConfigurationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update POS configuration"""

    config = db.query(POSConfiguration).filter(
        POSConfiguration.location_id == location_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    # Update fields
    update_data = config_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)

    # Audit log
    log_audit_event(
        db=db,
        user=current_user,
        action="update",
        entity_type="pos_configuration",
        entity_id=config.id,
        changes=update_data
    )

    # Mask sensitive data
    config.api_key = "****" if config.api_key else None
    config.access_token = "****" if config.access_token else None

    return config


@router.post("/configurations/{location_id}/test", response_model=POSConnectionTest)
async def test_pos_connection(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Test POS API connection"""

    config = db.query(POSConfiguration).filter(
        POSConfiguration.location_id == location_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    if not config.merchant_id or not config.access_token:
        raise HTTPException(
            status_code=400,
            detail="Missing merchant_id or access_token in configuration"
        )

    try:
        # Log what we're testing with (for debugging)
        print(f"Testing Clover connection:")
        print(f"  Merchant ID: {config.merchant_id}")
        print(f"  Environment: {config.api_environment}")
        print(f"  Token (first 10 chars): {config.access_token[:10] if config.access_token else 'None'}...")

        # Initialize Clover client
        client = CloverAPIClient(
            merchant_id=config.merchant_id,
            access_token=config.access_token,
            environment=config.api_environment
        )

        print(f"  Base URL: {client.base_url}")
        print(f"  Full URL: {client.base_url}/v3/merchants/{config.merchant_id}")

        # Test connection
        is_connected = await client.test_connection()

        if is_connected:
            return POSConnectionTest(
                success=True,
                message="Successfully connected to Clover POS",
                merchant_id=config.merchant_id
            )
        else:
            return POSConnectionTest(
                success=False,
                message="Failed to connect to Clover POS. Please check your credentials."
            )

    except Exception as e:
        print(f"Connection test exception: {str(e)}")
        return POSConnectionTest(
            success=False,
            message=f"Connection error: {str(e)}"
        )


@router.delete("/configurations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pos_configuration(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete POS configuration"""

    config = db.query(POSConfiguration).filter(
        POSConfiguration.location_id == location_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    # Audit log
    log_audit_event(
        db=db,
        user=current_user,
        action="delete",
        entity_type="pos_configuration",
        entity_id=config.id
    )

    db.delete(config)
    db.commit()

    return None
