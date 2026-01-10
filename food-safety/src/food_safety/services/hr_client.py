"""HR Service client for Food Safety"""
import logging
from typing import Optional, Dict, Any, List
import httpx

from food_safety.config import settings

logger = logging.getLogger(__name__)


class HRServiceClient:
    """Client for communicating with the HR Service"""

    def __init__(self):
        self.base_url = settings.HR_SERVICE_URL
        self.timeout = httpx.Timeout(10.0)

    async def get_employee(self, employee_id: int) -> Optional[Dict[str, Any]]:
        """Get employee details from HR service"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/employees/{employee_id}")
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    logger.error(f"HR service returned {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Failed to get employee from HR service: {e}")
            return None

    async def get_employee_name(self, employee_id: int) -> Optional[str]:
        """Get employee name from HR service"""
        employee = await self.get_employee(employee_id)
        if employee:
            first = employee.get("first_name", "")
            last = employee.get("last_name", "")
            return f"{first} {last}".strip() or None
        return None

    async def list_employees(self, location_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """List employees from HR service"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {}
                if location_id:
                    params["location_id"] = location_id

                response = await client.get(f"{self.base_url}/employees", params=params)
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"HR service returned {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"Failed to list employees from HR service: {e}")
            return []


# Singleton instance
hr_client = HRServiceClient()
