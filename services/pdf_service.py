from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from collections import Counter
import os

def add_section_header(elements, title, color=colors.darkblue, icon=None):
    elements.append(Spacer(1, 0.2 * inch))
    header_style = ParagraphStyle(
        name="HeaderStyle",
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=color,
        spaceAfter=12
    )
    icon_html = f'<img src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/svg/{icon}.svg" width="16" height="16" />' if icon else ""
    elements.append(Paragraph(f"{icon_html} {title}", header_style))
    elements.append(Spacer(1, 0.1 * inch))

def create_wrapped_table(data, col_widths):
    table_data = [[Paragraph(str(cell), getSampleStyleSheet()["BodyText"]) if isinstance(cell, str) else cell for cell in row] for row in data]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
    ]))
    return table

def generate_pdf_report(analytics: dict, recommendations: dict, filename="report.pdf"):
    pdf_path = os.path.join("/tmp", filename)
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle', fontSize=20, textColor=colors.darkblue, alignment=1, fontName="Helvetica-Bold"
    )
    elements.append(Paragraph("Rabbit Reporting v2.0", title_style))
    elements.append(Spacer(1, 0.4 * inch))

    add_section_header(elements, "Manufacturers Count", color=colors.blue, icon="industry")
    manufacturer_counts = Counter(analytics["counts"]["unique_manufacturers"])
    manufacturers_data = [["Manufacturer", "Count"]] + [[name, count] for name, count in manufacturer_counts.items()]
    elements.append(create_wrapped_table(manufacturers_data, col_widths=[4 * inch, 1.5 * inch]))
    elements.append(Spacer(1, 0.3 * inch))

    add_section_header(elements, "Integration Matches", color=colors.green, icon="link")
    integration_data = [["Device Name", "Matched Integrations"]]
    for match in analytics["integration_matches"]:
        integration_data.append([match["device_name"], ", ".join(match["matched_integrations"])] )
    elements.append(create_wrapped_table(integration_data, col_widths=[3 * inch, 3 * inch]))
    elements.append(Spacer(1, 0.3 * inch))

    add_section_header(elements, "Missing Integrations", color=colors.red, icon="unlink")
    missing_integrations_data = [["Device Name", "Missing Integrations"]]
    for device_name, missing_list in analytics["missing_integrations"].items():
        missing_integrations_data.append([device_name, ", ".join(missing_list)])
    elements.append(create_wrapped_table(missing_integrations_data, col_widths=[3 * inch, 3 * inch]))
    elements.append(Spacer(1, 0.3 * inch))

    add_section_header(elements, "Device Recommendations", color=colors.navy, icon="lightbulb")
    if recommendations.get("device_recommendations"):
        for rec in recommendations["device_recommendations"]:
            elements.append(Paragraph(f"<b>{rec.get('issue_type', 'General Issue')}</b>", styles['Heading3']))
            rec_text = ", ".join([f"{key}: {value}" for key, value in rec.items() if key != "issue_type"])
            elements.append(Paragraph(rec_text, styles['BodyText']))
            elements.append(Spacer(1, 0.1 * inch))
    else:
        elements.append(Paragraph("No recommendations available.", styles['BodyText']))

    doc.build(elements)
    return pdf_path
