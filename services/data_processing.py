from typing import List, Dict
from datetime import datetime
from models import DeviceData, TicketData


def count_open_tickets(tickets: List[TicketData]) -> int:
    """
    Counts the number of open tickets in a list of TicketData.

    Args:
        tickets (List[TicketData]): List of ticket data items.

    Returns:
        int: Count of open tickets.
    """
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
                "Auvik": 0
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
        }
    }

    # Analytics calculations
    for device in device_data:
        # Integration counts
        for integration in ["Datto_RMM", "Huntress", "Workstation_AD", "Server_AD", "ImmyBot", "Auvik"]:
            if getattr(device, integration, False):
                analytics["counts"]["integrations"][integration] += 1

        # Antivirus presence check based on device type
        if device.Workstation_AD:
            if device.antivirusProduct != "Microsoft Defender" or device.antivirusStatus != "RunningAndUpToDate":
                analytics["issues"]["missing_defender_on_workstation"].append(device.Name)
        elif device.Server_AD:
            if device.antivirusProduct != "Sentinel One" or device.antivirusStatus != "RunningAndUpToDate":
                analytics["issues"]["missing_sentinel_one_on_server"].append(device.Name)

        # Generic antivirus check for devices without expected antivirus products
        if not device.antivirusProduct or device.antivirusStatus != "RunningAndUpToDate":
            analytics["counts"]["no_antivirus"] += 1
            analytics["issues"]["no_antivirus_installed"].append(device.Name)

        # Last reboot check, ignoring inactive devices (rebootRequired = "N/A")
        if device.rebootRequired not in ["N/A", None]:
            analytics["issues"]["reboot_required"].append(device.Name)

        # Inactivity check
        if device.Inactive_Computer:
            analytics["counts"]["inactive_devices"] += 1
            analytics["trends"]["recently_inactive_devices"] += 1
            analytics["issues"]["not_seen_recently"].append(device.Name)
        else:
            analytics["trends"]["recently_active_devices"] += 1

        # Warranty check
        if device.warrantyDate != "N/A":
            try:
                warranty_date = datetime.strptime(device.warrantyDate, "%Y-%m-%d")
                if warranty_date < now:
                    analytics["issues"]["expired_warranty"].append(device.Name)
            except ValueError:
                pass  # Handle incorrect date formats if necessary

    return analytics
