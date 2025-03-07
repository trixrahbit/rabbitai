import base64
import json
from datetime import datetime
from typing import List, Dict, Optional
import jwt
from jwt import PyJWKClient
import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text
from config import OPENID_CONFIG_URL, APP_ID, get_db_connection, get_secondary_db_connection
from models.models import DeviceData
from security.auth import get_api_key
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from services.ai_processing import generate_recommendations, handle_sendtoai
from services.bot_actions import send_message_to_teams
from services.data_processing import generate_analytics, run_pipeline
from services.pdf_service import generate_pdf_report
import uuid
import os

from services.pipelines import start_kpi_background_update, Session
from ticket_handling.main_ticket_handler import fetch_tickets_from_webhook, assign_ticket_weights, construct_ticket_card
from fastapi import Body


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
logging.basicConfig(filename="/var/www/rabbitai/rabbitai.log", level=logging.INFO)
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

    jwks_uri = openid_config["jwks_uri"]

    # Fetch JWKS
    jwk_client = PyJWKClient(jwks_uri)
    signing_key = jwk_client.get_signing_key_from_jwt(token)

    # Validate token
    try:
        decoded_token = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=APP_ID,
            issuer="https://api.botframework.com"
        )
        logging.info(f"Token successfully validated. Decoded token: {decoded_token}")
        return decoded_token
    except jwt.InvalidTokenError as e:
        logging.error(f"Token validation failed: {e}")
        raise HTTPException(status_code=403, detail=f"Token validation failed: {e}")


@app.post("/count-tickets", dependencies=[Depends(get_api_key)])
async def count_tickets(request: Request):
    try:
        body = await request.body()
        logging.info("Raw request body: %s", body.decode("utf-8"))
        payload = await request.json()
        if isinstance(payload, list):
            ticket_count = len(payload)
        elif isinstance(payload, dict):
            ticket_count = 1
        else:
            raise HTTPException(status_code=400,
                                detail="Invalid format: Expected a JSON array or single ticket object.")

        return {"ticket_count": ticket_count}

    except Exception as e:
        logging.error("Error processing request: %s", str(e))
        raise HTTPException(status_code=500, detail="Error processing JSON data")


async def calculate_resolution_time(create_date: Optional[str], resolved_date: Optional[str]):
    if not create_date or not resolved_date:
        return None
    try:
        start = datetime.fromisoformat(create_date.rstrip("Z"))  # Handle 'Z'
        end = datetime.fromisoformat(resolved_date.rstrip("Z"))
        return (end - start).total_seconds() / 3600
    except ValueError:
        return None


async def check_sla_met(ticket):
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
async def generate_report(device_data: List[DeviceData] = Body(...)):
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
            "CyberCNS": device.CyberCNS,
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
            "cybercns_id": device.cybercns_id,
            "locationName": device.locationName if hasattr(device, "locationName") else "N/A",
            "itglue_id": device.itglue_id if hasattr(device, "itglue_id") else "N/A",
            "manufacturer_name": device.manufacturer_name if hasattr(device, "manufacturer_name") else "N/A",
            "model_name": device.model_name if hasattr(device, "model_name") else "N/A",
            "serial_number": device.serial_number if hasattr(device, "serial_number") else "N/A"
        }
        summary_list.append(device_summary)

    analytics = await generate_analytics(device_data)

    # ✅ Convert unique_manufacturers from a list to a dictionary with counts
    if isinstance(analytics.get("counts", {}).get("unique_manufacturers"), list):
        manufacturer_counts = {}
        for manufacturer in analytics["counts"]["unique_manufacturers"]:
            manufacturer_counts[manufacturer] = manufacturer_counts.get(manufacturer, 0) + 1
        analytics["counts"]["unique_manufacturers"] = manufacturer_counts  # Convert to dictionary

    recommendations = await generate_recommendations(analytics)

    filename = f"rabbit_report_{uuid.uuid4()}.pdf"
    pdf_path = generate_pdf_report(analytics, filename=filename)

    return {
        "download_url": f"https://rabbit.webitservices.com/download/{filename}",
        "report": {
            "summary": summary_list,
            "analytics": analytics,
            "recommendations": recommendations
        }
    }


async def cleanup_file(path: str):
    if os.path.exists(path):
        try:
            os.remove(path)
            logging.info(f"Deleted file: {path}")
        except Exception as e:
            logging.error(f"Error deleting file: {e}")


@app.get("/download/{filename}")
async def download_report(filename: str):
    pdf_path = os.path.join("/tmp", filename)

    if not os.path.exists(pdf_path):
        logging.error(f"❌ File {pdf_path} not found for download.")
        raise HTTPException(status_code=404, detail="File not found")

    # ✅ Streaming response ensures cleanup only after the file is fully sent
    def file_iterator():
        with open(pdf_path, "rb") as f:
            yield from f
        os.remove(pdf_path)  # Cleanup happens **only after** the file is sent
        logging.info(f"✅ Deleted file: {pdf_path}")

    return StreamingResponse(file_iterator(), media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename={filename}"
    })


@app.post("/command")
async def handle_command(request: Request):
    """Handles commands from Microsoft Teams."""
    logging.info("🚀 Received a command request from Teams.")

    # Step 1: Validate Authorization Header
    auth_header = request.headers.get("Authorization")
    logging.debug(f"🔑 Authorization Header: {auth_header}")

    await validate_teams_token(auth_header)

    try:
        # Step 2: Parse Payload
        payload = await request.json()
        logging.debug(f"📩 Received Payload: {json.dumps(payload, indent=2)}")

        command_text = payload.get("text", "").strip().lower()
        aad_object_id = payload.get("from", {}).get("aadObjectId")
        service_url = payload.get("serviceUrl")
        conversation_id = payload.get("conversation", {}).get("id")

        if not command_text or not aad_object_id or not service_url or not conversation_id:
            raise ValueError("🚨 Missing required fields in payload!")

        logging.info(f"🔹 Command Received: {command_text}")
        logging.debug(f"👤 AAD Object ID: {aad_object_id}, 📡 Service URL: {service_url}, 💬 Conversation ID: {conversation_id}")

        # **Handle `askRabbit` Command**
        if command_text.startswith("askrabbit"):
            args = command_text[len("askrabbit"):].strip()
            logging.info(f"🤖 Processing `askRabbit` command with args: {args}")

            result = await handle_sendtoai(args)

            response_text = result.get("response", "No response received.")
            if isinstance(response_text, list):  # Ensure it's not a list of dicts
                response_text = " ".join(
                    [item["text"] for item in response_text if isinstance(item, dict) and "text" in item]
                )

            logging.debug(f"📝 AI Response: {response_text}")

            try:
                async with get_db_connection() as conn:  # ✅ FIXED: Use `async with` instead of `async for`
                    async with conn.begin():
                        await conn.execute(
                            text(
                                "INSERT INTO CommandLogs (aadObjectId, command, command_data, result_data) "
                                "VALUES (:aadObjectId, :command, :command_data, :result_data)"
                            ),
                            {
                                "aadObjectId": aad_object_id,
                                "command": "askRabbit",
                                "command_data": json.dumps({"message": args}),
                                "result_data": json.dumps({"response": response_text}),
                            },
                        )
                        logging.info("✅ `askRabbit` command logged successfully!")
            except Exception as e:
                logging.error(f"❌ Failed to log 'askRabbit' command to database: {e}", exc_info=True)

            adaptive_card = {
                "type": "AdaptiveCard",
                "version": "1.2",
                "body": [
                    {"type": "TextBlock", "text": "**Rabbit AI Response**", "wrap": True, "weight": "Bolder", "size": "Medium"},
                    {"type": "TextBlock", "text": f"**Question:** {args}", "wrap": True, "weight": "Bolder"},
                    {"type": "TextBlock", "text": f"**Answer:**\n\n{response_text}", "wrap": True}
                ]
            }

            await send_message_to_teams(service_url, conversation_id, aad_object_id, adaptive_card)
            logging.info("📩 AI response sent to Teams!")

            return {"status": "success", "response": response_text}

        # **Handle `getnextticket` Command**
        if command_text.startswith("getnextticket"):
            logging.info("🎫 Processing `getnextticket` command...")
            tickets = await fetch_tickets_from_webhook(aad_object_id)
            logging.debug(f"📊 Tickets Retrieved: {len(tickets)}")

            top_tickets = await assign_ticket_weights(tickets)
            logging.debug(f"🏆 Top Ticket(s): {top_tickets}")

            ticket_details = [{"ticket_id": t["id"], "title": t["title"], "points": t["weight"]} for t in top_tickets]

            try:
                async with get_db_connection() as conn:  # ✅ FIXED: Use `async with`
                    async with conn.begin():
                        await conn.execute(
                            text(
                                "INSERT INTO CommandLogs (aadObjectId, command, command_data, result_data) "
                                "VALUES (:aadObjectId, :command, :command_data, :result_data)"
                            ),
                            {
                                "aadObjectId": aad_object_id,
                                "command": "getnextticket",
                                "command_data": json.dumps({"command": "getnextticket"}),
                                "result_data": json.dumps({"tickets": ticket_details}),
                            },
                        )
                        logging.info("✅ `getnextticket` command logged successfully!")
            except Exception as e:
                logging.error(f"❌ Failed to log 'getnextticket' command to database: {e}", exc_info=True)

            adaptive_card = await construct_ticket_card(top_tickets)
            await send_message_to_teams(service_url, conversation_id, aad_object_id, adaptive_card)
            logging.info("📩 Ticket details sent to Teams!")

            return {"status": "success", "message": "Tickets sent to Teams."}

        # **Handle `mytickets` Command**
        if command_text.startswith("mytickets"):
            logging.info("📋 Processing `mytickets` command...")
            tickets = await fetch_tickets_from_webhook(aad_object_id)

            if not tickets:
                logging.info("✅ No tickets assigned to user.")
                return {"status": "success", "message": "No tickets assigned to you."}

            ticket_cards = []
            for ticket in tickets:
                ticket_id = ticket.get("id", "Unknown")
                title = ticket.get("title", "Untitled")
                description = ticket.get("description", "No description available.")[:200] + "..."
                status = ticket.get("status", "Unknown")
                ticket_url = f"https://ww15.autotask.net/Mvc/ServiceDesk/TicketDetail.mvc?workspace=False&ids%5B0%5D={ticket_id}&ticketId={ticket_id}"

                ticket_cards.append({
                    "type": "Container",
                    "items": [
                        {"type": "TextBlock", "text": f"**Ticket ID:** {ticket_id}", "wrap": True, "weight": "Bolder"},
                        {"type": "TextBlock", "text": f"**Title:** {title}", "wrap": True},
                        {"type": "TextBlock", "text": f"**Description:** {description}", "wrap": True},
                        {"type": "TextBlock", "text": f"**Status:** {status}", "wrap": True},
                        {"type": "ActionSet", "actions": [{"type": "Action.OpenUrl", "title": "View Ticket", "url": ticket_url}]}
                    ]
                })

            adaptive_card = {
                "type": "AdaptiveCard",
                "version": "1.2",
                "body": [{"type": "TextBlock", "text": "**My Tickets**", "wrap": True, "weight": "Bolder", "size": "Large"}] + ticket_cards
            }

            await send_message_to_teams(service_url, conversation_id, aad_object_id, adaptive_card)
            logging.info("📩 User's ticket list sent to Teams!")

            return {"status": "success", "message": "Tickets sent to Teams."}

    except Exception as e:
        logging.error(f"❌ Error processing command: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process command.")


@app.post("/process_contracts/")
async def process_contracts(input_data: List[Dict] = Body(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    """
    Accepts contract data, immediately responds with 200 OK, and processes database updates asynchronously.
    """
    logging.info("🔄 Received contract data, starting background processing...")

    # ✅ Send the task to background and immediately return success response
    background_tasks.add_task(process_contracts_in_background, input_data)

    return {"message": "✅ Received successfully. Processing in background."}


async def process_units_in_background(input_data: List[Dict]):
    """Background task to insert/merge contract units into the database."""
    conn = await get_secondary_db_connection()

    logging.info(f"🔍 Connection Type: {type(conn)}")
    logging.info(f"📦 Received {len(input_data)} contract units to process.")
    if not input_data:
        logging.warning("⚠️ No contract unit data received. Exiting function.")
        conn.close()
        return

    logging.info(f"📦 First contract unit data sample: {input_data[:2]}")  # ✅ Log sample units

    try:
        for unit in input_data:
            unit_id = unit.get("id")
            contract_id = unit.get("contractID")
            service_id = unit.get("serviceID")

            logging.info(f"🔄 Processing Contract Unit ID: {unit_id}")

            start_dt = await parse_date(unit.get("startDate"))
            end_dt = await parse_date(unit.get("endDate"))
            approve_dt = await parse_date(unit.get("approveAndPostDate"))

            query = text("""
            MERGE INTO dbo.ContractUnits AS target
            USING (SELECT
                :id AS id,
                :contractID AS contractID,
                :serviceID AS serviceID,
                :startDate AS startDate,
                :endDate AS endDate,
                :approveAndPostDate AS approveAndPostDate,
                :unitCost AS unitCost,
                :unitPrice AS unitPrice,
                :internalCurrencyPrice AS internalCurrencyPrice,
                :organizationalLevelAssociationID AS organizationalLevelAssociationID,
                :invoiceDescription AS invoiceDescription,
                :units AS units
            ) AS source
            ON target.id = source.id  

            WHEN MATCHED THEN
                UPDATE SET
                    contractID = source.contractID,
                    serviceID = source.serviceID,
                    startDate = source.startDate,
                    endDate = source.endDate,
                    approveAndPostDate = source.approveAndPostDate,
                    unitCost = source.unitCost,
                    unitPrice = source.unitPrice,
                    internalCurrencyPrice = source.internalCurrencyPrice,
                    organizationalLevelAssociationID = source.organizationalLevelAssociationID,
                    invoiceDescription = source.invoiceDescription,
                    units = source.units

            WHEN NOT MATCHED THEN
                INSERT (
                    id, contractID, serviceID, startDate, endDate, approveAndPostDate, 
                    unitCost, unitPrice, internalCurrencyPrice, organizationalLevelAssociationID, 
                    invoiceDescription, units
                )
                VALUES (
                    source.id, source.contractID, source.serviceID, source.startDate, 
                    source.endDate, source.approveAndPostDate, source.unitCost, source.unitPrice, 
                    source.internalCurrencyPrice, source.organizationalLevelAssociationID, 
                    source.invoiceDescription, source.units
                );
            """)

            values = {
                "id": unit_id,
                "contractID": contract_id,
                "serviceID": service_id,
                "startDate": start_dt,
                "endDate": end_dt,
                "approveAndPostDate": approve_dt,
                "unitCost": unit.get("unitCost", 0),
                "unitPrice": unit.get("unitPrice", 0),
                "internalCurrencyPrice": unit.get("internalCurrencyPrice", 0),
                "organizationalLevelAssociationID": unit.get("organizationalLevelAssociationID", None),
                "invoiceDescription": unit.get("invoiceDescription", ""),
                "units": unit.get("units", 0),
            }

            try:
                result = conn.execute(query, values)
                conn.commit()
                logging.info(f"✅ Query executed. Affected rows: {result.rowcount}")
            except Exception as e:
                logging.critical(f"🔥 Error executing query for Contract Unit ID {unit_id}: {e}", exc_info=True)

    finally:
        conn.close()
        logging.info("🔌 Database connection closed.")


@app.post("/process_contract_units/")
async def process_contract_units(input_data: List[Dict] = Body(...),
                                 background_tasks: BackgroundTasks = BackgroundTasks()):
    """
    Accepts contract unit data, immediately responds with 200 OK, and processes database updates asynchronously.
    """
    logging.info(f"🔄 Received {len(input_data)} contract units, starting background processing...")

    # ✅ Send the task to background and immediately return success response
    background_tasks.add_task(process_units_in_background, input_data)

    return {"message": "✅ Received successfully. Processing in background."}


async def process_timeentries_in_background(input_data: List[Dict]):
    """Background task to insert/merge time entry data into the database."""
    conn = await get_secondary_db_connection()

    logging.info(f"🔍 Connection Type: {type(conn)}")
    logging.info(f"📦 Received {len(input_data)} time entries to process.")

    if not input_data:
        logging.warning("⚠️ No time entry data received. Exiting function.")
        conn.close()
        return

    logging.info(f"📦 First time entry sample: {input_data[:2]}")  # ✅ Log sample data

    successful_entries = 0
    failed_entries = 0

    try:
        for entry in input_data:
            entry_id = entry.get("id")
            contract_id = entry.get("contractID", None)

            # ✅ Ensure contractID is NEVER NULL (set to 0 if missing)
            if contract_id is None:
                contract_id = 0  # 👈 Use 0 as fallback for missing contractID

            logging.info(f"🔄 Processing Time Entry ID: {entry_id} with contractID: {contract_id}")

            # ✅ Convert date fields safely
            create_dt = parse_date(entry.get("createDateTime"))
            date_worked = parse_date(entry.get("dateWorked"))
            end_dt = parse_date(entry.get("endDateTime"))
            last_modified_dt = parse_date(entry.get("lastModifiedDateTime")) or datetime.utcnow()
            start_dt = parse_date(entry.get("startDateTime"))

            query = text("""
            MERGE INTO dbo.TimeEntries AS target
            USING (SELECT
                :id AS id,
                :contractID AS contractID,
                :contractServiceBundleID AS contractServiceBundleID,
                :contractServiceID AS contractServiceID,
                :createDateTime AS createDateTime,
                :creatorUserID AS creatorUserID,
                :dateWorked AS dateWorked,
                :endDateTime AS endDateTime,
                :hoursToBill AS hoursToBill,
                :hoursWorked AS hoursWorked,
                :internalNotes AS internalNotes,
                :isNonBillable AS isNonBillable,
                :lastModifiedDateTime AS lastModifiedDateTime,
                :resourceID AS resourceID,
                :roleID AS roleID,
                :startDateTime AS startDateTime,
                :summaryNotes AS summaryNotes,
                :taskID AS taskID,
                :ticketID AS ticketID,
                :timeEntryType AS timeEntryType
            ) AS source
            ON target.id = source.id  

            WHEN MATCHED THEN
                UPDATE SET
                    contractID = source.contractID,
                    contractServiceBundleID = source.contractServiceBundleID,
                    contractServiceID = source.contractServiceID,
                    createDateTime = source.createDateTime,
                    creatorUserID = source.creatorUserID,
                    dateWorked = source.dateWorked,
                    endDateTime = source.endDateTime,
                    hoursToBill = source.hoursToBill,
                    hoursWorked = source.hoursWorked,
                    internalNotes = source.internalNotes,
                    isNonBillable = source.isNonBillable,
                    lastModifiedDateTime = source.lastModifiedDateTime,
                    resourceID = source.resourceID,
                    roleID = source.roleID,
                    startDateTime = source.startDateTime,
                    summaryNotes = source.summaryNotes,
                    taskID = source.taskID,
                    ticketID = source.ticketID,
                    timeEntryType = source.timeEntryType

            WHEN NOT MATCHED THEN
                INSERT (
                    id, contractID, contractServiceBundleID, contractServiceID, createDateTime,
                    creatorUserID, dateWorked, endDateTime, hoursToBill, hoursWorked,
                    internalNotes, isNonBillable, lastModifiedDateTime, resourceID, roleID,
                    startDateTime, summaryNotes, taskID, ticketID, timeEntryType
                )
                VALUES (
                    source.id, source.contractID, source.contractServiceBundleID, source.contractServiceID, source.createDateTime,
                    source.creatorUserID, source.dateWorked, source.endDateTime, source.hoursToBill, source.hoursWorked,
                    source.internalNotes, source.isNonBillable, source.lastModifiedDateTime, source.resourceID, source.roleID,
                    source.startDateTime, source.summaryNotes, source.taskID, source.ticketID, source.timeEntryType
                );
            """)

            values = {
                "id": entry_id,
                "contractID": contract_id,  # ✅ Guaranteed to have a value (0 if missing)
                "contractServiceBundleID": entry.get("contractServiceBundleID"),
                "contractServiceID": entry.get("contractServiceID"),
                "createDateTime": create_dt,
                "creatorUserID": entry.get("creatorUserID"),
                "dateWorked": date_worked,
                "endDateTime": end_dt,
                "hoursToBill": entry.get("hoursToBill"),
                "hoursWorked": entry.get("hoursWorked"),
                "internalNotes": entry.get("internalNotes"),
                "isNonBillable": entry.get("isNonBillable"),
                "lastModifiedDateTime": last_modified_dt,
                "resourceID": entry.get("resourceID"),
                "roleID": entry.get("roleID"),
                "startDateTime": start_dt,
                "summaryNotes": entry.get("summaryNotes"),
                "taskID": entry.get("taskID"),
                "ticketID": entry.get("ticketID"),
                "timeEntryType": entry.get("timeEntryType"),
            }

            try:
                result = conn.execute(query, values)
                conn.commit()
                logging.info(f"✅ Query executed for Time Entry ID {entry_id}. Affected rows: {result.rowcount}")
                successful_entries += 1
            except Exception as e:
                logging.error(f"❌ Error executing query for Time Entry ID {entry_id}: {e}", exc_info=True)
                failed_entries += 1

        logging.info(f"🎯 Completed processing {successful_entries} time entries. {failed_entries} entries had issues.")

    except Exception as e:
        logging.critical(f"🔥 Critical error during time entry processing: {e}", exc_info=True)

    finally:
        conn.close()
        logging.info("🔌 Database connection closed.")


async def parse_datetime(date_str):
    """Converts a date string into a proper datetime format or returns None."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.rstrip("Z"))  # Handles 'Z' at the end
    except ValueError:
        logging.error(f"🚨 Invalid datetime format: {date_str}. Returning None.")
        return None


@app.post("/process_time_entries/")
async def process_time_entries(input_data: List[Dict] = Body(...),
                               background_tasks: BackgroundTasks = BackgroundTasks()):
    """
    Accepts time entry data, immediately responds with 200 OK, and processes database updates asynchronously.
    """
    logging.info("🔄 Received time entry data, starting background processing...")

    # ✅ Send the task to background and immediately return success response
    background_tasks.add_task(process_timeentries_in_background, input_data)

    return {"message": "✅ Received successfully. Processing in background."}


@app.get("/update-client-revenue/")
async def update_client_revenue(background_tasks: BackgroundTasks):
    """Trigger revenue update process in background."""
    logging.info("🔄 Manual trigger: Starting revenue update process...")
    background_tasks.add_task(run_pipeline)
    return {"message": "✅ Client revenue update scheduled!"}


@app.on_event("startup")
async def startup_kpi_event():
    """Start automatic updates when FastAPI starts."""
    logging.info("🚀 FastAPI startup: Initializing KPI update process...")
    await start_kpi_background_update()
