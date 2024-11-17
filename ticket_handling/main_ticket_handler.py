import logging
from datetime import datetime
from typing import List

import httpx
from fastapi import HTTPException

async def fetch_tickets_from_webhook(user_upn: str) -> List[dict]:
    url = "https://engine.rewst.io/webhooks/custom/trigger/01933846-ecca-7a63-a943-f09e358edcc3/018e6633-49b0-7f54-b610-e740d3bb1a3e"
    payload = {"user_upn": user_upn}
    headers = {"Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Extract the list of tickets from the nested format
            tickets = data.get("my_ticket", [])
            if not isinstance(tickets, list):
                raise ValueError("Malformed response: 'my_ticket' is not a list.")

            return tickets
    except httpx.HTTPStatusError as e:
        logging.error(f"Failed to fetch tickets from webhook: {e.response.text}")
        raise HTTPException(status_code=500, detail="Error fetching tickets.")
    except ValueError as e:
        logging.error(f"Invalid webhook response format: {e}")
        raise HTTPException(status_code=500, detail="Malformed ticket response.")


def assign_ticket_weights(tickets: List[dict]) -> List[dict]:
    def calculate_weight(ticket):
        weight = 0

        # Priority Weighting (Numeric keys)
        priority_weights = {5: 1, 3: 3, 2: 4, 1: 5, 4: 2}  # Updated to match numeric priorities
        priority = ticket.get("priority")
        if priority in priority_weights:
            weight += priority_weights[priority]

        # Status Weighting (Numeric keys)
        status_weights = {
            1: 1,   # New
            70: 70,  # Assigned
            32: 32,  # Scheduled
            36: 36,  # Scheduling Needed
            50: 50   # Client Responded
        }
        status = ticket.get("status")
        if status in status_weights:
            weight += status_weights[status]

        # Due Dates Weighting
        now = datetime.now()
        due_date_fields = [
            "firstResponseDueDateTime",
            "resolutionPlanDueDateTime",
            "resolvedDueDateTime"
        ]
        for field in due_date_fields:
            due_date_str = ticket.get(field)
            if due_date_str:
                due_date = datetime.fromisoformat(due_date_str.replace("Z", ""))
                hours_until_due = (due_date - now).total_seconds() / 3600
                if 0 <= hours_until_due <= 2:  # Coming due in the next 2 hours
                    weight += 50

        return weight

    # Assign weights to tickets
    for ticket in tickets:
        ticket["weight"] = calculate_weight(ticket)

    # Sort tickets by weight (descending) and return the top 5
    sorted_tickets = sorted(tickets, key=lambda t: t["weight"], reverse=True)
    return sorted_tickets[:5]




from datetime import datetime
from typing import List

def format_date(date_str):
    if date_str:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "")).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return "Invalid Date"
    return "N/A"

def construct_ticket_card(tickets: List[dict]) -> dict:
    body = []
    for ticket in tickets:
        body.append({
            "type": "Container",
            "items": [
                {
                    "type": "TextBlock",
                    "text": (
                        f"**Ticket ID**: {ticket['id']}\n\n"
                        f"**Title**: {ticket['title']}\n\n"
                        f"**Priority**: {ticket['priority']}\n\n"
                        f"**Status**: {ticket['status']}\n\n"
                        f"**Created Date**: {format_date(ticket['createDate'])}\n\n"
                        f"**First Response Due**: {format_date(ticket['firstResponseDueDateTime'])}\n\n"
                        f"**Resolution Plan Due**: {format_date(ticket['resolutionPlanDueDateTime'])}\n\n"
                        f"**Resolved Due**: {format_date(ticket['resolvedDueDateTime'])}\n\n"
                        f"**Weight**: {ticket['weight']}"
                    ),
                    "wrap": True,
                    "spacing": "Medium"
                },
                {
                    "type": "ActionSet",
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "View Ticket",
                            "url": f"https://ww15.autotask.net/Mvc/ServiceDesk/TicketDetail.mvc?workspace=False&ids%5B0%5D={ticket['id']}&ticketId={ticket['id']}"
                        }
                    ]
                }
            ],
            "spacing": "Large",
            "separator": True
        })

    return {
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": body
    }


