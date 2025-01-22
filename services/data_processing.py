import logging
from typing import List, Dict
from datetime import datetime
import httpx
from fastapi import HTTPException
from config import logger, APP_SECRET
from models import DeviceData, TicketData

from datetime import datetime
from typing import List, Dict
import logging
from models import DeviceData

def generate_analytics(device_data: List[DeviceData]) -> Dict[str, dict]:
    now = datetime.utcnow()
    analytics = {
        "counts": {
            "total_devices": len(device_data),
            "manufacturers": {},  # Dictionary to track device count per manufacturer
            "inactive_devices": 0,
            "no_antivirus": 0,
            "no_last_reboot": 0,
        },
        "integration_matches": {
            "full_matches": [],
            "partial_matches": [],
            "no_matches": []
        },
        "issues": {
            "no_antivirus_installed": [],
            "missing_defender_on_workstation": [],
            "missing_sentinel_one_on_server": [],
            "not_seen_recently": [],
            "reboot_required": [],
            "expired_warranty": []
        },
        "integrations": {key: 0 for key in [
            "Datto_RMM", "Huntress", "Workstation_AD", "Server_AD",
            "ImmyBot", "Auvik", "CyberCNS", "ITGlue"
        ]},
        "missing_integrations": {},
    }

    for device in device_data:
        device_name = device.device_name or "Unnamed Device"
        manufacturer = device.manufacturer_name

        if manufacturer and manufacturer != "N/A":
            analytics["counts"]["manufacturers"][manufacturer] = (
                analytics["counts"]["manufacturers"].get(manufacturer, 0) + 1
            )

        device_integrations = []
        missing_integrations = []

        for integration in [
            {"name": "Datto_RMM", "id_attr": "datto_id"},
            {"name": "Huntress", "id_attr": "huntress_id"},
            {"name": "Workstation_AD", "id_attr": "Workstation_AD"},
            {"name": "Server_AD", "id_attr": "Server_AD"},
            {"name": "ImmyBot", "id_attr": "immy_id"},
            {"name": "Auvik", "id_attr": "auvik_id"},
            {"name": "CyberCNS", "id_attr": "cybercns_id"},
            {"name": "ITGlue", "id_attr": "itglue_id"}
        ]:
            integration_name = integration["name"]

            if getattr(device, integration_name, False):
                analytics["integrations"][integration_name] += 1
                device_integrations.append(integration_name)
            else:
                missing_integrations.append(integration_name)

        if len(device_integrations) == len(analytics["integrations"]):
            analytics["integration_matches"]["full_matches"].append({
                "device_name": device_name,
                "matched_integrations": device_integrations
            })
        elif len(device_integrations) > 0:
            analytics["integration_matches"]["partial_matches"].append({
                "device_name": device_name,
                "matched_integrations": device_integrations
            })
        else:
            analytics["integration_matches"]["no_matches"].append({
                "device_name": device_name
            })

        analytics["missing_integrations"][device_name] = missing_integrations

        if device.Inactive_Computer:
            analytics["counts"]["inactive_devices"] += 1
            analytics["issues"]["not_seen_recently"].append({"device_name": device_name})

    return analytics




async def handle_mytickets(data: str) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post("http://127.0.0.1:8001/tickets", json={"data": data})
            response.raise_for_status()
            tickets_result = response.json()
            return {"response": f"Processed {len(tickets_result.get('tickets', []))} tickets"}
        except httpx.HTTPStatusError as e:
            return {"response": f"HTTP error: {e.response.status_code} - {str(e)}"}

def count_open_tickets(tickets: List[TicketData]) -> int:
    return sum(1 for ticket in tickets if ticket.status is not None and ticket.status != 5)
