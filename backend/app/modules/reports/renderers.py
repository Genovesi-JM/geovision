"""Deterministic report artifact rendering from validated structured facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from io import BytesIO
from typing import Any


def _text(value: Any) -> str:
    return escape("" if value is None else str(value))


def _table_rows(items: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> list[list[str]]:
    return [[_text(item.get(field)) for field in fields] for item in items]


def render_report_pdf(
    *,
    title: str,
    report_type: str,
    revision: int,
    context: Mapping[str, Any],
    narrative: Mapping[str, Any],
) -> bytes:
    """Render numbers only from context; narrative prose is already number-free."""

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
        author="GeoVision",
        subject=report_type,
        invariant=1,
        pageCompression=0,
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            textColor=colors.HexColor("#17324D"),
            spaceAfter=8 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            parent=styles["Heading2"],
            textColor=colors.HexColor("#17324D"),
            spaceBefore=5 * mm,
            spaceAfter=2 * mm,
        )
    )
    story: list[Any] = [
        Paragraph(_text(title), styles["ReportTitle"]),
        Paragraph(
            f"{_text(report_type.replace('_', ' ').title())} | Revision {_text(revision)}",
            styles["BodyText"],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Executive summary", styles["SectionTitle"]),
        Paragraph(_text(narrative.get("executive_summary")), styles["BodyText"]),
    ]
    for section in narrative.get("sections", []):
        if not isinstance(section, Mapping):
            continue
        story.append(Paragraph(_text(section.get("heading")), styles["SectionTitle"]))
        for paragraph in section.get("paragraphs", []):
            story.extend((Paragraph(_text(paragraph), styles["BodyText"]), Spacer(1, 2 * mm)))

    asset = context.get("asset", {})
    story.extend(
        (
            Paragraph("Asset", styles["SectionTitle"]),
            Table(
                [
                    ["Name", _text(asset.get("name"))],
                    ["Sector", _text(asset.get("sector"))],
                    ["Asset type", _text(asset.get("asset_type"))],
                    ["Location", _text(asset.get("location_label") or "Unavailable")],
                    ["Evidence as of", _text(context.get("as_of"))],
                ],
                colWidths=[42 * mm, 115 * mm],
            ),
        )
    )

    table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9D9D9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7FA")]),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )

    kpis = [item for item in context.get("kpis", []) if isinstance(item, Mapping)]
    story.append(Paragraph("Validated indicators", styles["SectionTitle"]))
    if kpis:
        rows = [["Indicator", "Exact value", "Unit", "Status", "Confidence", "Measured at"]]
        rows.extend(
            _table_rows(
                kpis,
                ("name", "value", "unit", "status", "confidence", "measured_at"),
            )
        )
        table = Table(rows, repeatRows=1, colWidths=[40 * mm, 23 * mm, 17 * mm, 20 * mm, 20 * mm, 38 * mm])
        table.setStyle(table_style)
        story.append(table)
    else:
        story.append(Paragraph("No eligible indicators are available.", styles["BodyText"]))

    observations = [
        item for item in context.get("observations", []) if isinstance(item, Mapping)
    ]
    story.append(Paragraph("Validated observations", styles["SectionTitle"]))
    if observations:
        rows = [["Finding", "Severity", "Value", "Unit", "Confidence", "Detected at"]]
        rows.extend(
            [
                [
                    _text(item.get("type")),
                    _text(item.get("severity")),
                    _text(
                        item.get("numeric_value")
                        if item.get("numeric_value") is not None
                        else item.get("value")
                    ),
                    _text(item.get("unit")),
                    _text(item.get("confidence")),
                    _text(item.get("detected_at")),
                ]
                for item in observations
            ]
        )
        table = Table(rows, repeatRows=1, colWidths=[38 * mm, 20 * mm, 30 * mm, 15 * mm, 20 * mm, 35 * mm])
        table.setStyle(table_style)
        story.append(table)
    else:
        story.append(Paragraph("No validated observations are available.", styles["BodyText"]))

    actions = [item for item in context.get("actions", []) if isinstance(item, Mapping)]
    story.append(Paragraph("Evidence backed actions", styles["SectionTitle"]))
    if actions:
        rows = [["Priority", "Action", "Status", "Due date"]]
        rows.extend(_table_rows(actions, ("priority", "title", "status", "due_date")))
        table = Table(rows, repeatRows=1, colWidths=[25 * mm, 80 * mm, 25 * mm, 30 * mm])
        table.setStyle(table_style)
        story.append(table)
    else:
        story.append(Paragraph("No evidence backed open actions are available.", styles["BodyText"]))

    limitations = list(
        dict.fromkeys(
            [
                *[str(item) for item in context.get("limitations", [])],
                *[str(item) for item in narrative.get("limitations", [])],
            ]
        )
    )
    if limitations:
        story.append(PageBreak())
        story.append(Paragraph("Limitations", styles["SectionTitle"]))
        for item in limitations:
            story.append(Paragraph(f"&#8226; {_text(item)}", styles["BodyText"]))

    document.build(story, canvasmaker=canvas.Canvas)
    payload = output.getvalue()
    if not payload.startswith(b"%PDF-"):
        raise RuntimeError("report renderer did not produce a PDF")
    return payload


__all__ = ["render_report_pdf"]
