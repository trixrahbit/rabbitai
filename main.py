from fastapi import FastAPI, Depends, HTTPException
from config import settings
from models import DataAggregationRequest, EmailRequest
from security.auth import get_api_key
from services.pdf_service import generate_pdf
from services.email_service import send_email_with_pdf

app = FastAPI()

@app.post("/aggregate-data", dependencies=[Depends(get_api_key)])
async def aggregate_data(request: DataAggregationRequest):
    """
    Endpoint to receive JSON data, aggregate it, and generate a PDF report.
    """
    pdf_path = generate_pdf(request.data)  # Generate PDF with aggregated data
    return {"message": "Data aggregated and PDF generated", "pdf_path": pdf_path}

@app.post("/generate-pdf-email", dependencies=[Depends(get_api_key)])
async def generate_pdf_and_email(request: EmailRequest):
    """
    Endpoint to send an aggregated PDF report via email.
    """
    pdf_path = "/tmp/report.pdf"  # Path to previously generated PDF (or re-generate if needed)
    if not send_email_with_pdf(request.email, pdf_path):
        raise HTTPException(status_code=500, detail="Failed to send email")
    return {"message": "PDF generated and email sent successfully"}
