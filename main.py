from fastapi import FastAPI, Depends, HTTPException, Request
from security.auth import get_api_key
import logging

app = FastAPI()
logging.basicConfig(filename="/var/www/rabbitai/webhook.log", level=logging.INFO)

@app.post("/count-tickets", dependencies=[Depends(get_api_key)])
async def count_tickets(request: Request):
    """
    Endpoint to receive raw JSON data (either a single ticket object or a list of tickets) and return the count.
    """
    try:
        # Parse the raw JSON input directly
        payload = await request.json()

        # Handle case where payload is a list of tickets
        if isinstance(payload, list):
            ticket_count = len(payload)
        # Handle case where payload is a single ticket object
        elif isinstance(payload, dict):
            ticket_count = 1
        else:
            raise HTTPException(status_code=400, detail="Invalid format: Expected a JSON array or single ticket object.")

        return {"ticket_count": ticket_count}

    except Exception as e:
        # Log and handle unexpected errors
        raise HTTPException(status_code=500, detail=str(e))