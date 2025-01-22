from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
import os


def generate_pdf_report(analytics: dict, filename="report.pdf"):
    """Generates a modern PDF using Jinja2 + WeasyPrint"""

    # Load Jinja2 Template
    template_env = Environment(loader=FileSystemLoader("."))  # Look for templates in current directory
    template = template_env.get_template("report_template.html")

    # Render HTML with data
    html_content = template.render(analytics=analytics)

    # Define PDF output path
    pdf_path = os.path.join("/tmp", filename)

    # Generate PDF from HTML
    HTML(string=html_content).write_pdf(pdf_path)

    return pdf_path
