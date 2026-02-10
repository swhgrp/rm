"""
Area management API endpoints

Areas/Locations are synced from Inventory system.
Inventory is the source of truth for locations.
"""
import os
import httpx
import logging
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List

# Logo storage directory
LOGO_UPLOAD_DIR = Path("/app/uploads/logos")

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.area import Area
from accounting.models.role import role_areas
from accounting.schemas.area import AreaCreate, AreaUpdate, AreaResponse
from accounting.api.auth import require_admin, require_auth

logger = logging.getLogger(__name__)

# Inventory API URL for syncing locations
INVENTORY_API_URL = os.getenv("INVENTORY_API_URL", "http://inventory-app:8000/api")

router = APIRouter(prefix="/api/areas", tags=["areas"])


@router.get("/", response_model=List[AreaResponse])
def list_areas(
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)  # Changed from require_admin - any user can list areas
):
    """List all areas/locations - available to all authenticated users"""
    query = db.query(Area)
    if not include_inactive:
        query = query.filter(Area.is_active == True)

    areas = query.offset(skip).limit(limit).all()
    return areas


@router.get("/{area_id}", response_model=AreaResponse)
def get_area(
    area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get a specific area by ID (admin only)"""
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Area not found"
        )
    return area


@router.post("/", response_model=AreaResponse)
def create_area(
    area_data: AreaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new area (admin only)"""
    # Check if area name already exists
    existing_name = db.query(Area).filter(Area.name == area_data.name).first()
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Area name already exists"
        )

    # Check if area code already exists
    existing_code = db.query(Area).filter(Area.code == area_data.code).first()
    if existing_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Area code already exists"
        )

    # Create new area
    new_area = Area(
        name=area_data.name,
        code=area_data.code,
        description=area_data.description,
        # Legal entity information
        legal_name=area_data.legal_name,
        ein=area_data.ein,
        entity_type=area_data.entity_type,
        # Address information
        address_line1=area_data.address_line1,
        address_line2=area_data.address_line2,
        city=area_data.city,
        state=area_data.state,
        zip_code=area_data.zip_code,
        country=area_data.country,
        # Contact information
        phone=area_data.phone,
        email=area_data.email,
        website=area_data.website,
        # GL Account Configuration
        safe_account_id=area_data.safe_account_id
    )

    db.add(new_area)
    db.commit()
    db.refresh(new_area)

    return new_area


@router.put("/{area_id}", response_model=AreaResponse)
def update_area(
    area_id: int,
    area_data: AreaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update an area (admin only)"""
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Area not found"
        )

    # Update fields if provided
    if area_data.name is not None:
        # Check if name already exists for another area
        existing_name = db.query(Area).filter(
            Area.name == area_data.name,
            Area.id != area_id
        ).first()
        if existing_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Area name already exists"
            )
        area.name = area_data.name

    if area_data.code is not None:
        # Check if code already exists for another area
        existing_code = db.query(Area).filter(
            Area.code == area_data.code,
            Area.id != area_id
        ).first()
        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Area code already exists"
            )
        area.code = area_data.code

    if area_data.description is not None:
        area.description = area_data.description

    if area_data.is_active is not None:
        area.is_active = area_data.is_active

    # Legal entity information
    if area_data.legal_name is not None:
        area.legal_name = area_data.legal_name

    if area_data.ein is not None:
        area.ein = area_data.ein

    if area_data.entity_type is not None:
        area.entity_type = area_data.entity_type

    # Address information
    if area_data.address_line1 is not None:
        area.address_line1 = area_data.address_line1

    if area_data.address_line2 is not None:
        area.address_line2 = area_data.address_line2

    if area_data.city is not None:
        area.city = area_data.city

    if area_data.state is not None:
        area.state = area_data.state

    if area_data.zip_code is not None:
        area.zip_code = area_data.zip_code

    if area_data.country is not None:
        area.country = area_data.country

    # Contact information
    if area_data.phone is not None:
        area.phone = area_data.phone

    if area_data.email is not None:
        area.email = area_data.email

    if area_data.website is not None:
        area.website = area_data.website

    # GL Account Configuration
    if area_data.safe_account_id is not None:
        area.safe_account_id = area_data.safe_account_id

    db.commit()
    db.refresh(area)

    return area


@router.delete("/{area_id}")
def delete_area(
    area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete an area (admin only)"""
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Area not found"
        )

    # Check if any roles are assigned to this area
    roles_count = db.query(role_areas).filter(role_areas.c.area_id == area_id).count()
    if roles_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete area: it is assigned to {roles_count} role(s)"
        )

    db.delete(area)
    db.commit()

    return {"message": "Area deleted successfully"}


# ============================================================================
# SYNC ENDPOINTS - Sync locations from Inventory (source of truth)
# ============================================================================

@router.post("/sync-from-inventory")
async def sync_areas_from_inventory(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Sync areas/locations from Inventory system.

    Inventory is the source of truth for locations.
    This endpoint pulls locations from Inventory and updates local areas.

    - Creates new areas for locations that don't exist
    - Updates existing areas to match Inventory data
    - Does NOT delete areas (manual cleanup required)
    """
    try:
        # Fetch locations from Inventory
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{INVENTORY_API_URL}/locations/_sync?include_inactive=true")

            if response.status_code != 200:
                logger.error(f"Failed to fetch locations from Inventory: {response.status_code}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to fetch locations from Inventory: {response.status_code}"
                )

            inventory_locations = response.json()

        logger.info(f"Fetched {len(inventory_locations)} locations from Inventory")

        created = 0
        updated = 0
        errors = []

        for inv_loc in inventory_locations:
            try:
                code = inv_loc.get("code")
                if not code:
                    errors.append(f"Location ID {inv_loc.get('id')} has no code, skipping")
                    continue

                # Try to find existing area by code
                existing = db.query(Area).filter(Area.code == code).first()

                if existing:
                    # Update existing area
                    existing.name = inv_loc.get("name", existing.name)
                    existing.legal_name = inv_loc.get("legal_name")
                    existing.ein = inv_loc.get("ein")
                    existing.city = inv_loc.get("city")
                    existing.state = inv_loc.get("state")
                    existing.zip_code = inv_loc.get("zip_code")
                    existing.address_line1 = inv_loc.get("address")
                    existing.phone = inv_loc.get("phone")
                    existing.is_active = inv_loc.get("is_active", True)
                    updated += 1
                    logger.info(f"Updated area {code}: {existing.name}")
                else:
                    # Create new area
                    new_area = Area(
                        code=code,
                        name=inv_loc.get("name"),
                        legal_name=inv_loc.get("legal_name"),
                        ein=inv_loc.get("ein"),
                        city=inv_loc.get("city"),
                        state=inv_loc.get("state"),
                        zip_code=inv_loc.get("zip_code"),
                        address_line1=inv_loc.get("address"),
                        phone=inv_loc.get("phone"),
                        is_active=inv_loc.get("is_active", True)
                    )
                    db.add(new_area)
                    created += 1
                    logger.info(f"Created area {code}: {new_area.name}")

            except Exception as e:
                errors.append(f"Error processing location {inv_loc.get('id')}: {str(e)}")
                logger.error(f"Error processing location: {e}")

        db.commit()

        return {
            "success": True,
            "message": "Sync completed",
            "inventory_locations": len(inventory_locations),
            "created": created,
            "updated": updated,
            "errors": errors[:10] if errors else []
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# LOGO UPLOAD ENDPOINTS
# ============================================================================

@router.post("/{area_id}/logo")
async def upload_area_logo(
    area_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Upload a logo image for an area/location.

    Supported formats: PNG, JPG, JPEG, GIF, SVG
    Max size: 2MB
    """
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    # Validate file type
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg'}
    file_ext = Path(file.filename).suffix.lower() if file.filename else ''
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )

    # Read file content
    content = await file.read()

    # Validate file size (2MB max)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 2MB")

    # Create upload directory if it doesn't exist
    LOGO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Delete old logo if exists
    if area.logo_path:
        old_logo_path = LOGO_UPLOAD_DIR / area.logo_path
        if old_logo_path.exists():
            try:
                old_logo_path.unlink()
            except Exception as e:
                logger.warning(f"Could not delete old logo: {e}")

    # Generate unique filename
    safe_code = area.code.lower().replace(' ', '_')
    filename = f"{safe_code}_logo{file_ext}"
    file_path = LOGO_UPLOAD_DIR / filename

    # Save file
    try:
        with open(file_path, 'wb') as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Error saving logo: {e}")
        raise HTTPException(status_code=500, detail="Error saving logo file")

    # Update area with logo path
    area.logo_path = filename
    db.commit()

    logger.info(f"Uploaded logo for area {area.code}: {filename}")

    return {
        "success": True,
        "message": f"Logo uploaded for {area.name}",
        "logo_path": filename
    }


@router.delete("/{area_id}/logo")
async def delete_area_logo(
    area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete the logo for an area/location"""
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    if not area.logo_path:
        raise HTTPException(status_code=404, detail="Area has no logo")

    # Delete file
    logo_path = LOGO_UPLOAD_DIR / area.logo_path
    if logo_path.exists():
        try:
            logo_path.unlink()
        except Exception as e:
            logger.warning(f"Could not delete logo file: {e}")

    # Clear logo path in database
    area.logo_path = None
    db.commit()

    return {"success": True, "message": "Logo deleted"}


@router.get("/{area_id}/logo")
async def get_area_logo(
    area_id: int,
    db: Session = Depends(get_db)
):
    """Get the logo image for an area/location"""
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    if not area.logo_path:
        raise HTTPException(status_code=404, detail="Area has no logo")

    logo_path = LOGO_UPLOAD_DIR / area.logo_path
    if not logo_path.exists():
        raise HTTPException(status_code=404, detail="Logo file not found")

    # Determine media type
    ext = logo_path.suffix.lower()
    media_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml'
    }
    media_type = media_types.get(ext, 'application/octet-stream')

    return FileResponse(logo_path, media_type=media_type)
