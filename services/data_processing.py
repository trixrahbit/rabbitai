from typing import List, Dict
from models import TicketData
from datetime import datetime
from models import DeviceData


def count_open_tickets(tickets: List[TicketData]) -> int:
    """
    Counts the number of open tickets in a list of TicketData.

    Args:
        tickets (List[TicketData]): List of ticket data items.

    Returns:
        int: Count of open tickets.
    """
    # Assuming status 5 means closed
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

        # Antivirus check
        if not device.antivirusProduct or device.antivirusStatus != "RunningAndUpToDate":
            analytics["counts"]["no_antivirus"] += 1
            analytics["issues"]["no_antivirus_installed"].append(device.Name)

        # Last reboot check
        if device.lastReboot == "N/A":
            analytics["counts"]["no_last_reboot"] += 1
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
            warranty_date = datetime.strptime(device.warrantyDate, "%Y-%m-%d")
            if warranty_date < now:
                analytics["issues"]["expired_warranty"].append(device.Name)

    return analytics