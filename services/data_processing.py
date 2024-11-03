from typing import List, Dict
from datetime import datetime
from models import DeviceData, TicketData


def count_open_tickets(tickets: List[TicketData]) -> int:
    open_tickets = [ticket for ticket in tickets if ticket.status != 5]
    return len(open_tickets)


def generate_analytics(device_data: List[DeviceData]) -> Dict[str, dict]:
    now = datetime.utcnow()

    # Initialize analytics counters
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
                "ITGlue": 0,
                "Networking_Auvik_ITGlue": 0
            }
        },
        "issues": {
            "no_antivirus_installed": [],
            "missing_defender_on_workstation": [],
            "missing_sentinel_one_on_server": [],
            "not_seen_recently": [],
            "reboot_required": [],
            "expired_warranty": [],
            "unmatched_auvik_devices": [],
            "unmatched_itglue_devices": []
        },
        "trends": {
            "recently_active_devices": 0,
            "recently_inactive_devices": 0
        }
    }

    # Analytics calculations
    auvik_devices = [device for device in device_data if device.Auvik]
    itglue_devices = [device for device in device_data if device.ITGlue]

    for device in device_data:
        # Integration counts
        for integration in ["Datto_RMM", "Huntress", "Workstation_AD", "Server_AD", "ImmyBot", "Auvik", "ITGlue"]:
            if getattr(device, integration, False):
                analytics["counts"]["integrations"][integration] += 1

        # Antivirus presence check based on device type
        if device.Workstation_AD:
            if device.antivirusProduct != "Windows Defender Antivirus" or device.antivirusStatus != "RunningAndUpToDate":
                analytics["issues"]["missing_defender_on_workstation"].append(device.device_name)
        elif device.Server_AD:
            if device.antivirusProduct != "Sentinel Agent" or device.antivirusStatus != "RunningAndUpToDate":
                analytics["issues"]["missing_sentinel_one_on_server"].append(device.device_name)

        # Generic antivirus check
        if not device.antivirusProduct or device.antivirusStatus != "RunningAndUpToDate":
            analytics["counts"]["no_antivirus"] += 1
            analytics["issues"]["no_antivirus_installed"].append(device.device_name)

        # Last reboot check, ignoring inactive devices
        if device.rebootRequired not in ["N/A", None]:
            analytics["issues"]["reboot_required"].append(device.device_name)

        # Inactivity check
        if device.Inactive_Computer:
            analytics["counts"]["inactive_devices"] += 1
            analytics["trends"]["recently_inactive_devices"] += 1
            analytics["issues"]["not_seen_recently"].append(device.device_name)
        else:
            analytics["trends"]["recently_active_devices"] += 1

        # Warranty check
        if device.warrantyDate != "N/A":
            try:
                warranty_date = datetime.strptime(device.warrantyDate, "%Y-%m-%d")
                if warranty_date < now:
                    analytics["issues"]["expired_warranty"].append(device.device_name)
            except ValueError:
                pass

    # Match networking devices between Auvik and ITGlue
    auvik_device_names = {device.device_name for device in auvik_devices}
    itglue_device_names = {device.device_name for device in itglue_devices}

    matched_networking_devices = auvik_device_names.intersection(itglue_device_names)
    unmatched_auvik_devices = auvik_device_names - itglue_device_names
    unmatched_itglue_devices = itglue_device_names - auvik_device_names

    # Count and record unmatched devices
    analytics["counts"]["integrations"]["Networking_Auvik_ITGlue"] = len(matched_networking_devices)
    analytics["issues"]["unmatched_auvik_devices"].extend(unmatched_auvik_devices)
    analytics["issues"]["unmatched_itglue_devices"].extend(unmatched_itglue_devices)

    return analytics
