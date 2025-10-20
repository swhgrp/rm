"""
Cache Management API endpoints for administrators
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
import logging

from restaurant_inventory.core.deps import get_current_user, require_admin
from restaurant_inventory.core.cache import cache, CacheKeys
from restaurant_inventory.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/clear-dashboard")
async def clear_dashboard_cache(
    current_user: User = Depends(require_admin)
) -> Dict[str, Any]:
    """Clear all dashboard-related cache (Admin only)"""
    try:
        deleted = CacheKeys.clear_dashboard_cache()
        logger.info(f"Dashboard cache cleared by {current_user.username}: {deleted} keys deleted")
        return {
            "success": True,
            "message": f"Dashboard cache cleared successfully",
            "keys_deleted": deleted
        }
    except Exception as e:
        logger.error(f"Error clearing dashboard cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-inventory")
async def clear_inventory_cache(
    location_id: int = None,
    current_user: User = Depends(require_admin)
) -> Dict[str, Any]:
    """Clear inventory cache for a location or all locations (Admin only)"""
    try:
        deleted = CacheKeys.clear_inventory_cache(location_id)
        location_desc = f"location {location_id}" if location_id else "all locations"
        logger.info(f"Inventory cache cleared for {location_desc} by {current_user.username}: {deleted} keys")
        return {
            "success": True,
            "message": f"Inventory cache cleared for {location_desc}",
            "keys_deleted": deleted
        }
    except Exception as e:
        logger.error(f"Error clearing inventory cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-all")
async def clear_all_cache(
    current_user: User = Depends(require_admin)
) -> Dict[str, Any]:
    """Clear entire cache - use with caution! (Admin only)"""
    try:
        success = cache.clear_all()
        if success:
            logger.warning(f"ENTIRE cache cleared by {current_user.username}")
            return {
                "success": True,
                "message": "Entire cache cleared successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to clear cache")
    except Exception as e:
        logger.error(f"Error clearing all cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_cache_stats(
    current_user: User = Depends(require_admin)
) -> Dict[str, Any]:
    """Get cache statistics (Admin only)"""
    try:
        stats = cache.get_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def cache_health(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Check if cache is enabled and working"""
    return {
        "enabled": cache.enabled,
        "status": "healthy" if cache.enabled else "disabled"
    }
