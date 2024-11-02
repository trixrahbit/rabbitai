from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os

def generate_pdf(data: list[dict], filename="report.pdf"):
    pdf_path = os.path.join("/tmp", filename)
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter

    c.drawString(100, height - 50, "Aggregated Report")
    y_position = height - 100
    for record in data:
        c.drawString(100, y_position, str(record))
        y_position -= 20

    c.save()
    return pdf_path
