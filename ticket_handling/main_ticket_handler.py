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
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()  # Assume it returns a list of ticket objects
    except httpx.HTTPStatusError as e:
        logging.error(f"Failed to fetch tickets from webhook: {e.response.text}")
        raise HTTPException(status_code=500, detail="Error fetching tickets.")

def assign_ticket_weights(tickets: List[dict]) -> List[dict]:
    def calculate_weight(ticket):
        weight = 0
        # Example weights (customize as needed)
        if ticket.get("priority") == 1:  # High priority
            weight += 50
        elif ticket.get("priority") == 2:  # Medium priority
            weight += 30

        if not ticket.get("sla_met"):  # SLA not met
            weight += 20

        # Age of the ticket (older tickets get higher weight)
        created_date = datetime.fromisoformat(ticket.get("created_date"))
        ticket_age = (datetime.now() - created_date).days
        weight += ticket_age

        return weight

    # Assign weight to each ticket
    for ticket in tickets:
        ticket["weight"] = calculate_weight(ticket)

    # Sort tickets by weight (descending)
    sorted_tickets = sorted(tickets, key=lambda t: t["weight"], reverse=True)
    return sorted_tickets[:5]  # Return top 5 tickets


def construct_ticket_card(tickets: List[dict]) -> dict:
    body = []
    actions = []
    for ticket in tickets:
        body.append({
            "type": "TextBlock",
            "text": f"**Ticket ID**: {ticket['id']}\n"
                    f"**Title**: {ticket['title']}\n"
                    f"**Priority**: {ticket['priority']}\n"
                    f"**Created Date**: {ticket['created_date']}\n"
                    f"**Weight**: {ticket['weight']}",
            "wrap": True
        })
        actions.append({
            "type": "Action.OpenUrl",
            "title": f"View Ticket {ticket['id']}",
            "url": f"https://ww15.autotask.net/Mvc/ServiceDesk/TicketDetail.mvc?workspace=False&ids%5B0%5D={ticket['id']}&ticketId={ticket['id']}"
        })

    return {
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": body,
        "actions": actions
    }

