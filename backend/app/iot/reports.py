from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from io import BytesIO

# ── Shared PDF scaffolding (used by device reports and construction inspections) ──
# reportlab is imported lazily inside the helpers so importing this module stays cheap
# and optional for callers that never render a PDF.

_GRID = 0.25


def report_doc(title: str):
    """Return (output_buffer, SimpleDocTemplate, styles) with GeoVision page setup."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    output = BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title=title)
    return output, doc, styles


def meta_table(rows, col_mm=(46, 116)):
    """Two-column key/value table with a light header column."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Table
    return Table(rows, colWidths=[c * mm for c in col_mm],
                 style=[("GRID", (0, 0), (-1, -1), _GRID, colors.HexColor("#cbd5e1")),
                        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e2e8f0")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP")])


def data_table(rows, col_mm=None, font_size=None):
    """Table with a dark header row (for measurement / timeline / KPI grids)."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Table
    style = [("GRID", (0, 0), (-1, -1), _GRID, colors.HexColor("#cbd5e1")),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
             ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if font_size:
        style.append(("FONTSIZE", (0, 0), (-1, -1), font_size))
    kwargs = {"repeatRows": 1, "style": style}
    if col_mm:
        kwargs["colWidths"] = [c * mm for c in col_mm]
    return Table(rows, **kwargs)


def build_device_pdf(device, site, company, readings, alerts, start: datetime, end: datetime, analytics: dict | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Spacer, Table

    output, doc, styles = report_doc(f"GeoVision sensor report — {device.name}")
    story = [Paragraph("GeoVision Operational Intelligence", styles["Title"]),
             Paragraph(f"Sensor monitoring report · {device.name}", styles["Heading2"]), Spacer(1, 6)]
    story.append(meta_table([
        ["Customer", company.name if company else device.company_id], ["Site", site.name if site else device.site_id],
        ["Device UID", device.public_id], ["Period", f"{start.isoformat()}Z — {end.isoformat()}Z"],
        ["Status", device.status], ["Generated", datetime.utcnow().isoformat() + "Z"],
    ], col_mm=(42, 120)))
    grouped = defaultdict(list)
    for row in readings:
        if row.numeric_value is not None:
            grouped[row.channel].append(float(row.numeric_value))
    metrics = [["Channel", "Samples", "Minimum", "Maximum", "Average", "Unit"]]
    for channel, values in sorted(grouped.items()):
        unit = next((r.unit for r in readings if r.channel == channel), "") or ""
        metrics.append([channel, len(values), f"{min(values):.2f}", f"{max(values):.2f}", f"{sum(values)/len(values):.2f}", unit])
    story += [Spacer(1, 12), Paragraph("Measurements", styles["Heading2"]), data_table(metrics)]
    incident_rows = [["Opened", "Severity", "Channel", "Status", "Message"]] + [[a.opened_at.isoformat(), a.severity, a.channel, a.status, a.message] for a in alerts]
    story += [Spacer(1, 12), Paragraph("Alert and incident timeline", styles["Heading2"]), data_table(incident_rows, col_mm=(30, 18, 25, 22, 72), font_size=7)]
    if analytics:
        ov = analytics.get("overview", {}); inc = analytics.get("incidents", {})
        kpi_rows = [
            ["Total readings", ov.get("total_readings", 0), "Channels reporting", ov.get("channels_reporting", 0)],
            ["Data completeness", f"{ov.get('completeness_pct')}%" if ov.get("completeness_pct") is not None else "n/a", "Data span", f"{int((ov.get('data_span_ratio') or 0)*100)}%"],
            ["Incidents", inc.get("total", 0), "Open", inc.get("open", 0)],
            ["MTTA (s)", inc.get("mtta_seconds") if inc.get("mtta_seconds") is not None else "n/a", "MTTR (s)", inc.get("mttr_seconds") if inc.get("mttr_seconds") is not None else "n/a"],
        ]
        from reportlab.lib.units import mm
        story += [Spacer(1, 12), Paragraph("Analytical KPIs", styles["Heading2"]),
                  Table(kpi_rows, colWidths=[42*mm, 39*mm, 42*mm, 39*mm],
                        style=[("GRID", (0, 0), (-1, -1), _GRID, colors.HexColor("#cbd5e1")),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e2e8f0")),
                               ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#e2e8f0"))])]
        analytic_metrics = [["Channel", "In-range %", "Duty %", "Est. run-hrs", "Bad samples"]]
        for s in analytics.get("channels", []):
            tir = f"{s['time_in_range_pct']}" if s.get("time_in_range_pct") is not None else "—"
            duty = f"{round(s['on_ratio']*100)}" if s.get("on_ratio") is not None else "—"
            runh = f"{s['estimated_on_hours']}" if s.get("estimated_on_hours") is not None else "—"
            analytic_metrics.append([s["channel"], tir, duty, runh, s.get("bad_quality_samples", 0)])
        if len(analytic_metrics) > 1:
            story += [Spacer(1, 8), data_table(analytic_metrics, font_size=7)]

    recommendations = (analytics or {}).get("recommendations") or [
        "Review unresolved alerts, inspect poor-quality channels, confirm local safety interlocks before sending any output command, and schedule calibration according to the sensor manufacturer’s interval.",
    ]
    story += [Spacer(1, 12), Paragraph("Data-driven recommendations", styles["Heading2"])]
    story += [Paragraph(f"• {rec}", styles["BodyText"]) for rec in recommendations]
    doc.build(story)
    return output.getvalue()
