from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from weasyprint import HTML, CSS
import os

def generate_pdf_report(analytics, filename="report.pdf"):
    """Generates a modern PDF using Jinja2 + WeasyPrint with error handling"""

    try:
        # ✅ Debugging Step: Print structure of analytics
        print(f"DEBUG: Type of analytics -> {type(analytics)}")
        print(f"DEBUG: analytics content -> {json.dumps(analytics, indent=2)}")

        if not isinstance(analytics, dict):
            raise ValueError(f"Expected 'analytics' to be a dictionary, but got {type(analytics).__name__}")

        # Define the template directory
        template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../reporting"))
        template_env = Environment(loader=FileSystemLoader(template_dir))
        template = template_env.get_template("report_template.html")

        # Render HTML with data
        html_content = template.render(analytics=analytics)

        # Define PDF output path
        pdf_path = os.path.join("/tmp", filename)

        # Generate PDF from HTML
        HTML(string=html_content).write_pdf(pdf_path)

        return pdf_path

    except ValueError as ve:
        print(f"❌ ValueError: {ve}")
    except TemplateNotFound:
        print(f"❌ Error: The template file 'report_template.html' was not found in {template_dir}")
    except Exception as e:
        print(f"❌ PDF Generation Failed: {str(e)}")

    return None  # Return None if an error occurs

