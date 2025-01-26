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
from starlette.responses import HTMLResponse
from config import APP_SECRET, OPENID_CONFIG_URL, APP_ID, get_db_connection, get_secondary_db_connection
from models import DeviceData, ContractUnit, ProcessedContractUnit
from security.auth import get_api_key
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from services.ai_processing import generate_recommendations, handle_sendtoai
from services.bot_actions import send_message_to_teams
from services.data_processing import generate_analytics
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

        command_text = payload.get("text")
        aad_object_id = payload.get("from", {}).get("aadObjectId")
        service_url = payload.get("serviceUrl")
        conversation_id = payload.get("conversation", {}).get("id")

        # Ensure all required fields are present
        if not command_text or not aad_object_id or not service_url or not conversation_id:
            raise ValueError("Missing required fields")

        # Process `askRabbit` command
        if command_text.startswith("askRabbit"):
            args = command_text[len("askRabbit"):].strip()
            result = await handle_sendtoai(args)
            response_text = result.get("response", "No response")

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

async def process_units_in_background(input_data: List[Dict]):
    """Background task to insert/merge contract units into the database."""
    logging.info(f"🚀 Starting background processing for {len(input_data)} contract units...")

    conn = get_secondary_db_connection()
    cursor = conn.cursor()

    try:
        for service in input_data:
            start_dt = parse_date(service.get("startDate"))
            end_dt = parse_date(service.get("endDate"))
            approve_dt = parse_date(service.get("approveAndPostDate"))

            try:
                cursor.execute("""
                    MERGE INTO dbo.ContractUnits AS target
                    USING (SELECT ? AS id, ? AS contractID, ? AS serviceID, ? AS startDate, ? AS endDate, ? AS approveAndPostDate,
                                  ? AS unitCost, ? AS unitPrice, ? AS internalCurrencyPrice, ? AS organizationalLevelAssociationID, ? AS invoiceDescription) AS source
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
                            invoiceDescription = source.invoiceDescription
                    WHEN NOT MATCHED THEN
                        INSERT (id, contractID, serviceID, startDate, endDate, approveAndPostDate, unitCost, unitPrice, internalCurrencyPrice, organizationalLevelAssociationID, invoiceDescription)
                        VALUES (source.id, source.contractID, source.serviceID, source.startDate, source.endDate, source.approveAndPostDate, source.unitCost, source.unitPrice, source.internalCurrencyPrice, source.organizationalLevelAssociationID, source.invoiceDescription);
                """,
                service.get("id"),
                service.get("contractID"),
                service.get("serviceID"),
                start_dt,
                end_dt,
                approve_dt,
                service.get("unitCost"),
                service.get("unitPrice"),
                service.get("internalCurrencyPrice"),
                service.get("organizationalLevelAssociationID"),
                service.get("invoiceDescription"))

            except pyodbc.Error as e:
                logging.error(f"🚨 MERGE failed for Contract Unit ID {service.get('id')}: {e}", exc_info=True)
                continue  # Log error but continue processing

        conn.commit()
        logging.info(f"✅ Successfully processed {len(input_data)} contract units.")

    except Exception as e:
        conn.rollback()
        logging.critical(f"🔥 Critical Error during contract units processing: {e}", exc_info=True)

    finally:
        cursor.close()
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

async def process_contracts_in_background(input_data: List[Dict]):
    """Background task to insert/merge contract data into the database."""
    conn = get_secondary_db_connection()
    cursor = conn.cursor()

    try:
        for contract in input_data:
            start_dt = parse_date(contract.get("startDate"))
            end_dt = parse_date(contract.get("endDate"))
            last_modified_dt = parse_date(contract.get("lastModifiedDateTime"))

            if last_modified_dt is None:
                last_modified_dt = datetime.utcnow()

            try:
                query = """
MERGE INTO dbo.Contracts AS target
USING (SELECT 
    ? AS id,
    ? AS status,
    ? AS endDate,
    ? AS setupFee,
    ? AS companyID,
    ? AS contactID,
    ? AS startDate,
    ? AS contactName,
    ? AS description,
    ? AS isCompliant,
    ? AS contractName,
    ? AS contractType,
    ? AS estimatedCost,
    ? AS opportunityID,
    ? AS contractNumber,
    ? AS estimatedHours,
    ? AS billToCompanyID,
    ? AS contractCategory,
    ? AS estimatedRevenue,
    ? AS billingPreference,
    ? AS isDefaultContract,
    ? AS renewedContractID,
    ? AS contractPeriodType,
    ? AS overageBillingRate,
    ? AS exclusionContractID,
    ? AS purchaseOrderNumber,
    ? AS lastModifiedDateTime,
    ? AS setupFeeBillingCodeID,
    ? AS billToCompanyContactID,
    ? AS contractExclusionSetID,
    ? AS serviceLevelAgreementID,
    ? AS internalCurrencySetupFee,
    ? AS organizationalLevelAssociationID,
    ? AS internalCurrencyOverageBillingRate,
    ? AS timeReportingRequiresStartAndStopTimes
) AS source
ON target.id = source.id

WHEN MATCHED AND (
    target.status <> source.status OR
    target.endDate <> source.endDate OR
    target.setupFee <> source.setupFee OR
    target.companyID <> source.companyID OR
    target.contactID <> source.contactID OR
    target.startDate <> source.startDate OR
    target.contactName <> source.contactName OR
    target.description <> source.description OR
    target.isCompliant <> source.isCompliant OR
    target.contractName <> source.contractName OR
    target.contractType <> source.contractType OR
    target.estimatedCost <> source.estimatedCost OR
    target.opportunityID <> source.opportunityID OR
    target.contractNumber <> source.contractNumber OR
    target.estimatedHours <> source.estimatedHours OR
    target.billToCompanyID <> source.billToCompanyID OR
    target.contractCategory <> source.contractCategory OR
    target.estimatedRevenue <> source.estimatedRevenue OR
    target.billingPreference <> source.billingPreference OR
    target.isDefaultContract <> source.isDefaultContract OR
    target.renewedContractID <> source.renewedContractID OR
    target.contractPeriodType <> source.contractPeriodType OR
    target.overageBillingRate <> source.overageBillingRate OR
    target.exclusionContractID <> source.exclusionContractID OR
    target.purchaseOrderNumber <> source.purchaseOrderNumber OR
    target.lastModifiedDateTime <> source.lastModifiedDateTime OR
    target.setupFeeBillingCodeID <> source.setupFeeBillingCodeID OR
    target.billToCompanyContactID <> source.billToCompanyContactID OR
    target.contractExclusionSetID <> source.contractExclusionSetID OR
    target.serviceLevelAgreementID <> source.serviceLevelAgreementID OR
    target.internalCurrencySetupFee <> source.internalCurrencySetupFee OR
    target.organizationalLevelAssociationID <> source.organizationalLevelAssociationID OR
    target.internalCurrencyOverageBillingRate <> source.internalCurrencyOverageBillingRate OR
    target.timeReportingRequiresStartAndStopTimes <> source.timeReportingRequiresStartAndStopTimes
)
THEN UPDATE SET
    status = source.status,
    endDate = source.endDate,
    setupFee = source.setupFee,
    companyID = source.companyID,
    contactID = source.contactID,
    startDate = source.startDate,
    contactName = source.contactName,
    description = source.description,
    isCompliant = source.isCompliant,
    contractName = source.contractName,
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
    id, status, endDate, setupFee, companyID, contactID, startDate, contactName, description, isCompliant,
    contractName, contractType, estimatedCost, opportunityID, contractNumber, estimatedHours, billToCompanyID,
    contractCategory, estimatedRevenue, billingPreference, isDefaultContract, renewedContractID, contractPeriodType,
    overageBillingRate, exclusionContractID, purchaseOrderNumber, lastModifiedDateTime, setupFeeBillingCodeID,
    billToCompanyContactID, contractExclusionSetID, serviceLevelAgreementID, internalCurrencySetupFee,
    organizationalLevelAssociationID, internalCurrencyOverageBillingRate, timeReportingRequiresStartAndStopTimes
)
VALUES (
    source.id, source.status, source.endDate, source.setupFee, source.companyID, source.contactID, source.startDate, 
    source.contactName, source.description, source.isCompliant, source.contractName, source.contractType, 
    source.estimatedCost, source.opportunityID, source.contractNumber, source.estimatedHours, source.billToCompanyID,
    source.contractCategory, source.estimatedRevenue, source.billingPreference, source.isDefaultContract, 
    source.renewedContractID, source.contractPeriodType, source.overageBillingRate, source.exclusionContractID, 
    source.purchaseOrderNumber, source.lastModifiedDateTime, source.setupFeeBillingCodeID, 
    source.billToCompanyContactID, source.contractExclusionSetID, source.serviceLevelAgreementID, 
    source.internalCurrencySetupFee, source.organizationalLevelAssociationID, 
    source.internalCurrencyOverageBillingRate, source.timeReportingRequiresStartAndStopTimes
);
                """

                values = (
                    contract.get("id", 0),
                    contract.get("status", ""),
                    end_dt,
                    contract.get("setupFee", 0),
                    contract.get("companyID", 0),
                    contract.get("contactID", 0),
                    start_dt,
                    contract.get("contactName", ""),
                    contract.get("description", ""),
                    contract.get("isCompliant", False),
                    contract.get("contractName", ""),
                    contract.get("contractType", ""),
                    contract.get("estimatedCost", 0),
                    contract.get("opportunityID", None),
                    contract.get("contractNumber", ""),
                    contract.get("estimatedHours", 0),
                    contract.get("billToCompanyID", 0),
                    contract.get("contractCategory", ""),
                    contract.get("estimatedRevenue", 0),
                    contract.get("billingPreference", ""),
                    contract.get("isDefaultContract", False),
                    contract.get("renewedContractID", None),
                    contract.get("contractPeriodType", ""),
                    contract.get("overageBillingRate", 0),
                    contract.get("exclusionContractID", None),
                    contract.get("purchaseOrderNumber", ""),
                    last_modified_dt,
                    contract.get("setupFeeBillingCodeID", None),
                    contract.get("billToCompanyContactID", None),
                    contract.get("contractExclusionSetID", None),
                    contract.get("serviceLevelAgreementID", None),
                    contract.get("internalCurrencySetupFee", 0),
                    contract.get("organizationalLevelAssociationID", None),
                    contract.get("internalCurrencyOverageBillingRate", 0),
                    contract.get("timeReportingRequiresStartAndStopTimes", False)
                )

                cursor.execute(query, values)

            except pyodbc.Error as e:
                logging.error(f"🚨 MERGE failed for Contract ID {contract.get('id')}: {e}", exc_info=True)
                continue

        conn.commit()
        logging.info(f"✅ Successfully processed {len(input_data)} contracts.")

    except Exception as e:
        conn.rollback()
        logging.critical(f"🔥 Critical Error during contracts processing: {e}", exc_info=True)

    finally:
        cursor.close()
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

