import logging
from datetime import datetime, timezone
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
    def check_sla(met_date_str, due_date_str):
        if not due_date_str or due_date_str.strip() == '':
            return None, None, None  # Return three None values
        try:
            due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
        except ValueError:
            logging.error(f"Invalid due_date_str: {due_date_str}")
            return None, None, None  # Return three None values
        if met_date_str and met_date_str.strip() != '':
            try:
                met_date = datetime.fromisoformat(met_date_str.replace("Z", "+00:00"))
            except ValueError:
                logging.error(f"Invalid met_date_str: {met_date_str}")
                return None, None, None  # Return three None values
            time_diff_seconds = (due_date - met_date).total_seconds()
            sla_met = met_date <= due_date
        else:
            now = datetime.now(timezone.utc)
            time_diff_seconds = (due_date - now).total_seconds()
            sla_met = now <= due_date
        return sla_met, time_diff_seconds, due_date

    def calculate_weight(ticket):
        weight = 0

        # Priority Weighting (Numeric keys)
        priority_weights = {5: 1, 3: 3, 2: 4, 1: 5, 4: 10}
        priority = ticket.get("priority")
        if priority in priority_weights:
            weight += priority_weights[priority]

        # Status Weighting (Numeric keys)
        status_weights = {
            1: 30,   # New
            70: 70,  # Assigned
            32: 10,  # Scheduled
            36: 36,  # Scheduling Needed
            50: 50   # Client Responded
        }
        status = ticket.get("status")
        if status in status_weights:
            weight += status_weights[status]

        # SLA Calculations
        sla_fields = [
            ("firstResponseDateTime", "firstResponseDueDateTime", "First Response"),
            ("resolutionPlanDateTime", "resolutionPlanDueDateTime", "Resolution Plan"),
            ("resolvedDateTime", "resolvedDueDateTime", "Resolution")
        ]

        sla_results = []
        for met_field, due_field, sla_name in sla_fields:
            met_date_str = ticket.get(met_field)
            due_date_str = ticket.get(due_field)

            logging.debug(f"Processing SLA '{sla_name}' with met_date_str={met_date_str}, due_date_str={due_date_str}")
            sla_met, time_diff_seconds, due_date = check_sla(met_date_str, due_date_str)
            logging.debug(f"check_sla returned: sla_met={sla_met}, time_diff_seconds={time_diff_seconds}, due_date={due_date}")

            if sla_met is not None:
                # Convert time difference to hours
                time_left_hours = time_diff_seconds / 3600  # Positive if time left, negative if overdue

                # Format dates as MM-DD-YY HH:MM
                due_date_formatted = due_date.strftime("%m-%d-%y %H:%M") if due_date else "N/A"
                if met_date_str and met_date_str.strip() != '':
                    met_date = datetime.fromisoformat(met_date_str.replace("Z", "+00:00"))
                    met_date_formatted = met_date.strftime("%m-%d-%y %H:%M")
                else:
                    met_date_formatted = "Not completed"

                # Store SLA results for display purposes
                sla_results.append({
                    "sla_name": sla_name,
                    "sla_met": sla_met,
                    "time_left_seconds": time_diff_seconds,
                    "due_date_formatted": due_date_formatted,
                    "met_date_formatted": met_date_formatted
                })

                if not sla_met:
                    # SLA was not met
                    weight += 100  # Adjust weight for SLA not met
                else:
                    if not met_date_str or met_date_str.strip() == '':
                        # Action not yet completed
                        if 0 <= time_left_hours <= 2:
                            # Coming due in next 2 hours
                            weight += 50
                    else:
                        # SLA was met and action completed
                        pass  # No additional weight adjustment

        # Store SLA results in the ticket for adaptive card display
        ticket["sla_results"] = sla_results

        return weight

    # Assign weights to tickets
    for ticket in tickets:
        logging.debug(f"Calculating weight for ticket ID {ticket.get('id')}")
        ticket["weight"] = calculate_weight(ticket)

    # Sort tickets by weight (descending) and return the top ticket
    sorted_tickets = sorted(tickets, key=lambda t: t["weight"], reverse=True)
    return sorted_tickets[:1]







def format_date(date_str):
    if date_str:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "")).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return "Invalid Date"
    return "N/A"

def construct_ticket_card(tickets: List[dict]) -> dict:
    def get_priority_color(priority):
        priority_map = {
            1: ("Critical", "attention"),  # Red
            2: ("High", "warning"),       # Orange
            3: ("Medium", "default"),     # Blue (default style)
            4: ("Low", "default"),        # Blue (default style)
            5: ("Very Low", "default")    # Blue (default style)
        }
        return priority_map.get(priority, ("Unknown", "default"))

    def get_due_date_color(due_date_str):
        if not due_date_str:
            return "default"

        now = datetime.now()
        due_date = datetime.fromisoformat(due_date_str.replace("Z", ""))
        delta = due_date - now

        if delta.total_seconds() <= 0:  # Missed
            return "attention"  # Red
        elif delta.total_seconds() <= 2 * 3600:  # < 2 hours
            return "warning"  # Yellow
        elif delta.total_seconds() > 2 * 3600:  # > 2 hours
            return "good"  # Green
        return "default"

    def format_timeline(ticket):
        timeline = []
        now = datetime.now()
        due_fields = {
            "First Response Due": ticket.get("firstResponseDueDateTime"),
            "Resolution Plan Due": ticket.get("resolutionPlanDueDateTime"),
            "Resolved Due": ticket.get("resolvedDueDateTime")
        }

        for label, due_date_str in due_fields.items():
            color = get_due_date_color(due_date_str)
            formatted_date = format_date(due_date_str)
            if due_date_str:
                due_date = datetime.fromisoformat(due_date_str.replace("Z", ""))
                status = "Missed" if due_date < now else "Upcoming"
            else:
                status = "N/A"
            timeline.append({
                "type": "Container",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"{label}: {formatted_date} ({status})",
                        "wrap": True,
                        "color": color,
                        "spacing": "Small"
                    }
                ],
                "spacing": "Small",
                "separator": True
            })

        return timeline

    body = []
    for ticket in tickets:
        priority_text, priority_color = get_priority_color(ticket.get("priority"))

        body.append({
            "type": "Container",
            "items": [
                {
                    "type": "TextBlock",
                    "text": f"Ticket ID: **{ticket['id']}**",
                    "wrap": True,
                    "weight": "bolder",
                    "spacing": "Small",
                    "color": "default"
                },
                {
                    "type": "TextBlock",
                    "text": f"Title: {ticket['title']}",
                    "wrap": True,
                    "spacing": "Small",
                    "color": "default"
                },
                {
                    "type": "TextBlock",
                    "text": f"Priority: {priority_text}",
                    "wrap": True,
                    "spacing": "Small",
                    "color": priority_color
                },
                {
                    "type": "TextBlock",
                    "text": f"Status: {ticket['status']}",
                    "wrap": True,
                    "spacing": "Small",
                    "color": "default"
                },
                {
                    "type": "TextBlock",
                    "text": f"Created Date: {format_date(ticket['createDate'])}",
                    "wrap": True,
                    "spacing": "Small",
                    "color": "default"
                },
                {
                    "type": "TextBlock",
                    "text": f"Weight: {ticket['weight']}",
                    "wrap": True,
                    "spacing": "Small",
                    "color": "default"
                },
                {
                    "type": "TextBlock",
                    "text": "Timeline:",
                    "weight": "bolder",
                    "wrap": True,
                    "spacing": "Medium",
                    "color": "default"
                },
                *format_timeline(ticket),
                {
                    "type": "ActionSet",
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "View Ticket",
                            "url": f"https://ww15.autotask.net/Mvc/ServiceDesk/TicketDetail.mvc?workspace=False&ids%5B0%5D={ticket['id']}&ticketId={ticket['id']}",
                            "style": "positive"
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





