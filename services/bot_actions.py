import logging
import httpx
from fastapi import HTTPException
from config import settings

# Configure logging to capture detailed information
logging.basicConfig(
    level=logging.DEBUG,  # Use DEBUG for detailed logs
    format="%(asctime)s - %(levelname)s - %(message)s"
)


async def get_bot_token():
    """Fetches a bot authentication token from Microsoft."""
    url = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.BOT_CLIENT_ID,
        "client_secret": settings.BOT_CLIENT_SECRET,
        "scope": "https://api.botframework.com/.default"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    logging.debug(f"[get_bot_token] Requesting bot token from: {url}")
    logging.debug(f"[get_bot_token] Payload: {payload}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=payload, headers=headers)
            response.raise_for_status()

            token_data = response.json()
            logging.info(f"[get_bot_token] Token acquired successfully.")
            logging.debug(f"[get_bot_token] Full token response: {token_data}")

            return token_data["access_token"]

    except httpx.HTTPStatusError as e:
        logging.error(f"[get_bot_token] HTTP Error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=401, detail="Failed to authenticate bot.")
    except Exception as e:
        logging.critical(f"[get_bot_token] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected error fetching bot token.")


async def send_message_to_teams(service_url, conversation_id, user_upn, adaptive_card):
    """Sends an Adaptive Card message to Microsoft Teams."""
    logging.info(f"[send_message_to_teams] Preparing to send message to Teams.")
    logging.debug(f"[send_message_to_teams] service_url: {service_url}")
    logging.debug(f"[send_message_to_teams] conversation_id: {conversation_id}")
    logging.debug(f"[send_message_to_teams] user_upn: {user_upn}")
    logging.debug(f"[send_message_to_teams] Adaptive Card: {adaptive_card}")

    try:
        # Step 1: Fetch bot token
        logging.info("[send_message_to_teams] Fetching bot token...")
        token = await get_bot_token()

        # Step 2: Construct URL for Teams API
        url = f"{service_url}/v3/conversations/{conversation_id}/activities"
        logging.debug(f"[send_message_to_teams] Target URL: {url}")

        # Step 3: Build payload
        payload = {
            "type": "message",
            "conversation": {"isGroup": False},
            "recipient": {"id": user_upn},
            "from": {
                "id": "28:431fa8f7-defa-4136-9be9-3e446a00027b",
                "name": "Rabbot"
            },
            "channelData": {
                "tenant": {"id": "c89aa4c2-4436-410b-8410-35695c2a9f30"}
            },
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": adaptive_card
                }
            ]
        }
        logging.debug(f"[send_message_to_teams] Final Payload: {payload}")

        # Step 4: Send POST request
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        logging.info("[send_message_to_teams] Sending message to Teams...")

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            logging.info("[send_message_to_teams] Message successfully sent to Teams!")
            logging.debug(f"[send_message_to_teams] Response Status: {response.status_code}")
            logging.debug(f"[send_message_to_teams] Response Body: {response.text}")

            return response.json()

    except httpx.HTTPStatusError as e:
        logging.error(f"[send_message_to_teams] HTTP Error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail="Failed to send message to Teams.")
    except Exception as e:
        logging.critical(f"[send_message_to_teams] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected error while sending message to Teams.")
