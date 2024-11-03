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
        # Explicit check and log for each name attribute
        device_name = (
                getattr(device, 'Name', None) or
                getattr(device, 'device_name', None) or
                getattr(device, 'hostname', None) or
                "Unnamed Device"
        )

        logger.debug(f"Device attributes - Name: {getattr(device, 'Name', 'Not Found')}, "
                     f"device_name: {getattr(device, 'device_name', 'Not Found')}, "
                     f"hostname: {getattr(device, 'hostname', 'Not Found')}")

        logger.debug(f"Resolved device_name: {device_name}")

        if device_name == "Unnamed Device":
            logger.warning("Device name could not be determined from 'Name', 'device_name', or 'hostname'.")

        device_integrations = []
        missing_integrations = []
        integration_ids = {}

        integrations_list = ["Datto_RMM", "Huntress", "Workstation_AD", "Server_AD", "ImmyBot", "Auvik", "ITGlue"]

        for integration in integrations_list:
            integration_id_attr = f"{integration.lower()}_id"
            integration_ids[integration] = getattr(device, integration_id_attr, "N/A")

        for integration in integrations_list:
            integration_value = getattr(device, integration, None)

            is_integration_present = False
            if isinstance(integration_value, str):
                is_integration_present = integration_value.lower() == "yes"
            elif isinstance(integration_value, bool):
                is_integration_present = integration_value
            else:
                is_integration_present = bool(integration_value)

            if is_integration_present:
                analytics["counts"]["integrations"][integration] += 1
                device_integrations.append(integration)
                logger.debug(f"{integration} present for device: {device_name}")
            else:
                missing_integrations.append(integration)

        if len(device_integrations) > 1:
            analytics["integration_matches"].append({
                "device_name": device_name,
                "integration_ids": integration_ids,
                "matched_integrations": device_integrations
            })

        if missing_integrations:
            analytics["missing_integrations"][device_name] = missing_integrations

        # Antivirus checks
        if device.Datto_RMM and (
                device.antivirusProduct != "Windows Defender Antivirus" or device.antivirusStatus != "RunningAndUpToDate"):
            analytics["issues"]["missing_defender_on_workstation"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })
            logger.debug(f"Missing Defender on workstation: {device_name}")
        elif device.Server_AD and (
                device.antivirusProduct != "Sentinel Agent" or device.antivirusStatus != "RunningAndUpToDate"):
            analytics["issues"]["missing_sentinel_one_on_server"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })
            logger.debug(f"Missing SentinelOne on server: {device_name}")

        if device.Datto_RMM and (not device.antivirusProduct or device.antivirusStatus != "RunningAndUpToDate"):
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

        if device.Inactive_Computer:
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
                logger.warning(f"Invalid warranty date for device: {device_name}")

        # OS version check and metrics
        os_name = device.OperatingSystem or "Unknown OS"
        if os_name not in analytics["os_metrics"]["os_counts"]:
            analytics["os_metrics"]["os_counts"][os_name] = 0
        analytics["os_metrics"]["os_counts"][os_name] += 1

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
