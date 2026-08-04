from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from io import BytesIO


def build_device_pdf(device, site, company, readings, alerts, start: datetime, end: datetime, analytics: dict | None = None) -> bytes:
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
    if analytics:
        ov = analytics.get("overview", {}); inc = analytics.get("incidents", {})
        kpi_rows = [
            ["Total readings", ov.get("total_readings", 0), "Channels reporting", ov.get("channels_reporting", 0)],
            ["Data completeness", f"{ov.get('completeness_pct')}%" if ov.get("completeness_pct") is not None else "n/a", "Data span", f"{int((ov.get('data_span_ratio') or 0)*100)}%"],
            ["Incidents", inc.get("total", 0), "Open", inc.get("open", 0)],
            ["MTTA (s)", inc.get("mtta_seconds") if inc.get("mtta_seconds") is not None else "n/a", "MTTR (s)", inc.get("mttr_seconds") if inc.get("mttr_seconds") is not None else "n/a"],
        ]
        story += [Spacer(1, 12), Paragraph("Analytical KPIs", styles["Heading2"]), Table(kpi_rows, colWidths=[42*mm,39*mm,42*mm,39*mm], style=[("GRID",(0,0),(-1,-1),.25,colors.HexColor("#cbd5e1")),("BACKGROUND",(0,0),(0,-1),colors.HexColor("#e2e8f0")),("BACKGROUND",(2,0),(2,-1),colors.HexColor("#e2e8f0"))])]
        analytic_metrics = [["Channel", "In-range %", "Duty %", "Est. run-hrs", "Bad samples"]]
        for s in analytics.get("channels", []):
            tir = f"{s['time_in_range_pct']}" if s.get("time_in_range_pct") is not None else "—"
            duty = f"{round(s['on_ratio']*100)}" if s.get("on_ratio") is not None else "—"
            runh = f"{s['estimated_on_hours']}" if s.get("estimated_on_hours") is not None else "—"
            analytic_metrics.append([s["channel"], tir, duty, runh, s.get("bad_quality_samples", 0)])
        if len(analytic_metrics) > 1:
            story += [Spacer(1, 8), Table(analytic_metrics, repeatRows=1, style=[("GRID",(0,0),(-1,-1),.25,colors.HexColor("#cbd5e1")),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0f172a")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTSIZE",(0,0),(-1,-1),7)])]

    recommendations = (analytics or {}).get("recommendations") or [
        "Review unresolved alerts, inspect poor-quality channels, confirm local safety interlocks before sending any output command, and schedule calibration according to the sensor manufacturer’s interval.",
    ]
    story += [Spacer(1, 12), Paragraph("Data-driven recommendations", styles["Heading2"])]
    story += [Paragraph(f"• {rec}", styles["BodyText"]) for rec in recommendations]
    doc.build(story); return output.getvalue()
