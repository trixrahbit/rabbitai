from fastapi import FastAPI, Depends, HTTPException
from config import settings
from models import DataAggregationRequest, EmailRequest
from security.auth import get_api_key
from services.pdf_service import generate_pdf
from services.email_service import send_email_with_pdf
from services.data_processing import count_open_tickets
from typing import List
from models import TicketData

app = FastAPI()

@app.post("/count-open-tickets", dependencies=[Depends(get_api_key)])
async def count_tickets(tickets: List[TicketData]):
    """
    Endpoint to count the number of open tickets.
    """
    open_ticket_count = count_open_tickets(tickets)
    return {"open_ticket_count": open_ticket_count}