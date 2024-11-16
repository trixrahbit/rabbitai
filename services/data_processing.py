import logging
from typing import List, Dict
from datetime import datetime
from collections import defaultdict

import httpx
from fastapi import HTTPException

from config import logger, APP_SECRET
from models import DeviceData, TicketData


def count_open_tickets(tickets: List[TicketData]) -> int:
    open_tickets = [ticket for ticket in tickets if ticket.status != 5]
    return len(open_tickets)

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
            "integrations": {
                "Datto_RMM": 0,
                "Huntress": 0,
                "Workstation_AD": 0,
                "Server_AD": 0,
                "ImmyBot": 0,
                "Auvik": 0,
                "ITGlue": 0
            },
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

    older_os_versions = [
        "Windows 7", "Windows 8", "Windows 8.1", "Windows Vista",
        "Windows XP", "Windows Server 2008", "Windows Server 2008 R2",
        "Windows Server 2012", "Windows Server 2012 R2"
    ]

    for device in device_data:
        device_name = getattr(device, 'device_name', None)
        if not device_name or device_name == "N/A":
            device_name = "Unnamed Device"
            logger.warning(f"Device name is missing or 'N/A' for one of the devices.")

        logger.debug(f"Resolved device name: {device_name}")

        # Retrieve manufacturer, model, and serial number without default values to debug data availability
        manufacturer = getattr(device, "manufacturer_name", None)
        model = getattr(device, "model_name", None)
        serial_number = getattr(device, "serial_number", None)

        # Log retrieved values for debugging
        logger.debug(f"Device {device_name} - Manufacturer: {manufacturer}, Model: {model}, Serial: {serial_number}")

        # Only update if values are valid
        if manufacturer and manufacturer != "N/A":
            analytics["counts"]["unique_manufacturers"].add(manufacturer)
        if model and model != "N/A":
            analytics["counts"]["unique_models"].add(model)
        if serial_number and serial_number != "N/A":
            analytics["counts"]["unique_serial_numbers"].add(serial_number)

        integration_ids = {}
        device_integrations = []
        missing_integrations = []

        # Determine device type for integration validation
        is_server = getattr(device, "Server_AD", False)
        is_workstation = getattr(device, "Workstation_AD", False)

        integrations_list = [
            {"name": "Datto_RMM", "id_attr": "datto_id"},
            {"name": "Huntress", "id_attr": "huntress_id"},
            {"name": "Workstation_AD", "id_attr": "workstation_ad_id"},
            {"name": "Server_AD", "id_attr": "server_ad_id"},
            {"name": "ImmyBot", "id_attr": "immy_id"},
            {"name": "Auvik", "id_attr": "auvik_id"},
            {"name": "ITGlue", "id_attr": "itglue_id"}
        ]

        for integration in integrations_list:
            integration_name = integration["name"]
            integration_id_attr = integration["id_attr"]
            integration_id = getattr(device, integration_id_attr, "N/A")

            integration_value = getattr(device, integration_name, "No")
            is_integration_present = integration_value == "Yes" if isinstance(integration_value, str) else bool(integration_value)

            # Apply filtering logic for incompatible integrations
            if (integration_name == "Workstation_AD" and is_server) or (integration_name == "Server_AD" and is_workstation):
                continue  # Skip incompatible integration for device type

            if is_integration_present:
                if integration_id != "N/A":
                    integration_ids[integration_name] = integration_id
                analytics["counts"]["integrations"][integration_name] += 1
                device_integrations.append(integration_name)
                logger.debug(f"{integration_name} is present for device: {device_name} with ID: {integration_id}")
            else:
                missing_integrations.append(integration_name)
                logger.debug(f"{integration_name} is not present for device: {device_name}; ID: {integration_id}")

        match_count = len(device_integrations)
        if match_count == len(integrations_list):
            analytics["counts"]["match_summary"]["full_matches"] += 1
            analytics["integration_matches"].append({
                "device_name": device_name,
                "integration_ids": integration_ids,
                "matched_integrations": device_integrations
            })
        elif match_count >= 2:
            analytics["counts"]["match_summary"]["partial_matches"] += 1
            analytics["integration_matches"].append({
                "device_name": device_name,
                "integration_ids": integration_ids,
                "matched_integrations": device_integrations
            })
        else:
            analytics["counts"]["match_summary"]["no_matches"] += 1
            analytics["missing_integrations"][device_name] = missing_integrations

        if integration_ids.get("Datto_RMM") and device.antivirusProduct == "N/A":
            analytics["counts"]["no_antivirus"] += 1
            analytics["issues"]["no_antivirus_installed"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })

        if device.rebootRequired not in ["N/A", None]:
            analytics["issues"]["reboot_required"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })

        if device.Inactive_Computer == "Yes":
            analytics["counts"]["inactive_devices"] += 1
            analytics["trends"]["recently_inactive_devices"] += 1
            analytics["issues"]["not_seen_recently"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })
        else:
            analytics["trends"]["recently_active_devices"] += 1

        if device.warrantyDate != "N/A":
            try:
                warranty_date = datetime.strptime(device.warrantyDate, "%Y-%m-%d")
                if warranty_date < now:
                    analytics["issues"]["expired_warranty"].append({
                        "device_name": device_name,
                        "integration_ids": integration_ids
                    })
            except ValueError:
                logger.warning(f"Invalid warranty date format for device: {device_name}")

        os_name = device.OperatingSystem or "Unknown OS"
        if os_name not in analytics["os_metrics"]["os_counts"]:
            analytics["os_metrics"]["os_counts"][os_name] = 0
        analytics["os_metrics"]["os_counts"][os_name] += 1

        if os_name in older_os_versions:
            analytics["os_metrics"]["end_of_life"].append({
                "device_name": device_name,
                "integration_ids": integration_ids,
                "os": os_name
            })
        elif os_name.lower() in ["windows 10", "windows server 2016"]:
            analytics["os_metrics"]["end_of_support"].append({
                "device_name": device_name,
                "integration_ids": integration_ids,
                "os": os_name
            })
        else:
            analytics["os_metrics"]["supported"].append({
                "device_name": device_name,
                "integration_ids": integration_ids,
                "os": os_name
            })

    analytics["counts"]["unique_manufacturers"] = list(analytics["counts"]["unique_manufacturers"])
    analytics["counts"]["unique_models"] = list(analytics["counts"]["unique_models"])
    analytics["counts"]["unique_serial_numbers"] = len(analytics["counts"]["unique_serial_numbers"])

    logger.debug(f"Final analytics counts: {analytics['counts']['integrations']}")
    return analytics


async def handle_mytickets(data: str) -> dict:
    """
    Fetches tickets from an endpoint, processes the result, and returns it.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "http://127.0.0.1:8001/tickets",  # Replace with actual tickets endpoint
                json={"data": data},
            )
            response.raise_for_status()
            tickets_result = response.json()

            # Placeholder processing logic
            processed_result = f"Processed {len(tickets_result.get('tickets', []))} tickets"

            return {"response": f"Tickets processed: {processed_result}"}
        except httpx.RequestError as e:
            return {"response": f"Error communicating with tickets endpoint: {str(e)}"}