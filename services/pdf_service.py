from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from weasyprint import HTML, CSS
import os

def generate_pdf_report(analytics: dict, filename="report.pdf"):
    """Generates a modern PDF using Jinja2 + WeasyPrint with error handling"""

    try:
        # ✅ Explicitly set the correct template directory
        template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../reporting"))
        template_env = Environment(loader=FileSystemLoader(template_dir))
        template = template_env.get_template("report_template.html")

        # Render HTML with data
        html_content = template.render(analytics=analytics)

        # Define PDF output path
        pdf_path = os.path.join("/tmp", filename)

        # Optional: Define CSS file path
        css_path = os.path.join(template_dir, "styles.css")  # Ensure this exists

        # Generate PDF from HTML with CSS
        HTML(string=html_content).write_pdf(pdf_path, stylesheets=[CSS(css_path)])

        return pdf_path

    except TemplateNotFound:
        print(f"❌ Error: The template file 'report_template.html' was not found in {template_dir}")
    except Exception as e:
        print(f"❌ PDF Generation Failed: {str(e)}")

    return None  # Return None if an error occurs
