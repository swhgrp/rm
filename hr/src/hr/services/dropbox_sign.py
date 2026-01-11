"""
Dropbox Sign (HelloSign) API Service Client

Handles all interactions with Dropbox Sign API for e-signatures.
"""

import os
import logging
import hashlib
import hmac
from datetime import datetime
from typing import Optional, Dict, Any, List
import httpx

logger = logging.getLogger(__name__)

# Dropbox Sign API configuration
DROPBOX_SIGN_API_KEY = os.getenv("DROPBOX_SIGN_API_KEY", "")
DROPBOX_SIGN_CLIENT_ID = os.getenv("DROPBOX_SIGN_CLIENT_ID", "")
DROPBOX_SIGN_API_BASE = "https://api.hellosign.com/v3"

# Webhook configuration
WEBHOOK_SECRET = os.getenv("DROPBOX_SIGN_WEBHOOK_SECRET", "")


class DropboxSignService:
    """Service class for Dropbox Sign API interactions"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or DROPBOX_SIGN_API_KEY
        self.base_url = DROPBOX_SIGN_API_BASE
        self.client_id = DROPBOX_SIGN_CLIENT_ID

    def _get_auth(self) -> tuple:
        """Get basic auth tuple for API requests"""
        return (self.api_key, "")

    async def send_signature_request(
        self,
        title: str,
        subject: str,
        message: str,
        signers: List[Dict[str, str]],
        file_paths: List[str] = None,
        file_urls: List[str] = None,
        template_id: str = None,
        metadata: Dict[str, Any] = None,
        test_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Send a signature request via Dropbox Sign.

        Args:
            title: Document title
            subject: Email subject line
            message: Email message body
            signers: List of signer dicts with 'email_address', 'name', 'order' (optional)
            file_paths: Local file paths to upload
            file_urls: URLs to documents
            template_id: Dropbox Sign template ID (if using template)
            metadata: Additional metadata to attach
            test_mode: If True, request is in test mode (not legally binding)

        Returns:
            API response with signature_request_id
        """
        try:
            async with httpx.AsyncClient() as client:
                if template_id:
                    # Use template-based request
                    return await self._send_with_template(
                        client, template_id, title, subject, message,
                        signers, metadata, test_mode
                    )
                else:
                    # Use file-based request
                    return await self._send_with_files(
                        client, title, subject, message, signers,
                        file_paths, file_urls, metadata, test_mode
                    )
        except Exception as e:
            logger.error(f"Error sending signature request: {e}")
            raise

    async def _send_with_files(
        self,
        client: httpx.AsyncClient,
        title: str,
        subject: str,
        message: str,
        signers: List[Dict[str, str]],
        file_paths: List[str] = None,
        file_urls: List[str] = None,
        metadata: Dict[str, Any] = None,
        test_mode: bool = False
    ) -> Dict[str, Any]:
        """Send signature request with file uploads"""
        url = f"{self.base_url}/signature_request/send"

        # Build form data
        data = {
            "title": title,
            "subject": subject,
            "message": message,
            "test_mode": "1" if test_mode else "0",
        }

        # Add signers
        for i, signer in enumerate(signers):
            data[f"signers[{i}][email_address]"] = signer["email_address"]
            data[f"signers[{i}][name]"] = signer["name"]
            if "order" in signer:
                data[f"signers[{i}][order]"] = str(signer["order"])

        # Add metadata
        if metadata:
            for key, value in metadata.items():
                data[f"metadata[{key}]"] = str(value)

        # Add file URLs if provided
        if file_urls:
            for i, url_path in enumerate(file_urls):
                data[f"file_url[{i}]"] = url_path

        # Prepare files for upload
        files = []
        if file_paths:
            for i, file_path in enumerate(file_paths):
                if os.path.exists(file_path):
                    files.append(
                        (f"file[{i}]", (os.path.basename(file_path), open(file_path, "rb"), "application/pdf"))
                    )

        try:
            response = await client.post(
                url,
                data=data,
                files=files if files else None,
                auth=self._get_auth(),
                timeout=60.0
            )
            response.raise_for_status()
            return response.json()
        finally:
            # Close file handles
            for _, file_tuple in files:
                if hasattr(file_tuple[1], 'close'):
                    file_tuple[1].close()

    async def _send_with_template(
        self,
        client: httpx.AsyncClient,
        template_id: str,
        title: str,
        subject: str,
        message: str,
        signers: List[Dict[str, str]],
        metadata: Dict[str, Any] = None,
        test_mode: bool = False
    ) -> Dict[str, Any]:
        """Send signature request using a template"""
        url = f"{self.base_url}/signature_request/send_with_template"

        data = {
            "template_ids[0]": template_id,
            "title": title,
            "subject": subject,
            "message": message,
            "test_mode": "1" if test_mode else "0",
        }

        # Add signers - template uses role names
        for i, signer in enumerate(signers):
            role = signer.get("role", "Signer")
            data[f"signers[{role}][email_address]"] = signer["email_address"]
            data[f"signers[{role}][name]"] = signer["name"]

        # Add metadata
        if metadata:
            for key, value in metadata.items():
                data[f"metadata[{key}]"] = str(value)

        response = await client.post(
            url,
            data=data,
            auth=self._get_auth(),
            timeout=60.0
        )
        response.raise_for_status()
        return response.json()

    async def get_signature_request(self, signature_request_id: str) -> Dict[str, Any]:
        """Get details of a signature request"""
        url = f"{self.base_url}/signature_request/{signature_request_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                auth=self._get_auth(),
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def get_signature_request_files(
        self,
        signature_request_id: str,
        file_type: str = "pdf"
    ) -> bytes:
        """
        Download the signed document files.

        Args:
            signature_request_id: The signature request ID
            file_type: 'pdf' or 'zip'

        Returns:
            File content as bytes
        """
        url = f"{self.base_url}/signature_request/files/{signature_request_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"file_type": file_type},
                auth=self._get_auth(),
                timeout=120.0
            )
            response.raise_for_status()
            return response.content

    async def cancel_signature_request(self, signature_request_id: str) -> bool:
        """Cancel a signature request"""
        url = f"{self.base_url}/signature_request/cancel/{signature_request_id}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                auth=self._get_auth(),
                timeout=30.0
            )
            return response.status_code == 200

    async def send_reminder(
        self,
        signature_request_id: str,
        email_address: str
    ) -> Dict[str, Any]:
        """Send a reminder to a signer"""
        url = f"{self.base_url}/signature_request/remind/{signature_request_id}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                data={"email_address": email_address},
                auth=self._get_auth(),
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def list_templates(self) -> Dict[str, Any]:
        """List available signature templates"""
        url = f"{self.base_url}/template/list"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                auth=self._get_auth(),
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def get_template(self, template_id: str) -> Dict[str, Any]:
        """Get template details"""
        url = f"{self.base_url}/template/{template_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                auth=self._get_auth(),
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def verify_webhook_signature(
        event_time: str,
        event_type: str,
        event_hash: str,
        api_key: str = None
    ) -> bool:
        """
        Verify webhook signature from Dropbox Sign.

        Dropbox Sign uses HMAC-SHA256 for webhook verification.
        """
        api_key = api_key or DROPBOX_SIGN_API_KEY

        # Construct the message to hash
        message = f"{event_time}{event_type}"

        # Calculate expected hash
        expected_hash = hmac.new(
            api_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_hash, event_hash)

    @staticmethod
    def parse_webhook_event(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse webhook event from Dropbox Sign.

        Returns normalized event data.
        """
        event = data.get("event", {})
        event_type = event.get("event_type", "")

        # Extract signature request info
        signature_request = event.get("signature_request", {})

        # Extract signer info if available
        signer_email = None
        related_signatures = event.get("related_signatures", [])
        if related_signatures:
            signer_email = related_signatures[0].get("signer_email_address")

        return {
            "event_type": event_type,
            "signature_request_id": signature_request.get("signature_request_id"),
            "title": signature_request.get("title"),
            "is_complete": signature_request.get("is_complete", False),
            "signer_email": signer_email,
            "event_time": event.get("event_time"),
            "event_hash": event.get("event_hash"),
            "metadata": signature_request.get("metadata", {}),
            "signatures": signature_request.get("signatures", [])
        }


# Singleton instance
dropbox_sign_service = DropboxSignService()
