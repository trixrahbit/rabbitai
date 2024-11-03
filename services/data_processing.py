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
        "missing_integrations": {}
    }

    for device in device_data:
        # Ensure we get the correct device name from either Name or device_name
        device_name = device.Name if device.Name != "N/A" else device.device_name or "Unknown Device"
        device_integrations = []
        missing_integrations = []
        integration_ids = {}

        # Check each integration and update counts
        for integration in ["Datto_RMM", "Huntress", "Workstation_AD", "Server_AD", "ImmyBot", "Auvik", "ITGlue"]:
            if getattr(device, integration, False):
                analytics["counts"]["integrations"][integration] += 1
                device_integrations.append(integration)
                integration_ids[integration] = getattr(device, f"{integration.lower()}_id", "N/A")
                logger.debug(f"Counted {integration} for device: {device_name}")
            else:
                missing_integrations.append(integration)

        # Check if device has two or more integrations and add integration IDs
        if len(device_integrations) > 1:
            analytics["integration_matches"].append({
                "device_name": device_name,
                "matched_integrations": device_integrations,
                "integration_ids": {integration: integration_ids[integration] for integration in device_integrations}
            })
            logger.debug(f"Device {device_name} has multiple integrations: {device_integrations}")

        # Record missing integrations for the device along with IDs of present integrations
        if missing_integrations:
            analytics["missing_integrations"][device_name] = {
                "missing": missing_integrations,
                "integration_ids": integration_ids
            }
            logger.debug(f"Device {device_name} is missing integrations: {missing_integrations}")

        # Antivirus checks only if Datto_RMM is present
        if device.Datto_RMM:
            if device.Workstation_AD and (
                device.antivirusProduct != "Windows Defender Antivirus" or device.antivirusStatus != "RunningAndUpToDate"
            ):
                analytics["issues"]["missing_defender_on_workstation"].append({
                    "device_name": device_name,
                    "integration_ids": integration_ids
                })
                logger.debug(f"Missing Defender on workstation: {device_name}")

            elif device.Server_AD and (
                device.antivirusProduct != "Sentinel Agent" or device.antivirusStatus != "RunningAndUpToDate"
            ):
                analytics["issues"]["missing_sentinel_one_on_server"].append({
                    "device_name": device_name,
                    "integration_ids": integration_ids
                })
                logger.debug(f"Missing SentinelOne on server: {device_name}")

            # Generic antivirus check for Datto_RMM devices
            if not device.antivirusProduct or device.antivirusStatus != "RunningAndUpToDate":
                analytics["counts"]["no_antivirus"] += 1
                analytics["issues"]["no_antivirus_installed"].append({
                    "device_name": device_name,
                    "integration_ids": integration_ids
                })

        # Last reboot check
        if device.rebootRequired not in ["N/A", None]:
            analytics["issues"]["reboot_required"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })

        # Inactivity and warranty checks with integration IDs
        if device.Inactive_Computer:
            analytics["counts"]["inactive_devices"] += 1
            analytics["trends"]["recently_inactive_devices"] += 1
            analytics["issues"]["not_seen_recently"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })
        else:
            analytics["trends"]["recently_active_devices"] += 1

        # Warranty expiration check
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

    logger.debug(f"Final analytics counts: {analytics['counts']['integrations']}")
    return analytics
