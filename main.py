from fastapi import FastAPI, Depends, HTTPException, Request
from config import settings
from models import DataAggregationRequest, EmailRequest
from security.auth import get_api_key
from services.pdf_service import generate_pdf
from services.email_service import send_email_with_pdf
from services.data_processing import count_open_tickets
from typing import List
from models import TicketData

app = FastAPI()

@app.post("/count-tickets", dependencies=[Depends(get_api_key)])
async def count_tickets(request: Request):
    """
    Endpoint to receive JSON data containing tickets and return the count.
    """
    try:
        # Parse the incoming JSON
        payload = await request.json()

        # Ensure 'data' key exists and is a list
        if "data" not in payload or not isinstance(payload["data"], list):
            raise HTTPException(status_code=400, detail="Invalid format: 'data' should be a list of tickets.")

        # Get the count of tickets
        ticket_count = len(payload["data"])

        return {"ticket_count": ticket_count}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
