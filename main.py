import json
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Request

from models import DeviceData
from security.auth import get_api_key
import logging
from starlette.middleware.base import BaseHTTPMiddleware

from services.data_processing import generate_analytics


# Define the Middleware Class
class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_size: int):
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_body_size:
            raise HTTPException(status_code=413, detail="Request body too large")
        return await call_next(request)


app = FastAPI()
logging.basicConfig(filename="/var/www/rabbitai/webhook.log", level=logging.INFO)
app.add_middleware(MaxBodySizeMiddleware, max_body_size=900_000_000)  # 100 MB

@app.post("/count-tickets", dependencies=[Depends(get_api_key)])
async def count_tickets(request: Request):
    """
    Endpoint to receive raw JSON data (either a single ticket object or a list of tickets) and return the count.
    """
    try:
        # Log raw request body
        body = await request.body()
        logging.info("Raw request body: %s", body)

        # Parse JSON data
        payload = await request.json()

        # Check if payload is a list or a single dictionary (ticket)
        if isinstance(payload, list):
            ticket_count = len(payload)
        elif isinstance(payload, dict):
            ticket_count = 1
        else:
            raise HTTPException(status_code=400, detail="Invalid format: Expected a JSON array or single ticket object.")

        return {"ticket_count": ticket_count}

    except Exception as e:
        logging.error("Error processing request: %s", str(e))
        raise HTTPException(status_code=500, detail="Error processing JSON data")


# Define a helper function to calculate resolution time in hours
def calculate_resolution_time(create_date, resolved_date):
    if create_date and resolved_date:
        return (datetime.fromisoformat(resolved_date[:-1]) - datetime.fromisoformat(
            create_date[:-1])).total_seconds() / 3600
    return None


# Define a helper function to calculate SLA met or not
def check_sla_met(ticket):
    return ticket.get("serviceLevelAgreementHasBeenMet") is True


@app.post("/ticket-stats")
async def ticket_stats(request: Request):
    try:
        tickets = await request.json()

        if not isinstance(tickets, list):
            raise HTTPException(status_code=400, detail="Expected a JSON array of tickets.")

        stats = {
            "total_tickets": len(tickets),
            "by_company": {},
            "by_contact": {},
            "sla_met_count": 0,
            "priority_count": {1: 0, 2: 0, 3: 0, 4: 0},
            "average_resolution_time": 0.0,
            "issue_type_count": {},
            "sub_issue_type_count": {}
        }

        total_resolution_time = 0
        resolved_tickets_count = 0

        for ticket in tickets:
            # Count by company and contact
            company_id = ticket.get("companyID")
            contact_id = ticket.get("contactID")

            stats["by_company"][company_id] = stats["by_company"].get(company_id, 0) + 1
            stats["by_contact"][contact_id] = stats["by_contact"].get(contact_id, 0) + 1

            # SLA check
            if check_sla_met(ticket):
                stats["sla_met_count"] += 1

            # Priority count
            priority = ticket.get("priority")
            if priority in stats["priority_count"]:
                stats["priority_count"][priority] += 1

            # Resolution time
            create_date = ticket.get("createDate")
            resolved_date = ticket.get("resolvedDateTime")
            resolution_time = calculate_resolution_time(create_date, resolved_date)

            if resolution_time is not None:
                total_resolution_time += resolution_time
                resolved_tickets_count += 1

            # Issue and sub-issue type counts
            issue_type = ticket.get("issueType")
            sub_issue_type = ticket.get("subIssueType")

            stats["issue_type_count"][issue_type] = stats["issue_type_count"].get(issue_type, 0) + 1
            stats["sub_issue_type_count"][sub_issue_type] = stats["sub_issue_type_count"].get(sub_issue_type, 0) + 1

        # Calculate average resolution time
        if resolved_tickets_count > 0:
            stats["average_resolution_time"] = total_resolution_time / resolved_tickets_count

        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/report/")
async def generate_report(device_data: list[DeviceData]):
    # Organize data based on integration presence
    summary_list = []
    for device in device_data:
        device_summary = {
            "device_name": device.Name,
            "Datto_RMM": device.Datto_RMM,
            "Huntress": device.Huntress,
            "Workstation_AD": device.Workstation_AD,
            "Server_AD": device.Server_AD,
            "ImmyBot": device.ImmyBot,
            "Auvik": device.Auvik,
            "Inactive_Computer": device.Inactive_Computer,
            "LastLoggedInUser": device.LastLoggedOnUser,
            "IPv4Address": device.IPv4Address,
            "OperatingSystem": device.OperatingSystem,
            "antivirusProduct": device.antivirusProduct,
            "antivirusStatus": device.antivirusStatus,
            "lastReboot": device.lastReboot,
            "lastSeen": device.lastSeen,
            "patchStatus": device.patchStatus,
            "rebootRequired": device.rebootRequired,
            "warrantyDate": device.warrantyDate,
            "datto_id": device.datto_id,
            "huntress_id": device.huntress_id,
            "immy_id": device.immy_id,
            "auvik_id": device.auvik_id
        }
        summary_list.append(device_summary)

    # Perform analytics on the data
    analytics = generate_analytics(device_data)

    return {"report": summary_list, "analytics": analytics}
