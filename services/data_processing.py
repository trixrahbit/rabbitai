from typing import List
from models import TicketData


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
