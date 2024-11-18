import logging
from datetime import datetime, timezone
from typing import List
from zoneinfo import ZoneInfo

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
        cst_tz = ZoneInfo('America/Chicago')

        if not due_date_str or due_date_str.strip() == '':
            return None, None, None  # Return three None values
        try:
            # Parse due_date_str as UTC datetime
            due_date_utc = datetime.fromisoformat(due_date_str.replace("Z", "+00:00")).astimezone(timezone.utc)
            # Convert to CST
            due_date = due_date_utc.astimezone(cst_tz)
        except ValueError:
            logging.error(f"Invalid due_date_str: {due_date_str}")
            return None, None, None  # Return three None values

        if met_date_str and met_date_str.strip() != '':
            try:
                # Parse met_date_str as UTC datetime
                met_date_utc = datetime.fromisoformat(met_date_str.replace("Z", "+00:00")).astimezone(timezone.utc)
                # Convert to CST
                met_date = met_date_utc.astimezone(cst_tz)
            except ValueError:
                logging.error(f"Invalid met_date_str: {met_date_str}")
                return None, None, None  # Return three None values
            time_diff_seconds = (due_date - met_date).total_seconds()
            sla_met = met_date <= due_date
        else:
            now = datetime.now(cst_tz)
            time_diff_seconds = (due_date - now).total_seconds()
            sla_met = now <= due_date

        return sla_met, time_diff_seconds, due_date

    def calculate_weight(ticket):
        weight = 0

        # Priority Weighting (Numeric keys)
        priority_weights = {
            1: 5,  # Critical
            2: 4,  # High
            3: 3,  # Medium
            4: 2,  # Low
            5: 1   # Very Low
        }
        priority = ticket.get("priority")
        if priority in priority_weights:
            weight += priority_weights[priority]

        # Status Weighting (Updated based on provided statuses)
        status_weights = {
            1: 50,   # New
            5: -10,  # Completed
            7: -20,  # Waiting Client
            11: 70,  # Escalated
            21: 60,  # Working issue now
            24: 65,  # Client Responded
            28: 55,  # Quote Needed
            29: 60,  # Reopened
            32: 45,  # Scheduled
            36: 65,  # Scheduling Needed
            41: -20, # Waiting Vendor
            54: 60,  # Needs Project
            56: 60,  # Received in Full
            64: 55,  # Scheduled next NA
            70: 70,  # Assigned
            71: 70,  # schedule onsite
            74: 70   # scheduled onsite
        }
        status = ticket.get("status")
        if status in status_weights:
            weight += status_weights[status]
        else:
            # Assign a default weight for statuses not listed
            weight += 10  # Adjust as needed

        # SLA Calculations (Existing code)
        sla_fields = [
            ("firstResponseDateTime", "firstResponseDueDateTime", "First Response"),
            ("resolutionPlanDateTime", "resolutionPlanDueDateTime", "Resolution Plan"),
            ("resolvedDateTime", "resolvedDueDateTime", "Resolution")
        ]

        sla_results = []
        for met_field, due_field, sla_name in sla_fields:
            met_date_str = ticket.get(met_field)
            due_date_str = ticket.get(due_field)

            sla_met, time_diff_seconds, due_date = check_sla(met_date_str, due_date_str)

            if sla_met is not None:
                # Convert time difference to hours
                time_left_hours = time_diff_seconds / 3600  # Positive if time left, negative if overdue

                # Format dates as MM-DD-YY HH:MM in CST
                due_date_formatted = due_date.strftime("%m-%d-%y %-I:%M %p %Z") if due_date else "N/A"
                if met_date_str and met_date_str.strip() != '':
                    met_date_utc = datetime.fromisoformat(met_date_str.replace("Z", "+00:00")).astimezone(timezone.utc)
                    met_date = met_date_utc.astimezone(ZoneInfo('America/Chicago'))
                    met_date_formatted = met_date.strftime("%m-%d-%y %-I:%M %p %Z")
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

    # Sort tickets by weight (descending) and return the top tickets
    sorted_tickets = sorted(tickets, key=lambda t: t["weight"], reverse=True)
    return sorted_tickets[:1]  # Adjust the number as needed

    # Assign weights to tickets
    for ticket in tickets:
        logging.debug(f"Calculating weight for ticket ID {ticket.get('id')}")
        ticket["weight"] = calculate_weight(ticket)

    # Sort tickets by weight (descending) and return the top ticket
    sorted_tickets = sorted(tickets, key=lambda t: t["weight"], reverse=True)
    return sorted_tickets[:1]


def format_date(date_str):
    cst_tz = ZoneInfo('America/Chicago')
    if date_str:
        try:
            date_utc = datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(timezone.utc)
            date_cst = date_utc.astimezone(cst_tz)
            # Updated format string
            return date_cst.strftime("%m-%d-%y %-I:%M %p %Z")
        except ValueError:
            return "Invalid Date"
    return "N/A"



def construct_ticket_card(tickets: List[dict]) -> dict:
    def get_priority_info(priority):
        priority_map = {
            1: ("Critical", "attention"),  # Red
            2: ("High", "warning"),        # Yellow
            3: ("Medium", "default"),      # Default color
            4: ("Low", "default"),         # Default color
            5: ("Very Low", "default")     # Default color
        }
        return priority_map.get(priority, ("Unknown", "default"))

    def get_status_text(status_id):
        status_map = {
            1: "New",
            5: "Completed",
            7: "Waiting Client",
            11: "Escalated",
            21: "Working Issue Now",
            24: "Client Responded",
            28: "Quote Needed",
            29: "Reopened",
            32: "Scheduled",
            36: "Scheduling Needed",
            41: "Waiting Vendor",
            54: "Needs Project",
            56: "Received in Full",
            64: "Scheduled Next NA",
            70: "Assigned",
            71: "Schedule Onsite",
            74: "Scheduled Onsite"
        }
        return status_map.get(status_id, f"Status ID {status_id}")

    def format_timeline(ticket):
        timeline = []
        cst_tz = ZoneInfo('America/Chicago')
        sla_results = ticket.get("sla_results", [])

        for sla in sla_results:
            sla_name = sla["sla_name"]
            sla_met = sla["sla_met"]
            time_left_seconds = sla["time_left_seconds"]
            due_date_formatted = sla["due_date_formatted"]
            met_date_formatted = sla["met_date_formatted"]

            # Determine SLA status and color
            if sla_met:
                sla_status_text = "Met"
                sla_status_color = "good"  # Green
            else:
                now = datetime.now(ZoneInfo('America/Chicago'))
                due_date = datetime.strptime(due_date_formatted, "%m-%d-%y %I:%M %p %Z")
                if due_date > now:
                    sla_status_text = "Not Yet Due"
                    sla_status_color = "default"  # Blue (default)
                else:
                    sla_status_text = "Not Met"
                    sla_status_color = "attention"  # Red

            # Time status
            if time_left_seconds is not None:
                if time_left_seconds >= 0:
                    time_status = f"Time Left: {time_left_seconds / 3600:.2f} hours"
                else:
                    time_status = f"Overdue by: {-time_left_seconds / 3600:.2f} hours"
            else:
                time_status = "N/A"

            timeline.append({
                "type": "Container",
                "spacing": "Small",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"**{sla_name} SLA**",
                        "weight": "Bolder",
                        "wrap": True,
                        "color": sla_status_color
                    },
                    {
                        "type": "FactSet",
                        "facts": [
                            {"title": "Status:", "value": sla_status_text},
                            {"title": "Due Date:", "value": due_date_formatted},
                            {"title": "Met Date:", "value": met_date_formatted},
                            {"title": "Time Status:", "value": time_status}
                        ]
                    }
                ]
            })

        return timeline

    # Since we're only displaying one ticket, we take the first one
    ticket = tickets[0]
    priority_text, priority_color = get_priority_info(ticket.get("priority"))
    status_text = get_status_text(ticket.get("status"))

    # Truncate description if it's too long
    description = ticket.get("description", "")
    max_description_length = 200  # Adjust as needed
    if len(description) > max_description_length:
        description = description[:max_description_length] + "..."

    body = [
        {
            "type": "TextBlock",
            "text": f"**Ticket ID:** {ticket['id']}",
            "wrap": True,
            "weight": "Bolder",
            "size": "Medium",
            "spacing": "Medium"
        },
        {
            "type": "TextBlock",
            "text": f"**Title:** {ticket['title']}",
            "wrap": True,
            "weight": "Bolder",
            "spacing": "Small"
        },
        {
            "type": "TextBlock",
            "text": f"**Description:** {description}",
            "wrap": True,
            "spacing": "Small"
        },
        {
            "type": "TextBlock",
            "text": f"**Priority:** {priority_text}",
            "wrap": True,
            "color": priority_color,
            "spacing": "Small",
            "weight": "Bolder"
        },
        {
            "type": "TextBlock",
            "text": f"**Status:** {status_text}",
            "wrap": True,
            "spacing": "Small",
            "weight": "Bolder"
        },
        {
            "type": "TextBlock",
            "text": f"**Created Date:** {format_date(ticket['createDate'])}",
            "wrap": True,
            "spacing": "Small"
        },
        {
            "type": "TextBlock",
            "text": "**SLA Information:**",
            "wrap": True,
            "weight": "Bolder",
            "spacing": "Medium",
            "size": "Medium"
        },
        *format_timeline(ticket),
        {
            "type": "ActionSet",
            "spacing": "Medium",
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "View Ticket",
                    "url": f"https://your-ticket-system.com/tickets/{ticket['id']}",
                    "style": "positive"
                }
            ]
        }
    ]

    # Final adaptive card
    adaptive_card = {
        "type": "AdaptiveCard",
        "version": "1.2",
        "body": body
    }

    return adaptive_card


