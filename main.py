import base64
import html
import json
from datetime import datetime
from typing import List, Dict, Optional, Union
import jwt
import pyodbc
from fastapi.encoders import jsonable_encoder
from jwt import PyJWKClient
import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks, Form
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import ValidationError
from sqlalchemy import text
from starlette.responses import HTMLResponse
from config import APP_SECRET, OPENID_CONFIG_URL, APP_ID, get_db_connection, get_secondary_db_connection
from models import DeviceData, ProcessedContractUnit
from security.auth import get_api_key
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from services.ai_processing import generate_recommendations, handle_sendtoai
from services.bot_actions import send_message_to_teams
from services.data_processing import generate_analytics, run_pipeline, start_background_update
from services.pdf_service import generate_pdf_report
import uuid
import os
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
            raise HTTPException(status_code=400, detail="Invalid format: Expected a JSON array or single ticket object.")

        return {"ticket_count": ticket_count}

    except Exception as e:
        logging.error("Error processing request: %s", str(e))
        raise HTTPException(status_code=500, detail="Error processing JSON data")

def calculate_resolution_time(create_date: Optional[str], resolved_date: Optional[str]):
    if not create_date or not resolved_date:
        return None
    try:
        start = datetime.fromisoformat(create_date.rstrip("Z"))  # Handle 'Z'
        end = datetime.fromisoformat(resolved_date.rstrip("Z"))
        return (end - start).total_seconds() / 3600
    except ValueError:
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

    analytics = generate_analytics(device_data)

    # ✅ Convert unique_manufacturers from a list to a dictionary with counts
    if isinstance(analytics.get("counts", {}).get("unique_manufacturers"), list):
        manufacturer_counts = {}
        for manufacturer in analytics["counts"]["unique_manufacturers"]:
            manufacturer_counts[manufacturer] = manufacturer_counts.get(manufacturer, 0) + 1
        analytics["counts"]["unique_manufacturers"] = manufacturer_counts  # Convert to dictionary

    recommendations = generate_recommendations(analytics)

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

def cleanup_file(path: str):
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

# Teams Commands Start Here
@app.post("/command")
async def handle_command(request: Request):
    auth_header = request.headers.get("Authorization")
    await validate_teams_token(auth_header)
    try:
        # Parse the incoming payload
        payload = await request.json()
        logging.debug(f"Received payload: {json.dumps(payload, indent=2)}")

        command_text = payload.get("text", "").strip().lower()  # Normalize command to lowercase
        aad_object_id = payload.get("from", {}).get("aadObjectId")
        service_url = payload.get("serviceUrl")
        conversation_id = payload.get("conversation", {}).get("id")

        # Ensure all required fields are present
        if not command_text or not aad_object_id or not service_url or not conversation_id:
            raise ValueError("Missing required fields")

        # Process `askRabbit` command
        if command_text.startswith("askrabbit"):
            args = command_text[len("askRabbit"):].strip()
            result = await handle_sendtoai(args)

            # Extract response as a string
            response_text = result.get("response", "No response received.")

            if isinstance(response_text, list):  # Ensure it's not a list of dicts
                response_text = " ".join(
                    [item["text"] for item in response_text if isinstance(item, dict) and "text" in item])

            # Log the command and response to the database
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO CommandLogs (aadObjectId, command, command_data, result_data) VALUES (?, ?, ?, ?)",
                    aad_object_id,
                    "askRabbit",
                    json.dumps({"message": args}),
                    json.dumps({"response": response_text})
                )
                conn.commit()
            except Exception as e:
                logging.error(f"Failed to log 'askRabbit' command to database: {e}")

            # Properly formatted Adaptive Card
            body = [
                {
                    "type": "TextBlock",
                    "text": "**Rabbit AI Response**",
                    "wrap": True,
                    "weight": "Bolder",
                    "size": "Medium",
                    "spacing": "Medium"
                },
                {
                    "type": "TextBlock",
                    "text": f"**Question:** {args}",
                    "wrap": True,
                    "weight": "Bolder",
                    "spacing": "Small"
                },
                {
                    "type": "TextBlock",
                    "text": f"**Answer:**\n\n{response_text}",
                    "wrap": True,
                    "spacing": "Small"
                }
            ]

            # Final Adaptive Card
            adaptive_card = {
                "type": "AdaptiveCard",
                "version": "1.2",
                "body": body
            }

            # Send Adaptive Card response to Teams
            await send_message_to_teams(service_url, conversation_id, aad_object_id, adaptive_card)

            return JSONResponse(content={"status": "success", "response": response_text})

        # Process `getnextticket` command
        if command_text.startswith("getnextticket"):
            tickets = await fetch_tickets_from_webhook(aad_object_id)
            top_tickets = assign_ticket_weights(tickets)

            # Prepare ticket details for logging
            ticket_details = [
                {"ticket_id": t["id"], "title": t["title"], "points": t["weight"]}
                for t in top_tickets
            ]

            # Log the command and result to the database
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO CommandLogs (aadObjectId, command, command_data, result_data) VALUES (?, ?, ?, ?)",
                    aad_object_id,
                    "getnextticket",
                    json.dumps({"command": "getnextticket"}),
                    json.dumps({"tickets": ticket_details})
                )
                conn.commit()
            except Exception as e:
                logging.error(f"Failed to log 'getnextticket' command to database: {e}")

            # Construct Adaptive Card for Teams
            adaptive_card = construct_ticket_card(top_tickets)
            await send_message_to_teams(service_url, conversation_id, aad_object_id, adaptive_card)

            return JSONResponse(content={"status": "success", "message": "Tickets sent to Teams."})

        # Process `mytickets` command
        if command_text.startswith("mytickets"):
            try:
                tickets = await fetch_tickets_from_webhook(aad_object_id)

                if not tickets:
                    return JSONResponse(content={"status": "success", "message": "No tickets assigned to you."})

                # Construct Adaptive Card to display a list of tickets
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
                            {
                                "type": "TextBlock",
                                "text": f"**Ticket ID:** {ticket_id}",
                                "wrap": True,
                                "weight": "Bolder",
                                "spacing": "Small"
                            },
                            {
                                "type": "TextBlock",
                                "text": f"**Title:** {title}",
                                "wrap": True,
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
                                "text": f"**Status:** {status}",
                                "wrap": True,
                                "spacing": "Small"
                            },
                            {
                                "type": "ActionSet",
                                "spacing": "Small",
                                "actions": [
                                    {
                                        "type": "Action.OpenUrl",
                                        "title": "View Ticket",
                                        "url": ticket_url
                                    }
                                ]
                            }
                        ]
                    })

                # Combine tickets into a single Adaptive Card
                adaptive_card = {
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "**My Tickets**",
                            "wrap": True,
                            "weight": "Bolder",
                            "size": "Large",
                            "spacing": "Medium"
                        },
                        *ticket_cards
                    ]
                }

                # Send Adaptive Card to Teams
                await send_message_to_teams(service_url, conversation_id, aad_object_id, adaptive_card)

                return JSONResponse(content={"status": "success", "message": "Tickets sent to Teams."})

            except Exception as e:
                logging.error(f"Error processing `mytickets` command: {e}")
                raise HTTPException(status_code=500, detail="Failed to process `mytickets` command.")



    except Exception as e:
        logging.error(f"Error processing command: {e}")
        raise HTTPException(status_code=500, detail="Failed to process command.")

def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Convert ISO 8601 timestamps into datetime objects."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")  # Handles fractional seconds
    except ValueError:
        try:
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")  # Handles 'Z' format without milliseconds
        except ValueError:
            logging.error(f"🚨 Invalid date format: {date_str}, setting to default")
            return datetime.utcnow()  # Default to current timestamp instead of None





async def process_contracts_in_background(input_data: List[Dict]):
    """Background task to insert/merge contract data into the database."""
    conn = get_secondary_db_connection()

    logging.info(f"🔍 Connection Type: {type(conn)}")
    logging.info(f"📦 Received {len(input_data)} contracts to process.")
    if not input_data:
        logging.warning("⚠️ No contract data received. Exiting function.")
        conn.close()
        return

    logging.info(f"📦 First contract data sample: {input_data[:2]}")  # ✅ Log sample contracts

    try:
        for contract in input_data:
            contract_id = contract.get("id")
            logging.info(f"🔄 Processing contract ID: {contract_id}")

            start_dt = parse_date(contract.get("startDate"))
            end_dt = parse_date(contract.get("endDate"))
            last_modified_dt = parse_date(contract.get("lastModifiedDateTime")) or datetime.utcnow()

            query = text("""
            MERGE INTO dbo.Contracts AS target
            USING (SELECT
                :id AS id,
                :contractName AS contractName,
                :companyID AS companyID,
                :status AS status,
                :endDate AS endDate,
                :setupFee AS setupFee,
                :contactID AS contactID,
                :startDate AS startDate,
                :contactName AS contactName,
                :description AS description,
                :isCompliant AS isCompliant,
                :contractType AS contractType,
                :estimatedCost AS estimatedCost,
                :opportunityID AS opportunityID,
                :contractNumber AS contractNumber,
                :estimatedHours AS estimatedHours,
                :billToCompanyID AS billToCompanyID,
                :contractCategory AS contractCategory,
                :estimatedRevenue AS estimatedRevenue,
                :billingPreference AS billingPreference,
                :isDefaultContract AS isDefaultContract,
                :renewedContractID AS renewedContractID,
                :contractPeriodType AS contractPeriodType,
                :overageBillingRate AS overageBillingRate,
                :exclusionContractID AS exclusionContractID,
                :purchaseOrderNumber AS purchaseOrderNumber,
                :lastModifiedDateTime AS lastModifiedDateTime,
                :setupFeeBillingCodeID AS setupFeeBillingCodeID,
                :billToCompanyContactID AS billToCompanyContactID,
                :contractExclusionSetID AS contractExclusionSetID,
                :serviceLevelAgreementID AS serviceLevelAgreementID,
                :internalCurrencySetupFee AS internalCurrencySetupFee,
                :organizationalLevelAssociationID AS organizationalLevelAssociationID,
                :internalCurrencyOverageBillingRate AS internalCurrencyOverageBillingRate,
                :timeReportingRequiresStartAndStopTimes AS timeReportingRequiresStartAndStopTimes
            ) AS source
            ON target.contractName = source.contractName AND target.companyID = source.companyID  

            WHEN MATCHED THEN
                UPDATE SET
                    id = source.id,
                    status = source.status,
                    endDate = source.endDate,
                    setupFee = source.setupFee,
                    contactID = source.contactID,
                    startDate = source.startDate,
                    contactName = source.contactName,
                    description = source.description,
                    isCompliant = source.isCompliant,
                    contractType = source.contractType,
                    estimatedCost = source.estimatedCost,
                    opportunityID = source.opportunityID,
                    contractNumber = source.contractNumber,
                    estimatedHours = source.estimatedHours,
                    billToCompanyID = source.billToCompanyID,
                    contractCategory = source.contractCategory,
                    estimatedRevenue = source.estimatedRevenue,
                    billingPreference = source.billingPreference,
                    isDefaultContract = source.isDefaultContract,
                    renewedContractID = source.renewedContractID,
                    contractPeriodType = source.contractPeriodType,
                    overageBillingRate = source.overageBillingRate,
                    exclusionContractID = source.exclusionContractID,
                    purchaseOrderNumber = source.purchaseOrderNumber,
                    lastModifiedDateTime = source.lastModifiedDateTime,
                    setupFeeBillingCodeID = source.setupFeeBillingCodeID,
                    billToCompanyContactID = source.billToCompanyContactID,
                    contractExclusionSetID = source.contractExclusionSetID,
                    serviceLevelAgreementID = source.serviceLevelAgreementID,
                    internalCurrencySetupFee = source.internalCurrencySetupFee,
                    organizationalLevelAssociationID = source.organizationalLevelAssociationID,
                    internalCurrencyOverageBillingRate = source.internalCurrencyOverageBillingRate,
                    timeReportingRequiresStartAndStopTimes = source.timeReportingRequiresStartAndStopTimes

            WHEN NOT MATCHED THEN
                INSERT (
                    id, contractName, companyID, status, endDate, setupFee, contactID, startDate, contactName, description, isCompliant,
                    contractType, estimatedCost, opportunityID, contractNumber, estimatedHours, billToCompanyID, contractCategory,
                    estimatedRevenue, billingPreference, isDefaultContract, renewedContractID, contractPeriodType, overageBillingRate,
                    exclusionContractID, purchaseOrderNumber, lastModifiedDateTime, setupFeeBillingCodeID, billToCompanyContactID,
                    contractExclusionSetID, serviceLevelAgreementID, internalCurrencySetupFee, organizationalLevelAssociationID,
                    internalCurrencyOverageBillingRate, timeReportingRequiresStartAndStopTimes
                )
                VALUES (
                    source.id, source.contractName, source.companyID, source.status, source.endDate, source.setupFee, source.contactID, source.startDate,
                    source.contactName, source.description, source.isCompliant, source.contractType, source.estimatedCost, source.opportunityID,
                    source.contractNumber, source.estimatedHours, source.billToCompanyID, source.contractCategory, source.estimatedRevenue,
                    source.billingPreference, source.isDefaultContract, source.renewedContractID, source.contractPeriodType,
                    source.overageBillingRate, source.exclusionContractID, source.purchaseOrderNumber, source.lastModifiedDateTime,
                    source.setupFeeBillingCodeID, source.billToCompanyContactID, source.contractExclusionSetID, source.serviceLevelAgreementID,
                    source.internalCurrencySetupFee, source.organizationalLevelAssociationID, source.internalCurrencyOverageBillingRate,
                    source.timeReportingRequiresStartAndStopTimes
                );
            """)

            values = {
                "id": contract_id,
                "contractName": contract.get("contractName", ""),
                "companyID": contract.get("companyID", 0),
                "status": contract.get("status", ""),
                "endDate": end_dt,
                "setupFee": contract.get("setupFee", 0),
                "contactID": contract.get("contactID", 0),
                "startDate": start_dt,
                "contactName": contract.get("contactName", ""),
                "description": contract.get("description", ""),
                "isCompliant": contract.get("isCompliant", False),
                "contractType": contract.get("contractType", ""),
                "estimatedCost": contract.get("estimatedCost", 0),
                "opportunityID": contract.get("opportunityID", None),
                "contractNumber": contract.get("contractNumber", ""),
                "estimatedHours": contract.get("estimatedHours", 0),
                "billToCompanyID": contract.get("billToCompanyID", 0),
                "contractCategory": contract.get("contractCategory", ""),
                "estimatedRevenue": contract.get("estimatedRevenue", 0),
                "billingPreference": contract.get("billingPreference", ""),
                "isDefaultContract": contract.get("isDefaultContract", False),
                "renewedContractID": contract.get("renewedContractID", None),
                "contractPeriodType": contract.get("contractPeriodType", 0),  # 👈 Ensure this field always has a value
                "overageBillingRate": contract.get("overageBillingRate", 0),
                "exclusionContractID": contract.get("exclusionContractID", None),
                "purchaseOrderNumber": contract.get("purchaseOrderNumber", ""),
                "lastModifiedDateTime": last_modified_dt,
                "setupFeeBillingCodeID": contract.get("setupFeeBillingCodeID", None),
                "billToCompanyContactID": contract.get("billToCompanyContactID", None),
                "contractExclusionSetID": contract.get("contractExclusionSetID", None),
                "serviceLevelAgreementID": contract.get("serviceLevelAgreementID", None),
                "internalCurrencySetupFee": contract.get("internalCurrencySetupFee", 0),
                "organizationalLevelAssociationID": contract.get("organizationalLevelAssociationID", None),
                "internalCurrencyOverageBillingRate": contract.get("internalCurrencyOverageBillingRate", 0),
                "timeReportingRequiresStartAndStopTimes": contract.get("timeReportingRequiresStartAndStopTimes", False)
            }

            try:
                result = conn.execute(query, values)
                conn.commit()
                logging.info(f"✅ Query executed. Affected rows: {result.rowcount}")
            except Exception as e:
                logging.critical(f"🔥 Error executing query: {e}", exc_info=True)

    finally:
        conn.close()
        logging.info("🔌 Database connection closed.")



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
    conn = get_secondary_db_connection()

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

            start_dt = parse_date(unit.get("startDate"))
            end_dt = parse_date(unit.get("endDate"))
            approve_dt = parse_date(unit.get("approveAndPostDate"))

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
async def process_contract_units(input_data: List[Dict] = Body(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    """
    Accepts contract unit data, immediately responds with 200 OK, and processes database updates asynchronously.
    """
    logging.info(f"🔄 Received {len(input_data)} contract units, starting background processing...")

    # ✅ Send the task to background and immediately return success response
    background_tasks.add_task(process_units_in_background, input_data)

    return {"message": "✅ Received successfully. Processing in background."}


async def process_timeentries_in_background(input_data: List[Dict]):
    """Background task to insert/merge time entry data into the database."""
    conn = get_secondary_db_connection()
    cursor = conn.cursor()

    try:
        for entry in input_data:
            # Ensure contractID exists
            cursor.execute("SELECT 1 FROM dbo.Contracts WHERE id = ?", entry.get("contractID"))
            if not cursor.fetchone():
                logging.warning(f"🚨 Skipping Time Entry ID {entry.get('id')}: contractID {entry.get('contractID')} does not exist.")
                continue  # Skip this entry

            # Ensure ticketID exists (if not None)
            ticket_id = entry.get("ticketID")
            if ticket_id is not None:
                cursor.execute("SELECT 1 FROM dbo.Tickets WHERE id = ?", ticket_id)
                if not cursor.fetchone():
                    logging.warning(f"🚨 Skipping Time Entry ID {entry.get('id')}: ticketID {ticket_id} does not exist.")
                    continue  # Skip this entry

            # Convert dates
            create_dt = parse_date(entry.get("createDateTime"))
            date_worked = parse_date(entry.get("dateWorked"))
            end_dt = parse_date(entry.get("endDateTime"))
            last_modified_dt = parse_date(entry.get("lastModifiedDateTime"))
            start_dt = parse_date(entry.get("startDateTime"))

            if last_modified_dt is None:
                last_modified_dt = datetime.utcnow()

            try:
                query = """
MERGE INTO dbo.TimeEntries AS target
USING (SELECT 
    ? AS id, ? AS contractID, ? AS contractServiceBundleID, ? AS contractServiceID,
    ? AS createDateTime, ? AS creatorUserID, ? AS dateWorked, ? AS endDateTime,
    ? AS hoursToBill, ? AS hoursWorked, ? AS internalNotes, ? AS isNonBillable,
    ? AS lastModifiedDateTime, ? AS resourceID, ? AS roleID, ? AS startDateTime,
    ? AS summaryNotes, ? AS taskID, ? AS ticketID, ? AS timeEntryType
) AS source
ON target.id = source.id

WHEN MATCHED AND (
    target.contractID <> source.contractID OR
    target.contractServiceBundleID <> source.contractServiceBundleID OR
    target.contractServiceID <> source.contractServiceID OR
    target.createDateTime <> source.createDateTime OR
    target.creatorUserID <> source.creatorUserID OR
    target.dateWorked <> source.dateWorked OR
    target.endDateTime <> source.endDateTime OR
    target.hoursToBill <> source.hoursToBill OR
    target.hoursWorked <> source.hoursWorked OR
    CAST(target.internalNotes AS NVARCHAR(MAX)) <> CAST(source.internalNotes AS NVARCHAR(MAX)) OR
    target.isNonBillable <> source.isNonBillable OR
    target.lastModifiedDateTime <> source.lastModifiedDateTime OR
    target.resourceID <> source.resourceID OR
    target.roleID <> source.roleID OR
    target.startDateTime <> source.startDateTime OR
    CAST(target.summaryNotes AS NVARCHAR(MAX)) <> CAST(source.summaryNotes AS NVARCHAR(MAX)) OR
    target.taskID <> source.taskID OR
    target.ticketID <> source.ticketID OR
    target.timeEntryType <> source.timeEntryType
)

THEN UPDATE SET
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
    id, contractID, contractServiceBundleID, contractServiceID, createDateTime, creatorUserID, dateWorked, endDateTime,
    hoursToBill, hoursWorked, internalNotes, isNonBillable, lastModifiedDateTime, resourceID, roleID, startDateTime, 
    summaryNotes, taskID, ticketID, timeEntryType
)
VALUES (
    source.id, source.contractID, source.contractServiceBundleID, source.contractServiceID, source.createDateTime,
    source.creatorUserID, source.dateWorked, source.endDateTime, source.hoursToBill, source.hoursWorked,
    source.internalNotes, source.isNonBillable, source.lastModifiedDateTime, source.resourceID, source.roleID,
    source.startDateTime, source.summaryNotes, source.taskID, source.ticketID, source.timeEntryType
);
                """

                values = (
                    entry.get("id", 0),
                    entry.get("contractID", 0),
                    entry.get("contractServiceBundleID", None),
                    entry.get("contractServiceID", None),
                    create_dt,
                    entry.get("creatorUserID", 0),
                    date_worked,
                    end_dt,
                    entry.get("hoursToBill", 0.0),
                    entry.get("hoursWorked", 0.0),
                    entry.get("internalNotes", ""),
                    entry.get("isNonBillable", False),
                    last_modified_dt,
                    entry.get("resourceID", 0),
                    entry.get("roleID", 0),
                    start_dt,
                    entry.get("summaryNotes", ""),
                    entry.get("taskID", None),
                    entry.get("ticketID", 0),
                    entry.get("timeEntryType", 0)
                )

                cursor.execute(query, values)

            except pyodbc.Error as e:
                logging.error(f"🚨 MERGE failed for Time Entry ID {entry.get('id')}: {e}", exc_info=True)
                continue

        conn.commit()
        logging.info(f"✅ Successfully processed {len(input_data)} time entries.")

    except Exception as e:
        conn.rollback()
        logging.critical(f"🔥 Critical Error during time entries processing: {e}", exc_info=True)

    finally:
        cursor.close()
        conn.close()
        logging.info("🔌 Database connection closed.")


@app.post("/process_time_entries/")
async def process_time_entries(input_data: List[Dict] = Body(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    """
    Accepts time entry data, immediately responds with 200 OK, and processes database updates asynchronously.
    """
    logging.info("🔄 Received time entry data, starting background processing...")

    # ✅ Send the task to background and immediately return success response
    background_tasks.add_task(process_timeentries_in_background, input_data)

    return {"message": "✅ Received successfully. Processing in background."}

@app.get("/update-client-revenue/")
def update_client_revenue(background_tasks: BackgroundTasks):
    """Trigger revenue update process in background."""
    logging.info("🔄 Manual trigger: Starting revenue update process...")
    background_tasks.add_task(run_pipeline)
    return {"message": "✅ Client revenue update scheduled!"}

# @app.on_event("startup")
# def startup_event():
#     """Start automatic updates when FastAPI starts."""
#     logging.info("🚀 FastAPI startup: Initializing revenue update process...")
#     start_background_update()
