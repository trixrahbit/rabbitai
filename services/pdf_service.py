from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from collections import Counter
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
import os

# Register a custom font if desired
pdfmetrics.registerFont(TTFont('Helvetica', 'Helvetica.ttf'))

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
    elements.append(Spacer(1, 0.02 * inch))

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
    manufacturers_table = Table(manufacturers_data, colWidths=[4 * inch, 1.5 * inch])
    manufacturers_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.4, 0.6)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(manufacturers_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Integration Matches Section
    add_section_header(elements, "Integration Matches", color=colors.green)
    integration_data = [["Device Name", "Matched Integrations"]]
    for match in analytics["integration_matches"]:
        device_name = match["device_name"]
        matched_integrations = ", ".join(match["matched_integrations"])
        integration_data.append([device_name, matched_integrations])
    integration_table = Table(integration_data, colWidths=[3 * inch, 3 * inch])
    integration_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.3, 0.5, 0.3)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.Color(0.9, 0.9, 0.9)),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 1), (-1, -1), 8 if len(matched_integrations) > 50 else 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(integration_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Missing Integrations Section
    add_section_header(elements, "Missing Integrations", color=colors.red)
    missing_integrations_data = [["Device Name", "Missing Integrations"]]
    for device_name, missing_list in analytics["missing_integrations"].items():
        missing_text = ", ".join(missing_list)
        missing_integrations_data.append([device_name, missing_text])
    missing_integrations_table = Table(missing_integrations_data, colWidths=[3 * inch, 3 * inch])
    missing_integrations_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.8, 0.2, 0.2)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.Color(0.95, 0.9, 0.9)),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 1), (-1, -1), 8 if len(missing_text) > 50 else 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(missing_integrations_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Trends Section
    add_section_header(elements, "Device Trends", color=colors.purple)
    trends_data = [
        ["Recently Active Devices", analytics["trends"]["recently_active_devices"]],
        ["Recently Inactive Devices", analytics["trends"]["recently_inactive_devices"]]
    ]
    trends_table = Table(trends_data, colWidths=[4 * inch, 2 * inch])
    trends_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.5, 0.4, 0.6)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.Color(0.95, 0.95, 0.9)),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(trends_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Expiring Warranties Section
    add_section_header(elements, "Expiring Warranties", color=colors.orange)
    expiring_warranties_data = [["Device Name", "Warranty Expiration Date"]]
    for device in analytics["issues"]["expired_warranty"]:
        device_name = device["device_name"]
        warranty_date = device.get("warranty_date", "N/A")
        expiring_warranties_data.append([device_name, warranty_date])
    expiring_warranties_table = Table(expiring_warranties_data, colWidths=[3 * inch, 3 * inch])
    expiring_warranties_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.8, 0.6, 0.2)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightyellow),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(expiring_warranties_table)
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
