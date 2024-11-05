from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import os

def generate_pdf_report(analytics: dict, recommendations: list, filename="board_report.pdf"):
    # Define the PDF path
    pdf_path = os.path.join("/tmp", filename)
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Title Section
    title = Paragraph("Board-Approved Device Analytics Report", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))

    # Analytics Sections
    elements.append(Paragraph("1. Device Analytics Summary", styles['Heading1']))
    counts = analytics["counts"]

    # Integration Counts Table
    elements.append(Paragraph("1.1 Integration Counts", styles['Heading2']))
    integration_data = [["Integration", "Count"]]
    for integration, count in counts["integrations"].items():
        integration_data.append([integration, count])
    table = Table(integration_data)
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                               ('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    elements.append(table)
    elements.append(Spacer(1, 12))

    # Unique Device Counts
    elements.append(Paragraph("1.2 Unique Device Identifiers", styles['Heading2']))
    unique_data = [
        ["Attribute", "Count"],
        ["Manufacturers", len(counts["unique_manufacturers"])],
        ["Models", len(counts["unique_models"])],
        ["Serial Numbers", counts["unique_serial_numbers"]]
    ]
    unique_table = Table(unique_data)
    unique_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                                      ('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    elements.append(unique_table)
    elements.append(Spacer(1, 12))

    # Issues Section
    elements.append(Paragraph("2. Issues Detected", styles['Heading1']))
    for issue_type, issues in analytics["issues"].items():
        elements.append(Paragraph(f"{issue_type.replace('_', ' ').title()}", styles['Heading2']))
        if issues:
            issue_data = [["Device Name", "Integration IDs"]]
            for issue in issues:
                issue_data.append([issue["device_name"], issue["integration_ids"]])
            issue_table = Table(issue_data)
            issue_table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
            elements.append(issue_table)
        else:
            elements.append(Paragraph("No issues detected.", styles['Normal']))
        elements.append(Spacer(1, 12))

    # Recommendations Section
    elements.append(Paragraph("3. Recommendations", styles['Heading1']))
    for recommendation in recommendations:
        elements.append(Paragraph(f"- {recommendation}", styles['Normal']))

    # Build the PDF
    doc.build(elements)
    return pdf_path
