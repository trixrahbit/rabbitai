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
            logging.info(f"Webhook response: {data}")

            if not isinstance(data, list):
                raise ValueError("Webhook response is not a list of tickets.")
            if not all(isinstance(ticket, dict) for ticket in data):
                raise ValueError("Each ticket in the response must be a dictionary.")

            return data
    except httpx.HTTPStatusError as e:
        logging.error(f"Failed to fetch tickets from webhook: {e.response.text}")
        raise HTTPException(status_code=500, detail="Error fetching tickets.")
    except ValueError as e:
        logging.error(f"Invalid webhook response format: {e}")
        raise HTTPException(status_code=500, detail="Malformed ticket response.")


def assign_ticket_weights(tickets: List[dict]) -> List[dict]:
    def calculate_weight(ticket):
        weight = 0
        try:
            priority = ticket.get("priority", 3)  # Default to low priority if missing
            if priority == 1:  # High priority
                weight += 50
            elif priority == 2:  # Medium priority
                weight += 30

            if not ticket.get("sla_met", True):  # Default SLA met to True if missing
                weight += 20

            created_date_str = ticket.get("created_date")
            if created_date_str:
                created_date = datetime.fromisoformat(created_date_str)
                ticket_age = (datetime.now() - created_date).days
                weight += ticket_age
        except Exception as e:
            logging.error(f"Error calculating weight for ticket {ticket}: {e}")
            weight = -1  # Assign a low weight if there's an error
        return weight

    # Assign weight to each ticket
    for ticket in tickets:
        ticket["weight"] = calculate_weight(ticket)

    # Filter out tickets with invalid weights
    valid_tickets = [t for t in tickets if t["weight"] >= 0]

    # Sort tickets by weight (descending)
    sorted_tickets = sorted(valid_tickets, key=lambda t: t["weight"], reverse=True)
    return sorted_tickets[:5]  # Return top 5 tickets



def construct_ticket_card(tickets: List[dict]) -> dict:
    body = []
    actions = []
    for ticket in tickets:
        try:
            body.append({
                "type": "TextBlock",
                "text": f"**Ticket ID**: {ticket.get('id', 'N/A')}\n"
                        f"**Title**: {ticket.get('title', 'N/A')}\n"
                        f"**Priority**: {ticket.get('priority', 'N/A')}\n"
                        f"**Created Date**: {ticket.get('created_date', 'N/A')}\n"
                        f"**Weight**: {ticket.get('weight', 'N/A')}",
                "wrap": True
            })
            actions.append({
                "type": "Action.OpenUrl",
                "title": f"View Ticket {ticket.get('id', 'N/A')}",
                "url": f"https://ww15.autotask.net/Mvc/ServiceDesk/TicketDetail.mvc?"
                       f"workspace=False&ids%5B0%5D={ticket.get('id', '')}&ticketId={ticket.get('id', '')}"
            })
        except Exception as e:
            logging.error(f"Error constructing card for ticket: {e}")

    return {
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": body,
        "actions": actions
    }
