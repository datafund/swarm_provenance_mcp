"""Client for communicating with the swarm_connect FastAPI gateway."""

import json
from typing import Dict, List, Any, Optional
import requests
from requests.exceptions import RequestException

from .config import settings


class SwarmGatewayClient:
    """Client for interacting with the Swarm gateway API."""

    def __init__(self, base_url: Optional[str] = None):
        """Initialize the gateway client.

        Args:
            base_url: Override the default gateway URL from settings
        """
        self.base_url = (base_url or settings.swarm_gateway_url).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": f"{settings.mcp_server_name}/{settings.mcp_server_version}"
        })

    def purchase_stamp(
        self,
        amount: int,
        depth: int,
        label: Optional[str] = None
    ) -> Dict[str, Any]:
        """Purchase a new postage stamp.

        Args:
            amount: Amount of the stamp in wei
            depth: Depth of the stamp
            label: Optional label for the stamp

        Returns:
            Response containing batchID and message

        Raises:
            RequestException: If the request fails
        """
        url = f"{self.base_url}/api/v1/stamps"
        payload = {
            "amount": amount,
            "depth": depth
        }
        if label:
            payload["label"] = label

        response = self.session.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_stamp_details(self, stamp_id: str) -> Dict[str, Any]:
        """Get details for a specific stamp.

        Args:
            stamp_id: The batch ID of the stamp

        Returns:
            Stamp details including expiration and usage info

        Raises:
            RequestException: If the request fails
        """
        url = f"{self.base_url}/api/v1/stamps/{stamp_id}"
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def list_stamps(self) -> Dict[str, Any]:
        """List all available stamps.

        Returns:
            Response containing list of stamps and total count

        Raises:
            RequestException: If the request fails
        """
        url = f"{self.base_url}/api/v1/stamps"
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def extend_stamp(self, stamp_id: str, amount: int) -> Dict[str, Any]:
        """Extend an existing stamp with additional funds.

        Args:
            stamp_id: The batch ID of the stamp to extend
            amount: Additional amount to add in wei

        Returns:
            Response containing batchID and message

        Raises:
            RequestException: If the request fails
        """
        url = f"{self.base_url}/api/v1/stamps/{stamp_id}/extend"
        payload = {"amount": amount}

        response = self.session.patch(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()


    def close(self):
        """Close the HTTP session."""
        self.session.close()