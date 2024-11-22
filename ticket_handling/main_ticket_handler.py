import logging
from datetime import datetime, timezone
from typing import List
from zoneinfo import ZoneInfo
import httpx
from fastapi import HTTPException
from config import logger

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

            # Exclude tickets with specified queueIDs
            excluded_queue_ids = {29683506, 29683552, 29683546, 29683535}
            tickets = [
                ticket for ticket in tickets
                if ticket.get('queueID') not in excluded_queue_ids
            ]

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

        try:
            # Parse due_date_str
            if due_date_str:
                due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
                # Convert to CST regardless of current timezone
                due_date = due_date.astimezone(cst_tz)
            else:
                due_date = None

            # Parse met_date_str
            if met_date_str:
                met_date = datetime.fromisoformat(met_date_str.replace("Z", "+00:00"))
                # Convert to CST regardless of current timezone
                met_date = met_date.astimezone(cst_tz)
            else:
                met_date = None

            # Debug logging
            logging.debug(f"Parsed due_date (CST): {due_date}, tzinfo: {due_date.tzinfo if due_date else 'None'}")
            logging.debug(f"Parsed met_date (CST): {met_date}, tzinfo: {met_date.tzinfo if met_date else 'None'}")

        except ValueError as e:
            logging.error(f"Invalid datetime format: {e}")
            return None, None, None

        # SLA logic
        if due_date:
            if met_date:
                # SLA is met if `met_date` is on or before `due_date`
                sla_met = met_date <= due_date
            else:
                # SLA is not met if `due_date` is in the past and `met_date` is not available
                now = datetime.now(cst_tz)
                sla_met = now <= due_date
        else:
            # SLA cannot be calculated without a due_date
            logging.debug("Due date is None, skipping SLA calculation.")
            return None, None, None

        # Calculate time difference in seconds
        if met_date:
            time_diff_seconds = (due_date - met_date).total_seconds() if due_date else None
        else:
            time_diff_seconds = (due_date - datetime.now(cst_tz)).total_seconds() if due_date else None

        return sla_met, time_diff_seconds, due_date

    def calculate_weight(ticket):
        weight = 0

        # Priority Weighting
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

        # Status Weighting
        status_weights = {
            1: 50,  # New
            5: -10,  # Completed
            7: -20,  # Waiting Client
            11: 70,  # Escalated
            21: 60,  # Working issue now
            24: 65,  # Client Responded
            28: 55,  # Quote Needed
            29: 60,  # Reopened
            32: 0,   # Scheduled
            36: 65,  # Scheduling Needed
            41: -20, # Waiting Vendor
            54: 60,  # Needs Project
            56: 60,  # Received in Full
            64: -20, # Scheduled next NA
            70: 70,  # Assigned
            71: 70,  # schedule onsite
            74: -20,  # scheduled onsite
            38: -400  # Waiting on Hold
        }
        status = ticket.get("status")
        if status in status_weights:
            weight += status_weights[status]
        else:
            weight += 10  # Default weight

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
            logging.debug(f"SLA Field - {sla_name}: met_date={met_date_str}, due_date={due_date_str}")

            sla_met, time_diff_seconds, due_date = check_sla(met_date_str, due_date_str)

            if sla_met is not None:
                # Additional debug to verify SLA results
                logging.debug(
                    f"Appending SLA - {sla_name}: sla_met={sla_met}, due_date={due_date}, met_date={met_date_str}")

                due_date_formatted = due_date.strftime("%m-%d-%y %-I:%M %p %Z") if due_date else "N/A"
                met_date_formatted = (
                    datetime.fromisoformat(met_date_str.replace("Z", "+00:00"))
                    .astimezone(ZoneInfo("America/Chicago"))
                    .strftime("%m-%d-%y %-I:%M %p %Z")
                    if met_date_str and met_date_str.strip() != ''
                    else "Not completed"
                )

                # Append to SLA results
                sla_results.append({
                    "sla_name": sla_name,
                    "sla_met": sla_met,
                    "time_left_seconds": time_diff_seconds,
                    "due_date_formatted": due_date_formatted,
                    "met_date_formatted": met_date_formatted,
                    "due_date": due_date,
                })

                if not sla_met:
                    weight += 100  # Penalize for unmet SLA

        ticket["sla_results"] = sla_results

        # Age of Ticket Weighting
        create_date_str = ticket.get("createDate")
        if create_date_str:
            try:
                create_date = datetime.fromisoformat(create_date_str.replace("Z", "+00:00"))
                if create_date.tzinfo is None:
                    create_date = create_date.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                days_since_creation = (now_utc - create_date).days
                weight += days_since_creation * 10
                logger.debug(f"Ticket ID {ticket.get('id')} age: {days_since_creation} days")
            except ValueError:
                logger.error(f"Invalid createDate: {create_date_str}")

        return weight

    for ticket in tickets:
        ticket["weight"] = calculate_weight(ticket)

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
            74: "Scheduled Onsite",
            38: "Waiting on Hold"
        }
        return status_map.get(status_id, f"Status ID {status_id}")

    def format_timeline(ticket):
        timeline = []
        cst_tz = ZoneInfo('America/Chicago')
        sla_results = ticket.get("sla_results", [])

        for sla in sla_results:
            sla_name = sla["sla_name"]
            sla_met = sla["sla_met"]
            due_date = sla["due_date"]
            met_date = sla.get("met_date")  # May be None

            # Debug log for each SLA
            logging.debug(f"Formatting SLA - {sla_name}: sla_met={sla_met}, due_date={due_date}, met_date={met_date}")

            # Ensure dates are in CST
            due_date = due_date.astimezone(cst_tz) if due_date else None
            met_date = met_date.astimezone(cst_tz) if met_date else None

            # Determine SLA status and color
            now = datetime.now(cst_tz)
            if sla_met:
                sla_status_text = "Met"
                sla_status_color = "good"  # Green
            elif due_date and due_date > now:
                sla_status_text = "Not Yet Due"
                sla_status_color = "default"  # Blue
            else:
                sla_status_text = "Not Met"
                sla_status_color = "attention"  # Red

            # Time status
            time_left_seconds = sla["time_left_seconds"]
            time_status = (
                f"Time Left: {time_left_seconds / 3600:.2f} hours"
                if time_left_seconds and time_left_seconds >= 0
                else f"Overdue by: {-time_left_seconds / 3600:.2f} hours"
                if time_left_seconds
                else "N/A"
            )

            # Format dates for display
            due_date_formatted = due_date.strftime("%m-%d-%y %-I:%M %p %Z") if due_date else "N/A"
            met_date_formatted = met_date.strftime("%m-%d-%y %-I:%M %p %Z") if met_date else "Not completed"

            # Append to timeline
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
                    "url": f"https://ww15.autotask.net/Mvc/ServiceDesk/TicketDetail.mvc?workspace=False&ids%5B0%5D={ticket['id']}&ticketId={ticket['id']}",
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


