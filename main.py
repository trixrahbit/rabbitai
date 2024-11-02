from fastapi import FastAPI, Depends, HTTPException, Request
from security.auth import get_api_key
import logging

app = FastAPI()
logging.basicConfig(filename="/var/www/rabbitai/webhook.log", level=logging.INFO)

@app.post("/count-tickets", dependencies=[Depends(get_api_key)])
async def count_tickets(request: Request):
    try:
        # Parse the incoming JSON
        payload = await request.json()
        logging.info("Received payload: %s", payload)  # Log incoming payload

        # Ensure 'data' key exists and is a list
        if "data" not in payload or not isinstance(payload["data"], list):
            raise HTTPException(status_code=400, detail="Invalid format: 'data' should be a list of tickets.")

        # Get the count of tickets
        ticket_count = len(payload["data"])

        return {"ticket_count": ticket_count}

    except Exception as e:
        logging.error("Error processing request: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
