from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from io import BytesIO


def build_device_pdf(device, site, company, readings, alerts, start: datetime, end: datetime) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = BytesIO(); styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm, title=f"GeoVision sensor report — {device.name}")
    story = [Paragraph("GeoVision Operational Intelligence", styles["Title"]), Paragraph(f"Sensor monitoring report · {device.name}", styles["Heading2"]), Spacer(1, 6)]
    story.append(Table([
        ["Customer", company.name if company else device.company_id], ["Site", site.name if site else device.site_id],
        ["Device UID", device.public_id], ["Period", f"{start.isoformat()}Z — {end.isoformat()}Z"],
        ["Status", device.status], ["Generated", datetime.utcnow().isoformat() + "Z"],
    ], colWidths=[42*mm, 120*mm], style=[("GRID",(0,0),(-1,-1),.25,colors.HexColor("#cbd5e1")),("BACKGROUND",(0,0),(0,-1),colors.HexColor("#e2e8f0")),("VALIGN",(0,0),(-1,-1),"TOP")]))
    grouped = defaultdict(list)
    for row in readings:
        if row.numeric_value is not None: grouped[row.channel].append(float(row.numeric_value))
    metrics = [["Channel", "Samples", "Minimum", "Maximum", "Average", "Unit"]]
    for channel, values in sorted(grouped.items()):
        unit = next((r.unit for r in readings if r.channel == channel), "") or ""
        metrics.append([channel, len(values), f"{min(values):.2f}", f"{max(values):.2f}", f"{sum(values)/len(values):.2f}", unit])
    story += [Spacer(1, 12), Paragraph("Measurements", styles["Heading2"]), Table(metrics, repeatRows=1, style=[("GRID",(0,0),(-1,-1),.25,colors.HexColor("#cbd5e1")),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0f172a")),("TEXTCOLOR",(0,0),(-1,0),colors.white)])]
    incident_rows = [["Opened", "Severity", "Channel", "Status", "Message"]] + [[a.opened_at.isoformat(), a.severity, a.channel, a.status, a.message] for a in alerts]
    story += [Spacer(1, 12), Paragraph("Alert and incident timeline", styles["Heading2"]), Table(incident_rows, repeatRows=1, colWidths=[30*mm,18*mm,25*mm,22*mm,72*mm], style=[("GRID",(0,0),(-1,-1),.25,colors.HexColor("#cbd5e1")),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0f172a")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTSIZE",(0,0),(-1,-1),7),("VALIGN",(0,0),(-1,-1),"TOP")])]
    story += [Spacer(1, 12), Paragraph("Operational recommendation", styles["Heading2"]), Paragraph("Review unresolved alerts, inspect poor-quality channels, confirm local safety interlocks before sending any output command, and schedule calibration according to the sensor manufacturer’s interval.", styles["BodyText"])]
    doc.build(story); return output.getvalue()
