import logging

import httpx
from fastapi import HTTPException

from config import settings


async def get_bot_token():
    url = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.BOT_CLIENT_ID,
        "client_secret": settings.BOT_CLIENT_SECRET,
        "scope": "https://api.botframework.com/.default"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        async with httpx.AsyncClient() as client:
            logging.info(f"Token request payload: {payload}")
            response = await client.post(url, data=payload, headers=headers)
            response.raise_for_status()
            token_data = response.json()
            logging.info(f"Token acquired: {token_data}")
            return token_data["access_token"]
    except httpx.HTTPStatusError as e:
        logging.error(f"Failed to acquire token: {e.response.text}")
        raise HTTPException(status_code=401, detail="Failed to authenticate bot.")


async def send_message_to_teams(service_url, conversation_id, user_upn, adaptive_card):
    # Step 1: Get the bot token
    token = await get_bot_token()

    # Step 2: Build the URL
    url = f"{service_url}/v3/conversations/{conversation_id}/activities"

    # Step 3: Construct the payload
    payload = {
        "type": "message",
        "conversation": {
            "isGroup": False
        },
        "recipient": {
            "id": user_upn
        },
        "from": {
            "id": "28:431fa8f7-defa-4136-9be9-3e446a00027b",
            "name": "Rabbot"
        },
        "channelData": {
            "tenant": {
                "id": "c89aa4c2-4436-410b-8410-35695c2a9f30"
            }
        },
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": adaptive_card
            }
        ]
    }
    logging.info(f"Payload to Teams: {payload}")

    # Step 4: Send the POST request
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
