from fastapi import FastAPI, Depends, HTTPException, Request
from security.auth import get_api_key
import logging

app = FastAPI()
logging.basicConfig(filename="/var/www/rabbitai/webhook.log", level=logging.INFO)

@app.post("/count-tickets", dependencies=[Depends(get_api_key)])
async def count_tickets(request: Request):
    """
    Endpoint to receive raw JSON array data containing tickets and return the count.
    """
    try:
        # Parse the incoming JSON and expect it to be a list directly
        payload = await request.json()

        # Check if payload is a list
        if not isinstance(payload, list):
            raise HTTPException(status_code=400, detail="Invalid format: Expected a JSON array of tickets.")

        # Get the count of tickets
        ticket_count = len(payload)

        return {"ticket_count": ticket_count}

    except Exception as e:
        # Log and handle unexpected errors
        raise HTTPException(status_code=500, detail=str(e))