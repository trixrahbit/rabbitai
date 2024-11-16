from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from collections import Counter
import os

def add_section_header(elements, title, color=colors.darkblue):
    """Utility function to add a styled section header."""
    elements.append(Spacer(1, 0.1 * inch))
    header_style = ParagraphStyle(
        name="HeaderStyle",
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=color,
        spaceAfter=10
    )
    elements.append(Paragraph(title, header_style))
    elements.append(Spacer(1, 0.05 * inch))

def create_wrapped_table(data, col_widths):
    """Creates a table with wrapped text cells to prevent overflow."""
    table_data = [[Paragraph(cell, getSampleStyleSheet()["BodyText"]) if isinstance(cell, str) else cell for cell in row] for row in data]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
    ]))
    return table

def generate_pdf_report(analytics: dict, recommendations: dict, filename="report.pdf"):
    pdf_path = os.path.join("/tmp", filename)
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    title_style = ParagraphStyle(
        'TitleStyle', fontSize=18, textColor=colors.darkblue, alignment=1, fontName="Helvetica-Bold"
    )
    elements.append(Paragraph("Rabbit Reporting v1.0", title_style))
    elements.append(Spacer(1, 0.3 * inch))

    # Manufacturers Section with Counts
    add_section_header(elements, "Manufacturers Count", color=colors.Color(0.2, 0.4, 0.6))
    manufacturer_counts = Counter(analytics["counts"]["unique_manufacturers"])
    manufacturers_data = [["Manufacturer", "Count"]] + [[name, count] for name, count in manufacturer_counts.items()]
    elements.append(create_wrapped_table(manufacturers_data, col_widths=[4 * inch, 1.5 * inch]))
    elements.append(Spacer(1, 0.2 * inch))

    # Integration Matches Section
    add_section_header(elements, "Integration Matches", color=colors.green)
    integration_data = [["Device Name", "Matched Integrations"]]
    for match in analytics["integration_matches"]:
        device_name = match["device_name"]
        matched_integrations = ", ".join(match["matched_integrations"])
        integration_data.append([device_name, matched_integrations])
    elements.append(create_wrapped_table(integration_data, col_widths=[3 * inch, 3 * inch]))
    elements.append(Spacer(1, 0.2 * inch))

    # Missing Integrations Section
    add_section_header(elements, "Missing Integrations", color=colors.red)
    missing_integrations_data = [["Device Name", "Missing Integrations"]]
    for device_name, missing_list in analytics["missing_integrations"].items():
        missing_text = ", ".join(missing_list)
        missing_integrations_data.append([device_name, missing_text])
    elements.append(create_wrapped_table(missing_integrations_data, col_widths=[3 * inch, 3 * inch]))
    elements.append(Spacer(1, 0.2 * inch))

    # Trends Section
    add_section_header(elements, "Device Trends", color=colors.purple)
    trends_data = [
        ["Recently Active Devices", analytics["trends"]["recently_active_devices"]],
        ["Recently Inactive Devices", analytics["trends"]["recently_inactive_devices"]]
    ]
    elements.append(create_wrapped_table(trends_data, col_widths=[4 * inch, 2 * inch]))
    elements.append(Spacer(1, 0.2 * inch))

    # Expiring Warranties Section
    add_section_header(elements, "Expiring Warranties", color=colors.orange)
    expiring_warranties_data = [["Device Name", "Warranty Expiration Date"]]
    for device in analytics["issues"]["expired_warranty"]:
        device_name = device["device_name"]
        warranty_date = device.get("warranty_date", "N/A")
        expiring_warranties_data.append([device_name, warranty_date])
    elements.append(create_wrapped_table(expiring_warranties_data, col_widths=[3 * inch, 3 * inch]))
    elements.append(Spacer(1, 0.2 * inch))

    # Recommendations and Strategic Plan
    add_section_header(elements, "Device Recommendations", color=colors.navy)
    if recommendations.get("device_recommendations"):
        for rec in recommendations["device_recommendations"]:
            issue_type = rec.get("issue_type", "General Issue")
            elements.append(Paragraph(f"<b>{issue_type}</b>", styles['Heading3']))
            rec_text = ", ".join([f"{key}: {value}" for key, value in rec.items() if key != "issue_type"])
            elements.append(Paragraph(rec_text, styles['BodyText']))
            elements.append(Spacer(1, 0.1 * inch))
    else:
        elements.append(Paragraph("No recommendations available.", styles['BodyText']))

    add_section_header(elements, "Strategic Plan", color=colors.teal)
    if recommendations.get("strategic_plan"):
        for strategy in recommendations["strategic_plan"]:
            elements.append(Paragraph("<b>Action Item:</b>", styles['Heading3']))
            strategy_text = ", ".join([f"{key}: {value}" for key, value in strategy.items()])
            elements.append(Paragraph(strategy_text, styles['BodyText']))
            elements.append(Spacer(1, 0.1 * inch))
    else:
        elements.append(Paragraph("No strategic plan details available.", styles['BodyText']))

    # Build and save PDF
    doc.build(elements)
    return pdf_path
