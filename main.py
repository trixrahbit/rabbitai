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