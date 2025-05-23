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

    logging.debug(f"[fetch_tickets_from_webhook] Requesting tickets for: {user_upn}")
    logging.debug(f"[fetch_tickets_from_webhook] Request payload: {payload}")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            logging.debug(f"[fetch_tickets_from_webhook] Response Status: {response.status_code}")
            logging.debug(f"[fetch_tickets_from_webhook] Response Body: {response.text}")

            data = response.json()

            # Ensure response contains 'my_ticket'
            if "my_ticket" not in data:
                logging.error(f"[fetch_tickets_from_webhook] Missing 'my_ticket' key in response.")
                logging.error(f"[fetch_tickets_from_webhook] Full Response: {data}")
                raise ValueError("Malformed response: Missing 'my_ticket' key.")

            tickets = data.get("my_ticket", [])
            if not isinstance(tickets, list):
                logging.error(f"[fetch_tickets_from_webhook] Expected 'my_ticket' to be a list but got {type(tickets)}")
                raise ValueError("Malformed response: 'my_ticket' is not a list.")

            logging.info(f"[fetch_tickets_from_webhook] Retrieved {len(tickets)} tickets before filtering.")

            # Exclude tickets with specified queueIDs
            excluded_queue_ids = {29683506, 29683552, 29683546, 29683535}
            filtered_tickets = [
                ticket for ticket in tickets if ticket.get("queueID") not in excluded_queue_ids
            ]

            logging.info(f"[fetch_tickets_from_webhook] {len(filtered_tickets)} tickets after filtering.")

            return filtered_tickets

    except httpx.HTTPStatusError as e:
        logging.error(f"[fetch_tickets_from_webhook] HTTP Error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=500, detail=f"Error fetching tickets: {e.response.text}")
    except ValueError as e:
        logging.error(f"[fetch_tickets_from_webhook] Invalid Webhook Response: {e}")
        raise HTTPException(status_code=500, detail="Malformed ticket response.")
    except Exception as e:
        logging.critical(f"[fetch_tickets_from_webhook] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected error fetching tickets.")



async def assign_ticket_weights(tickets: List[dict]) -> List[dict]:
    logging.info(f"[assign_ticket_weights] Processing {len(tickets)} tickets for weight assignment.")

    async def check_sla(met_date_str, due_date_str):
        cst_tz = ZoneInfo('America/Chicago')

        try:
            # Parse due_date_str
            due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00")).astimezone(cst_tz) if due_date_str else None
            met_date = datetime.fromisoformat(met_date_str.replace("Z", "+00:00")).astimezone(cst_tz) if met_date_str else None

            logging.debug(f"[check_sla] due_date: {due_date}, met_date: {met_date}")

        except ValueError as e:
            logging.error(f"[check_sla] Invalid datetime format: {e}")
            return False, None, "N/A", "Not completed"

        sla_met = False
        time_diff_seconds = None

        if due_date:
            if met_date:
                sla_met = met_date <= due_date
                time_diff_seconds = (due_date - met_date).total_seconds()
            else:
                sla_met = False
                now = datetime.now(cst_tz)
                time_diff_seconds = (due_date - now).total_seconds()
        else:
            logging.debug("[check_sla] Due date is None, returning N/A for SLA calculation.")
            return False, None, "N/A", "Not completed"

        return sla_met, time_diff_seconds, due_date.strftime("%m-%d-%y %-I:%M %p %Z") if due_date else "N/A", met_date.strftime("%m-%d-%y %-I:%M %p %Z") if met_date else "Not completed"

    async def calculate_weight(ticket):
        try:
            weight = 0
            ticket_id = ticket.get("id", "Unknown")
            logging.debug(f"[calculate_weight] Calculating weight for Ticket ID: {ticket_id}")

            priority = ticket.get("priority", "N/A")
            status = ticket.get("status", "N/A")

            priority_weights = {1: 5, 2: 4, 3: 3, 4: 2, 5: 1}
            status_weights = {1: 50, 5: -10, 7: -20, 11: 70, 21: 60, 24: 65, 28: 55, 29: 60, 32: 0, 36: 65, 41: -20, 54: 60, 56: 60, 64: -20, 70: 70, 71: 70, 74: -20, 38: -400}

            weight += priority_weights.get(priority, 0)
            weight += status_weights.get(status, 10)

            sla_fields = [("firstResponseDateTime", "firstResponseDueDateTime", "First Response"),
                          ("resolutionPlanDateTime", "resolutionPlanDueDateTime", "Resolution Plan"),
                          ("resolvedDateTime", "resolvedDueDateTime", "Resolution")]

            for met_field, due_field, sla_name in sla_fields:
                met_date_str = ticket.get(met_field)
                due_date_str = ticket.get(due_field)
                logging.debug(f"[calculate_weight] SLA Field {sla_name}: met_date={met_date_str}, due_date={due_date_str}")

                sla_met, time_diff_seconds, due_date_formatted, met_date_formatted = await check_sla(met_date_str, due_date_str)
                logging.debug(f"[calculate_weight] SLA {sla_name}: Met={sla_met}, Due={due_date_formatted}, Met={met_date_formatted}")

                if not sla_met:
                    weight += 100  # Penalize for unmet SLA

            create_date_str = ticket.get("createDate")
            if create_date_str:
                try:
                    create_date = datetime.fromisoformat(create_date_str.replace("Z", "+00:00"))
                    days_since_creation = (datetime.now(timezone.utc) - create_date).days
                    weight += days_since_creation * 10
                    logging.debug(f"[calculate_weight] Ticket {ticket_id} Age: {days_since_creation} days, Final Weight: {weight}")
                except ValueError:
                    logging.error(f"[calculate_weight] Invalid createDate format: {create_date_str}")

            return weight

        except Exception as e:
            logging.critical(f"[calculate_weight] Unexpected error for Ticket ID: {ticket_id} - {e}", exc_info=True)
            return 0  # Default weight in case of failure

    for ticket in tickets:
        ticket["weight"] = await calculate_weight(ticket)

    sorted_tickets = sorted(tickets, key=lambda t: t["weight"], reverse=True)
    logging.info(f"[assign_ticket_weights] Top Ticket ID: {sorted_tickets[0]['id']} Weight: {sorted_tickets[0]['weight']}")
    return sorted_tickets[:1]



async def format_date(date_str):
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


async def construct_ticket_card(tickets: List[dict]) -> dict:
    async def get_priority_info(priority):
        priority_map = {
            4: ("Critical", "attention"),  # Red
            1: ("High", "warning"),  # Yellow
            2: ("Medium", "default"),
            3: ("Low", "default"),
            5: ("Very Low", "default")
        }
        return priority_map.get(priority, ("Unknown", "default"))

    async def get_status_text(status_id):
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

    async def format_timeline(rawticket):
        """Format the timeline of SLAs"""
        timeline = []
        cst_tz = ZoneInfo('America/Chicago')
        sla_results = rawticket.get("sla_results", [])

        logging.debug(f"🛠️ SLA Results for Ticket ID {rawticket.get('id')}: {sla_results}")

        if not sla_results:
            logging.warning(f"⚠️ No SLA results found for Ticket ID {rawticket.get('id')}")
            return [{
                "type": "TextBlock",
                "text": "No SLA Information Available",
                "wrap": True,
                "weight": "Lighter",
                "spacing": "Small",
                "size": "Medium",
                "color": "attention"
            }]

        for sla in sla_results:
            sla_name = sla.get("sla_name", "Unknown SLA")
            sla_met = sla.get("sla_met", False)
            due_date_formatted = sla.get("due_date_formatted", "N/A")
            met_date_formatted = sla.get("met_date_formatted", "Not completed")
            time_left_seconds = sla.get("time_left_seconds", None)

            now = datetime.now(cst_tz)
            sla_status_text = "Not Met" if not sla_met else "Met"
            sla_status_color = "attention" if not sla_met else "good"

            if met_date_formatted == "Not completed" and due_date_formatted != "N/A":
                due_date = datetime.strptime(due_date_formatted, "%m-%d-%y %I:%M %p %Z").astimezone(cst_tz)
                if due_date > now:
                    sla_status_text = "Not Yet Due"
                    sla_status_color = "default"

            # Debugging logs
            logging.debug(
                f"📌 SLA: {sla_name} | Met: {sla_met} | Due: {due_date_formatted} | Met Date: {met_date_formatted} | Time Left: {time_left_seconds}")

            time_status = "N/A"
            if time_left_seconds is not None:
                if time_left_seconds >= 0:
                    time_status = f"Time Left: {time_left_seconds / 3600:.2f} hours"
                else:
                    time_status = f"Overdue by: {-time_left_seconds / 3600:.2f} hours"

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

    # Since we're only displaying one ticket, take the first one
    ticket = tickets[0]
    priority_text, priority_color = await get_priority_info(ticket.get("priority"))
    status_text = await get_status_text(ticket.get("status"))

    description = ticket.get("description", "")
    max_description_length = 200
    if len(description) > max_description_length:
        description = description[:max_description_length] + "..."

    timeline_items = await format_timeline(ticket)  # ✅ FIX: Await the async function

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
            "text": "**SLA Information:**",
            "wrap": True,
            "weight": "Bolder",
            "spacing": "Medium",
            "size": "Medium"
        },
        *timeline_items,  # ✅ FIX: `timeline_items` is now an iterable, not a coroutine
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

    adaptive_card = {
        "type": "AdaptiveCard",
        "version": "1.2",
        "body": body
    }

    return adaptive_card  # ✅ Now it correctly returns a JSON object

