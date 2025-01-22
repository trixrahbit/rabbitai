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
            "unique_manufacturers": set(),
            "unique_models": set(),
            "unique_serial_numbers": set(),
            "inactive_devices": 0,
            "no_antivirus": 0,
            "no_last_reboot": 0,
            "integrations": {key: 0 for key in [
                "Datto_RMM", "Huntress", "Workstation_AD", "Server_AD",
                "ImmyBot", "Auvik", "CyberCNS", "ITGlue"
            ]},
            "match_summary": {
                "full_matches": 0,
                "partial_matches": 0,
                "no_matches": 0
            }
        },
        "issues": {
            "no_antivirus_installed": [],
            "missing_defender_on_workstation": [],
            "missing_sentinel_one_on_server": [],
            "not_seen_recently": [],
            "reboot_required": [],
            "expired_warranty": []
        },
        "trends": {
            "recently_active_devices": 0,
            "recently_inactive_devices": 0
        },
        "integration_matches": [],
        "missing_integrations": {},
        "os_metrics": {
            "end_of_life": [],
            "end_of_support": [],
            "supported": [],
            "os_counts": {}
        }
    }

    for device in device_data:
        device_name = device.device_name or "Unnamed Device"
        manufacturer = device.manufacturer_name
        model = device.model_name
        serial_number = device.serial_number

        if manufacturer and manufacturer != "N/A":
            analytics["counts"]["unique_manufacturers"].add(manufacturer)
        if model and model != "N/A":
            analytics["counts"]["unique_models"].add(model)
        if serial_number and serial_number != "N/A":
            analytics["counts"]["unique_serial_numbers"].add(serial_number)

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
            integration_id = getattr(device, integration["id_attr"], None)

            if getattr(device, integration_name, False):
                analytics["counts"]["integrations"][integration_name] += 1
                device_integrations.append(integration_name)
            else:
                missing_integrations.append(integration_name)

        if device_integrations:
            analytics["integration_matches"].append({
                "device_name": device_name,
                "matched_integrations": device_integrations
            })

        analytics["missing_integrations"][device_name] = missing_integrations

        if device.Inactive_Computer:
            analytics["counts"]["inactive_devices"] += 1
            analytics["issues"]["not_seen_recently"].append({"device_name": device_name})

        if device.warrantyDate and device.warrantyDate != "N/A":
            try:
                warranty_date = datetime.strptime(device.warrantyDate, "%Y-%m-%d")
                if warranty_date < now:
                    analytics["issues"]["expired_warranty"].append({"device_name": device_name})
            except ValueError:
                logging.warning(f"Invalid warranty date format for {device_name}")

    analytics["counts"]["unique_manufacturers"] = list(analytics["counts"]["unique_manufacturers"])
    analytics["counts"]["unique_models"] = list(analytics["counts"]["unique_models"])
    analytics["counts"]["unique_serial_numbers"] = len(analytics["counts"]["unique_serial_numbers"])

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
