import base64
import json
from datetime import datetime
from typing import List, Dict

import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks, Form
from fastapi.responses import FileResponse, JSONResponse
from jose import JWTError, jwt

from config import APP_SECRET, OPENID_CONFIG_URL
from models import DeviceData
from security.auth import get_api_key
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from services.ai_processing import generate_recommendations, handle_sendtoai
from services.data_processing import generate_analytics, handle_mytickets, send_message_to_teams
from services.pdf_service import generate_pdf_report
import uuid
import os

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


def decode_jwt(token):
    try:
        parts = token.split(".")
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "==").decode("utf-8"))
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "==").decode("utf-8"))
        return header, payload
    except Exception as e:
        return {"error": f"Failed to decode token: {e}"}

async def validate_teams_token(auth_header: str):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authorization header")

    token = auth_header.split(" ")[1]

    # Fetch OpenID configuration
    async with httpx.AsyncClient() as client:
        response = await client.get(OPENID_CONFIG_URL)
        response.raise_for_status()
        openid_config = response.json()
    logging.info(f"OpenID configuration fetched: {openid_config}")

    jwks_uri = openid_config["jwks_uri"]
    issuer = openid_config["issuer"]

    # Fetch JWKS
    async with httpx.AsyncClient() as client:
        jwks_response = await client.get(jwks_uri)
        jwks_response.raise_for_status()
        jwks = jwks_response.json()
    logging.info(f"JWKS fetched: {jwks}")

    decoded_header, decoded_payload = decode_jwt(token)
    logging.info(f"Decoded JWT Header: {decoded_header}")
    logging.info(f"Decoded JWT Payload: {decoded_payload}")

    jwks_kids = [key["kid"] for key in jwks["keys"]]
    logging.info(f"Available JWKS kids: {jwks_kids}")
    logging.info(f"JWT kid: {decoded_header['kid']}")

    # Validate audience ('aud') claim
    valid_audiences = ["https://api.botframework.com", APP_ID]
    if decoded_payload.get("aud") not in valid_audiences:
        logging.error(f"Invalid audience: {decoded_payload.get('aud')}")
        raise HTTPException(status_code=403, detail="Invalid audience")

    # Validate issuer ('iss') claim
    if decoded_payload.get("iss") != issuer:
        logging.error(f"Invalid issuer: {decoded_payload.get('iss')}")
        raise HTTPException(status_code=403, detail="Invalid issuer")

    # Find the matching JWKS key
    key = next((k for k in jwks["keys"] if k["kid"] == decoded_header["kid"]), None)
    if not key:
        logging.error(f"No matching key found for kid: {decoded_header['kid']}")
        raise HTTPException(status_code=403, detail="No matching JWKS key for token 'kid'")
    logging.info(f"Found matching key: {key}")

    try:
        decoded_token = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=valid_audiences,
            issuer=issuer
        )
        logging.info(f"Token successfully validated. Decoded token: {decoded_token}")
        return decoded_token
    except JWTError as e:
        logging.error(f"Token validation failed: {e}")
        raise HTTPException(status_code=403, detail=f"Token validation failed: {e}")




@app.post("/count-tickets", dependencies=[Depends(get_api_key)])
async def count_tickets(request: Request):
    try:
        body = await request.body()
        logging.info("Raw request body: %s", body)

        payload = await request.json()

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


def calculate_resolution_time(create_date, resolved_date):
    if create_date and resolved_date:
        return (datetime.fromisoformat(resolved_date[:-1]) - datetime.fromisoformat(create_date[:-1])).total_seconds() / 3600
    return None


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
            company_id = ticket.get("companyID")
            contact_id = ticket.get("contactID")

            stats["by_company"][company_id] = stats["by_company"].get(company_id, 0) + 1
            stats["by_contact"][contact_id] = stats["by_contact"].get(contact_id, 0) + 1

            if check_sla_met(ticket):
                stats["sla_met_count"] += 1

            priority = ticket.get("priority")
            if priority in stats["priority_count"]:
                stats["priority_count"][priority] += 1

            create_date = ticket.get("createDate")
            resolved_date = ticket.get("resolvedDateTime")
            resolution_time = calculate_resolution_time(create_date, resolved_date)

            if resolution_time is not None:
                total_resolution_time += resolution_time
                resolved_tickets_count += 1

            issue_type = ticket.get("issueType")
            sub_issue_type = ticket.get("subIssueType")

            stats["issue_type_count"][issue_type] = stats["issue_type_count"].get(issue_type, 0) + 1
            stats["sub_issue_type_count"][sub_issue_type] = stats["sub_issue_type_count"].get(sub_issue_type, 0) + 1

        if resolved_tickets_count > 0:
            stats["average_resolution_time"] = total_resolution_time / resolved_tickets_count

        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/report/", dependencies=[Depends(get_api_key)])
async def generate_report(device_data: List[DeviceData]):
    summary_list = []
    for device in device_data:
        device_summary = {
            "device_name": device.Name,
            "Datto_RMM": device.Datto_RMM,
            "Huntress": device.Huntress,
            "IT_Glue": device.ITGlue,
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
            "auvik_id": device.auvik_id,
            "locationName": device.locationName if hasattr(device, "locationName") else "N/A",
            "itglue_id": device.itglue_id if hasattr(device, "itglue_id") else "N/A",
            "manufacturer_name": device.manufacturer_name if hasattr(device, "manufacturer_name") else "N/A",
            "model_name": device.model_name if hasattr(device, "model_name") else "N/A",
            "serial_number": device.serial_number if hasattr(device, "serial_number") else "N/A"
        }
        summary_list.append(device_summary)

    analytics = generate_analytics(device_data)
    recommendations = generate_recommendations(analytics)

    filename = f"rabbit_report_{uuid.uuid4()}.pdf"
    pdf_path = generate_pdf_report(analytics, recommendations, filename=filename)

    return {
        "download_url": f"https://rabbit.webitservices.com/download/{filename}",
        "report": {
            "summary": summary_list,
            "analytics": analytics,
            "recommendations": recommendations
        }
    }

def cleanup_file(path: str):
    try:
        os.remove(path)
        print(f"Deleted file: {path}")
    except Exception as e:
        print(f"Error deleting file: {e}")

@app.get("/download/{filename}")
async def download_report(filename: str, background_tasks: BackgroundTasks):
    pdf_path = os.path.join("/tmp", filename)
    if os.path.exists(pdf_path):
        background_tasks.add_task(cleanup_file, pdf_path)
        return FileResponse(path=pdf_path, filename=filename)
    else:
        raise HTTPException(status_code=404, detail="File not found")


# Teams Commands Start Here
@app.post("/ai")
async def ai_endpoint(data: dict) -> Dict[str, str]:
    """
    Example AI processing endpoint.
    """
    text = data.get("data", "")
    processed = text[::-1]  # Reverse the text as an example
    return {"result": processed}


@app.post("/command")
async def handle_command(request: Request):
    """
    Handle slash commands from Teams.
    """
    # Verify the request
    auth_header = request.headers.get("Authorization")
    await validate_teams_token(auth_header)

    try:
        # Parse JSON payload
        payload = await request.json()
        logging.info(f"Payload: {payload}")

        command = payload.get("command")
        user_id = payload.get("user_id")
        service_url = payload.get("serviceUrl")
        conversation_id = payload.get("conversation", {}).get("id")

        if not command or not user_id or not service_url or not conversation_id:
            raise ValueError("Missing required fields: 'command', 'user_id', 'serviceUrl', or 'conversation'")
    except Exception as e:
        logging.error(f"Invalid payload: {e}")
        raise HTTPException(status_code=422, detail=f"Invalid request format: {e}")

    # Log the incoming command
    logging.info(f"Received command: {command} from user: {user_id}")

    # Parse the command
    if command.startswith("/"):
        command = command[1:]  # Remove leading slash

    parts = command.split(maxsplit=1)
    command_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""

    # Dispatch to the appropriate handler
    try:
        if command_name == "sendtoai":
            result = await handle_sendtoai(args)
        elif command_name == "mytickets":
            result = await handle_mytickets(args)
        else:
            result = {"response": f"Unknown command: {command_name}"}
    except Exception as e:
        logging.error(f"Error processing command '{command_name}': {e}")
        result = {"response": f"Error processing command '{command_name}': {e}"}

    # Format the result as a message
    message = result.get("response", "No response generated.")

    # Send the result back to the user in Teams
    try:
        await send_message_to_teams(service_url, conversation_id, message)
        return JSONResponse(content={"status": "success", "message": "Message sent to Teams chat."})
    except Exception as e:
        logging.error(f"Failed to send message to Teams: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message to Teams: {e}")
