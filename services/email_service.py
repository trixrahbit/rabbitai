from msal import ConfidentialClientApplication
import requests
import base64
from config import settings

def get_access_token():
    app = ConfidentialClientApplication(
        client_id=settings.CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{settings.TENANT_ID}",
        client_credential=settings.CLIENT_SECRET
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return result.get("access_token")

def send_email_with_pdf(to_address: str, pdf_path: str):
    access_token = get_access_token()

    with open(pdf_path, "rb") as f:
        pdf_content = base64.b64encode(f.read()).decode("utf-8")

    email_data = {
        "message": {
            "subject": "Your Aggregated Report",
            "body": {
                "contentType": "Text",
                "content": "Please find attached the requested report."
            },
            "toRecipients": [{"emailAddress": {"address": to_address}}],
            "attachments": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "report.pdf",
                    "contentBytes": pdf_content
                }
            ]
        }
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    response = requests.post(
        "https://graph.microsoft.com/v1.0/me/sendMail",
        headers=headers,
        json=email_data
    )
    return response.status_code == 202
