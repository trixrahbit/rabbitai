from typing import List, Dict
from datetime import datetime
from models import DeviceData, TicketData
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def count_open_tickets(tickets: List[TicketData]) -> int:
    open_tickets = [ticket for ticket in tickets if ticket.status != 5]
    return len(open_tickets)


def generate_analytics(device_data: List[DeviceData]) -> Dict[str, dict]:
    now = datetime.utcnow()
    analytics = {
        "counts": {
            "total_devices": len(device_data),
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
        # Set device name, handle "N/A" separately
        device_name = getattr(device, 'device_name', None)
        if not device_name or device_name == "N/A":
            device_name = "Unnamed Device"
            logger.warning(f"Device name is missing or 'N/A' for one of the devices.")

        logger.debug(f"Resolved device name: {device_name}")

        # Initialize integration IDs and flags
        integration_ids = {}
        device_integrations = []
        missing_integrations = []

        integrations_list = [
            {"name": "Datto_RMM", "id_attr": "datto_id"},
            {"name": "Huntress", "id_attr": "huntress_id"},
            {"name": "Workstation_AD", "id_attr": "workstation_ad_id"},
            {"name": "Server_AD", "id_attr": "server_ad_id"},
            {"name": "ImmyBot", "id_attr": "immy_id"},
            {"name": "Auvik", "id_attr": "auvik_id"},
            {"name": "ITGlue", "id_attr": "itglue_id"}
        ]

        # Process each integration, determining presence and setting the ID correctly
        for integration in integrations_list:
            integration_name = integration["name"]
            integration_id_attr = integration["id_attr"]
            integration_id = getattr(device, integration_id_attr, "N/A")

            # Determine if the integration is present based on "Yes"/"No" or boolean
            integration_value = getattr(device, integration_name, "No")
            if isinstance(integration_value, bool):
                is_integration_present = integration_value
            elif isinstance(integration_value, str):
                is_integration_present = integration_value.lower() == "yes"
            else:
                is_integration_present = bool(integration_value)

            # Only add to integration_ids if the integration is present and has a valid ID
            if is_integration_present and integration_id != "N/A":
                integration_ids[integration_name] = integration_id
                analytics["counts"]["integrations"][integration_name] += 1
                device_integrations.append(integration_name)
                logger.debug(f"{integration_name} is present for device: {device_name} with ID: {integration_id}")
            else:
                missing_integrations.append(integration_name)
                logger.debug(f"{integration_name} is not present for device: {device_name}; ID: {integration_id}")

        # Add to integration matches if any integrations were found
        if device_integrations:
            analytics["integration_matches"].append({
                "device_name": device_name,
                "integration_ids": integration_ids,
                "matched_integrations": device_integrations
            })

        if missing_integrations:
            analytics["missing_integrations"][device_name] = missing_integrations

        # Antivirus checks based on Datto_RMM or Server_AD
        if integration_ids.get("Datto_RMM") and device.antivirusProduct == "N/A":
            analytics["counts"]["no_antivirus"] += 1
            analytics["issues"]["no_antivirus_installed"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })
            logger.debug(f"Antivirus missing on device: {device_name}")

        if device.rebootRequired not in ["N/A", None]:
            analytics["issues"]["reboot_required"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })

        # Track inactive devices
        if device.Inactive_Computer == "Yes":
            analytics["counts"]["inactive_devices"] += 1
            analytics["trends"]["recently_inactive_devices"] += 1
            analytics["issues"]["not_seen_recently"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })
        else:
            analytics["trends"]["recently_active_devices"] += 1

        # Warranty checks
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

        # OS metrics
        os_name = device.OperatingSystem or "Unknown OS"
        if os_name not in analytics["os_metrics"]["os_counts"]:
            analytics["os_metrics"]["os_counts"][os_name] = 0
        analytics["os_metrics"]["os_counts"][os_name] += 1

        # Classify OS based on support status
        if os_name.lower().startswith("windows server") and "2016" not in os_name:
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

    logger.debug(f"Final analytics counts: {analytics['counts']['integrations']}")
    return analytics
