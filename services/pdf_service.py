from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import os


def generate_pdf_report(analytics: dict, recommendations: dict, filename="report.pdf"):
    pdf_path = os.path.join("/tmp", filename)
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    elements.append(Paragraph("Board-Approved Report", styles['Title']))
    elements.append(Spacer(1, 0.2 * inch))

    # Manufacturers Section
    elements.append(Paragraph("Manufacturers Count", styles['Heading2']))
    manufacturers_data = [["Manufacturer", "Count"]] + [[name, count] for name, count in
                                                        analytics["counts"]["unique_manufacturers"].items()]
    manufacturers_table = Table(manufacturers_data, colWidths=[3 * inch, 2 * inch])
    manufacturers_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(manufacturers_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Integration Matches Section
    elements.append(Paragraph("Integration Matches", styles['Heading2']))
    integration_data = [["Device Name", "Matched Integrations"]]
    for match in analytics["integration_matches"]:
        device_name = match["device_name"]
        matched_integrations = ", ".join(match["matched_integrations"])
        integration_data.append([device_name, matched_integrations])
    integration_table = Table(integration_data, colWidths=[3 * inch, 3 * inch])
    integration_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightyellow),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(integration_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Missing Integrations Section
    elements.append(Paragraph("Missing Integrations", styles['Heading2']))
    missing_integrations_data = [["Device Name", "Missing Integrations"]]
    for device_name, missing_list in analytics["missing_integrations"].items():
        missing_integrations_data.append([device_name, ", ".join(missing_list)])
    missing_integrations_table = Table(missing_integrations_data, colWidths=[3 * inch, 3 * inch])
    missing_integrations_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightpink),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(missing_integrations_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Trends Section
    elements.append(Paragraph("Device Trends", styles['Heading2']))
    trends_data = [
        ["Recently Active Devices", analytics["trends"]["recently_active_devices"]],
        ["Recently Inactive Devices", analytics["trends"]["recently_inactive_devices"]]
    ]
    trends_table = Table(trends_data, colWidths=[4 * inch, 2 * inch])
    trends_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(trends_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Recommendations and Strategic Plan
    elements.append(Paragraph("Device Recommendations", styles['Heading2']))
    if recommendations.get("device_recommendations"):
        for rec in recommendations["device_recommendations"]:
            elements.append(Paragraph(rec, styles['BodyText']))
            elements.append(Spacer(1, 0.1 * inch))
    else:
        elements.append(Paragraph("No recommendations available.", styles['BodyText']))

    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph("Strategic Plan", styles['Heading2']))
    if recommendations.get("strategic_plan"):
        for strategy in recommendations["strategic_plan"]:
            elements.append(Paragraph(strategy, styles['BodyText']))
            elements.append(Spacer(1, 0.1 * inch))
    else:
        elements.append(Paragraph("No strategic plan details available.", styles['BodyText']))

    # Build and save PDF
    doc.build(elements)
    return pdf_path
