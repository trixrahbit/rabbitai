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
        device_name = device.Name if device.Name != "N/A" else device.device_name or "Unknown Device"
        device_integrations = []
        missing_integrations = []
        integration_ids = {
            "Datto_RMM": device.datto_id if device.Datto_RMM else "N/A",
            "Huntress": device.huntress_id if device.Huntress else "N/A",
            "Workstation_AD": "N/A",
            "Server_AD": "N/A",
            "ImmyBot": device.immy_id if device.ImmyBot else "N/A",
            "Auvik": device.auvik_id if device.Auvik else "N/A",
            "ITGlue": device.itglue_id if device.ITGlue else "N/A"
        }

        for integration in ["Datto_RMM", "Huntress", "Workstation_AD", "Server_AD", "ImmyBot", "Auvik", "ITGlue"]:
            if getattr(device, integration, False):
                analytics["counts"]["integrations"][integration] += 1
                device_integrations.append(integration)
                if integration_ids[integration] == "N/A":
                    integration_ids[integration] = getattr(device, f"{integration.lower()}_id", "N/A")
                logger.debug(f"Counted {integration} for device: {device_name}")
            else:
                missing_integrations.append(integration)

        if not (device.Datto_RMM and device.ImmyBot):
            analytics["issues"]["missing_critical_integrations"].append({
                "device_name": device_name,
                "integration_ids": integration_ids
            })
            logger.debug(f"Device {device_name} is missing critical integrations.")

        os_type = device.OperatingSystem or "Unknown"
        analytics["counts"]["os_distribution"][os_type] = analytics["counts"]["os_distribution"].get(os_type, 0) + 1

        os_status = "supported"
        if "Windows Server 2016" in os_type or "Windows 10" in os_type:
            analytics["counts"]["end_of_support"] += 1
            os_status = "end_of_support"
        elif "Windows Server" in os_type and "2012" in os_type or "Windows 7" in os_type:
            analytics["counts"]["end_of_life"] += 1
            os_status = "end_of_life"
        elif "Windows 11" in os_type or "Windows Server 2019" in os_type or "Windows Server 2022" in os_type:
            analytics["counts"]["supported_os"] += 1

        if os_status in ["end_of_life", "end_of_support"]:
            analytics["issues"][os_status].append({
                "device_name": device_name,
                "os_type": os_type,
                "integration_ids": integration_ids
            })

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

            if not device.antivirusProduct or device.antivirusStatus != "RunningAndUpToDate":
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

    logger.debug(f"Final analytics counts: {analytics['counts']['integrations']}")
    return analytics
