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
            },
            "os_distribution": {},
            "end_of_life": 0,
            "end_of_support": 0,
            "supported_os": 0
        },
        "issues": {
            "no_antivirus_installed": [],
            "missing_defender_on_workstation": [],
            "missing_sentinel_one_on_server": [],
            "not_seen_recently": [],
            "reboot_required": [],
            "expired_warranty": [],
            "missing_critical_integrations": [],
            "end_of_life": [],
            "end_of_support": []
        },
        "trends": {
            "recently_active_devices": 0,
            "recently_inactive_devices": 0
        },
        "integration_matches": [],
        "missing_integrations": {}
    }

    for device in device_data:
        # Retrieve the device name with comprehensive fallback handling
        device_name = getattr(device, 'Name', None) or getattr(device, 'device_name', None) or "Unnamed Device"
        if device_name == "Unnamed Device":
            logger.warning(f"Device name missing for entry with ID(s): {device}")

        device_integrations = []
        missing_integrations = []
        integration_ids = {}

        for integration in ["Datto_RMM", "Huntress", "Workstation_AD", "Server_AD", "ImmyBot", "Auvik", "ITGlue"]:
            integration_id = getattr(device, f"{integration.lower()}_id", "N/A")
            integration_ids[integration] = integration_id

            integration_value = getattr(device, integration, None)

            # Determine if integration is present
            if isinstance(integration_value, str):
                is_integration_present = integration_value.lower() == "yes"
            else:
                is_integration_present = bool(integration_value)

            if is_integration_present:
                analytics["counts"]["integrations"][integration] += 1
                device_integrations.append(integration)
                logger.debug(f"{integration} found for device: {device_name}, ID: {integration_id}")
            else:
                missing_integrations.append(integration)

        # Append matched integrations if more than one integration exists
        if len(device_integrations) > 1:
            analytics["integration_matches"].append({
                "device_name": device_name,
                "matched_integrations": device_integrations,
                "integration_ids": {integration: integration_ids[integration] for integration in device_integrations}
            })
            logger.debug(f"Device {device_name} matched with multiple integrations: {device_integrations}")

        # Record missing integrations with explicit logging
        if missing_integrations:
            analytics["missing_integrations"][device_name] = {
                "missing": missing_integrations,
                "integration_ids": integration_ids
            }
            logger.debug(f"Device {device_name} missing integrations: {missing_integrations}")

        # Ensure critical integrations for Datto RMM and ImmyBot
        if not (getattr(device, 'Datto_RMM', False) and getattr(device, 'ImmyBot', False)):
            analytics["issues"]["missing_critical_integrations"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })

        # OS metrics and end-of-life/support checks
        os_type = getattr(device, 'OperatingSystem', "Unknown")
        analytics["counts"]["os_distribution"][os_type] = analytics["counts"]["os_distribution"].get(os_type, 0) + 1

        os_status = None
        if "Windows Server 2016" in os_type or "Windows 10" in os_type:
            analytics["counts"]["end_of_support"] += 1
            os_status = "end_of_support"
        elif "Windows Server 2012" in os_type or "Windows 7" in os_type:
            analytics["counts"]["end_of_life"] += 1
            os_status = "end_of_life"
        elif "Windows 11" in os_type or "Windows Server 2019" in os_type or "Windows Server 2022" in os_type:
            analytics["counts"]["supported_os"] += 1
            os_status = "supported"

        if os_status in ["end_of_life", "end_of_support"]:
            analytics["issues"][os_status].append({
                "device_name": device_name,
                "os_type": os_type,
                "integration_ids": integration_ids
            })

        # Antivirus checks only for devices with Datto RMM
        if getattr(device, 'Datto_RMM', False):
            antivirusProduct = getattr(device, 'antivirusProduct', "")
            antivirusStatus = getattr(device, 'antivirusStatus', "")
            workstation_ad_value = getattr(device, 'Workstation_AD', False)
            server_ad_value = getattr(device, 'Server_AD', False)

            if workstation_ad_value and (
                antivirusProduct != "Windows Defender Antivirus" or antivirusStatus != "RunningAndUpToDate"
            ):
                analytics["issues"]["missing_defender_on_workstation"].append({
                    "device_name": device_name,
                    "integration_ids": integration_ids
                })

            elif server_ad_value and (
                antivirusProduct != "Sentinel Agent" or antivirusStatus != "RunningAndUpToDate"
            ):
                analytics["issues"]["missing_sentinel_one_on_server"].append({
                    "device_name": device_name,
                    "integration_ids": integration_ids
                })

            if not antivirusProduct or antivirusStatus != "RunningAndUpToDate":
                analytics["counts"]["no_antivirus"] += 1
                analytics["issues"]["no_antivirus_installed"].append({
                    "device_name": device_name,
                    "integration_ids": integration_ids
                })

        # Last reboot check
        reboot_required = getattr(device, 'rebootRequired', None)
        if reboot_required and reboot_required != "N/A":
            analytics["issues"]["reboot_required"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })

        # Inactivity and warranty checks
        inactive_computer = getattr(device, 'Inactive_Computer', False)
        if inactive_computer:
            analytics["counts"]["inactive_devices"] += 1
            analytics["trends"]["recently_inactive_devices"] += 1
            analytics["issues"]["not_seen_recently"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })
        else:
            analytics["trends"]["recently_active_devices"] += 1

        # Warranty expiration check
        warrantyDate = getattr(device, 'warrantyDate', "N/A")
        if warrantyDate != "N/A":
            try:
                warranty_date = datetime.strptime(warrantyDate, "%Y-%m-%d")
                if warranty_date < now:
                    analytics["issues"]["expired_warranty"].append({
                        "device_name": device_name,
                        "integration_ids": integration_ids
                    })
            except ValueError:
                logger.warning(f"Invalid warranty date for device: {device_name}")

    logger.debug(f"Final analytics counts: {analytics['counts']['integrations']}")
    return analytics
