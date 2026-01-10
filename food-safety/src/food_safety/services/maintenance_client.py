"""Maintenance Service client for Food Safety"""
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from decimal import Decimal
import httpx

from food_safety.config import settings

logger = logging.getLogger(__name__)


@dataclass
class MaintenanceEquipment:
    """Equipment data from Maintenance Service"""
    id: int
    name: str
    location_id: int
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    status: str = "operational"
    serial_number: Optional[str] = None
    model_number: Optional[str] = None
    manufacturer: Optional[str] = None
    qr_code: Optional[str] = None

    # Food safety specific fields (from specifications JSON)
    equipment_type: Optional[str] = None  # cooler, freezer, hot_holding
    min_temp: Optional[Decimal] = None
    max_temp: Optional[Decimal] = None
    temp_unit: str = "F"


class MaintenanceServiceClient:
    """Client for communicating with the Maintenance Service"""

    def __init__(self):
        self.base_url = settings.MAINTENANCE_SERVICE_URL
        self.timeout = httpx.Timeout(10.0)

    def _parse_equipment(self, data: Dict[str, Any]) -> MaintenanceEquipment:
        """Parse equipment data from API response"""
        # Try to extract food safety specs from specifications JSON
        specs = {}
        if data.get("specifications"):
            try:
                import json
                specs = json.loads(data["specifications"]) if isinstance(data["specifications"], str) else data["specifications"]
            except:
                pass

        return MaintenanceEquipment(
            id=data["id"],
            name=data["name"],
            location_id=data["location_id"],
            category_id=data.get("category_id"),
            category_name=data.get("category_name"),
            status=data.get("status", "operational"),
            serial_number=data.get("serial_number"),
            model_number=data.get("model_number"),
            manufacturer=data.get("manufacturer"),
            qr_code=data.get("qr_code"),
            equipment_type=specs.get("equipment_type") or data.get("category_name", "").lower().replace(" ", "_"),
            min_temp=Decimal(str(specs["min_temp"])) if specs.get("min_temp") else None,
            max_temp=Decimal(str(specs["max_temp"])) if specs.get("max_temp") else None,
            temp_unit=specs.get("temp_unit", "F")
        )

    async def get_equipment(self, equipment_id: int) -> Optional[MaintenanceEquipment]:
        """Get equipment details from Maintenance service"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/equipment/{equipment_id}")
                if response.status_code == 200:
                    return self._parse_equipment(response.json())
                elif response.status_code == 404:
                    logger.warning(f"Equipment {equipment_id} not found in Maintenance service")
                    return None
                else:
                    logger.error(f"Maintenance service returned {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Failed to get equipment from Maintenance service: {e}")
            return None

    async def list_equipment(
        self,
        location_id: Optional[int] = None,
        category_id: Optional[int] = None,
        status: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[MaintenanceEquipment]:
        """List equipment from Maintenance service"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {}
                if location_id:
                    params["location_id"] = location_id
                if category_id:
                    params["category_id"] = category_id
                if status:
                    params["status"] = status
                if search:
                    params["search"] = search

                response = await client.get(f"{self.base_url}/equipment", params=params)
                if response.status_code == 200:
                    equipment_list = response.json()
                    return [self._parse_equipment(eq) for eq in equipment_list]
                else:
                    logger.error(f"Maintenance service returned {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"Failed to list equipment from Maintenance service: {e}")
            return []

    async def get_equipment_by_location(self, location_id: int) -> List[MaintenanceEquipment]:
        """Get all equipment for a specific location"""
        return await self.list_equipment(location_id=location_id)

    async def get_temperature_equipment(self, location_id: Optional[int] = None) -> List[MaintenanceEquipment]:
        """Get equipment that requires temperature monitoring (coolers, freezers, hot holding)"""
        all_equipment = await self.list_equipment(location_id=location_id)

        # Filter to temperature-related equipment types/categories
        temp_keywords = {
            "cooler", "freezer", "refriger",  # refrigerator, refrigeration
            "walk-in", "walk_in", "reach-in", "reach_in",
            "hot_holding", "hot holding", "food warmer", "warmer",
            "ice machine", "prep table"  # refrigerated prep tables
        }

        return [
            eq for eq in all_equipment
            if eq.status.upper() == "OPERATIONAL" and (
                (eq.equipment_type and any(kw in eq.equipment_type.lower() for kw in temp_keywords)) or
                (eq.category_name and any(kw in eq.category_name.lower() for kw in temp_keywords)) or
                (eq.name and any(kw in eq.name.lower() for kw in temp_keywords))
            )
        ]

    async def get_categories(self) -> List[Dict[str, Any]]:
        """Get equipment categories from Maintenance service"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/categories")
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Maintenance service returned {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"Failed to get categories from Maintenance service: {e}")
            return []


# Singleton instance
maintenance_client = MaintenanceServiceClient()
