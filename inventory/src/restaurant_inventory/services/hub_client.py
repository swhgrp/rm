"""
Hub Client Service

Client for calling Integration Hub API to fetch invoice and vendor item data.
Makes Hub the source of truth for these entities.
"""

import os
import httpx
import logging
from typing import Optional, List, Dict, Any
from datetime import date

logger = logging.getLogger(__name__)

# Hub API URL (internal Docker network)
HUB_API_URL = os.getenv("HUB_API_URL", "http://integration-hub:8000")


class HubClient:
    """Client for Integration Hub API"""

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or HUB_API_URL).rstrip('/')
        self.timeout = 30.0

    async def get_invoices(
        self,
        page: int = 1,
        page_size: int = 50,
        status: Optional[str] = None,
        vendor_name: Optional[str] = None,
        location_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        sent_to_inventory: Optional[bool] = None,
        include_statements: bool = False
    ) -> Dict[str, Any]:
        """
        Fetch invoices from Hub API.

        Returns:
            Dict with 'invoices', 'total', 'page', 'page_size', 'pages' keys
        """
        params = {
            "page": page,
            "page_size": page_size,
            "include_statements": include_statements
        }

        if status:
            params["status"] = status
        if vendor_name:
            params["vendor_name"] = vendor_name
        if location_id:
            params["location_id"] = location_id
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
        if sent_to_inventory is not None:
            params["sent_to_inventory"] = sent_to_inventory

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/invoices/",
                    params=params
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching invoices from Hub: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error fetching invoices from Hub: {str(e)}")
            raise

    async def get_invoice(self, invoice_id: int) -> Dict[str, Any]:
        """
        Fetch single invoice with full details from Hub API.

        Returns:
            Dict with invoice details and items
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/invoices/{invoice_id}"
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error(f"HTTP error fetching invoice {invoice_id} from Hub: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error fetching invoice {invoice_id} from Hub: {str(e)}")
            raise

    async def get_invoice_by_number(
        self,
        invoice_number: str,
        vendor_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Look up invoice by number.
        """
        params = {}
        if vendor_name:
            params["vendor_name"] = vendor_name

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/invoices/by-number/{invoice_number}",
                    params=params
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error looking up invoice by number: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error looking up invoice by number: {str(e)}")
            raise

    async def get_invoice_items(
        self,
        invoice_id: int,
        mapped_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetch items for a specific invoice.
        """
        params = {}
        if mapped_only:
            params["mapped_only"] = True

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/invoices/{invoice_id}/items",
                    params=params
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            logger.error(f"HTTP error fetching invoice items from Hub: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error fetching invoice items from Hub: {str(e)}")
            raise

    async def get_vendor_items(
        self,
        page: int = 1,
        page_size: int = 50,
        vendor_id: Optional[int] = None,
        master_item_id: Optional[int] = None,
        search: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Fetch vendor items from Hub API.
        """
        params = {
            "page": page,
            "page_size": page_size
        }

        if vendor_id:
            params["vendor_id"] = vendor_id
        if master_item_id:
            params["master_item_id"] = master_item_id
        if search:
            params["search"] = search
        if is_active is not None:
            params["is_active"] = is_active

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/vendor-items/",
                    params=params
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching vendor items from Hub: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error fetching vendor items from Hub: {str(e)}")
            raise

    async def get_vendor_item(self, vendor_item_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch single vendor item by ID.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/vendor-items/{vendor_item_id}"
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching vendor item from Hub: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error fetching vendor item from Hub: {str(e)}")
            raise

    async def get_vendor_item_by_sku(
        self,
        vendor_sku: str,
        vendor_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Look up vendor item by SKU.
        """
        params = {}
        if vendor_id:
            params["vendor_id"] = vendor_id

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/vendor-items/by-sku/{vendor_sku}",
                    params=params
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error looking up vendor item by SKU: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error looking up vendor item by SKU: {str(e)}")
            raise

    async def health_check(self) -> bool:
        """
        Check if Hub is reachable.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception:
            return False

    async def create_vendor_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new vendor item in Hub.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/vendor-items/",
                    json=item_data
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error creating vendor item in Hub: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error creating vendor item in Hub: {str(e)}")
            raise

    async def update_vendor_item(
        self,
        vendor_item_id: int,
        item_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a vendor item in Hub.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.put(
                    f"{self.base_url}/api/v1/vendor-items/{vendor_item_id}",
                    json=item_data
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error(f"HTTP error updating vendor item in Hub: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error updating vendor item in Hub: {str(e)}")
            raise

    async def delete_vendor_item(self, vendor_item_id: int) -> Dict[str, Any]:
        """
        Delete (soft-delete) a vendor item in Hub.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.delete(
                    f"{self.base_url}/api/v1/vendor-items/{vendor_item_id}"
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error(f"HTTP error deleting vendor item in Hub: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error deleting vendor item in Hub: {str(e)}")
            raise


# Singleton instance
_hub_client: Optional[HubClient] = None


def get_hub_client() -> HubClient:
    """Get or create Hub client singleton"""
    global _hub_client
    if _hub_client is None:
        _hub_client = HubClient()
    return _hub_client
