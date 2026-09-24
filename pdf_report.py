# -*- coding: utf-8 -*-
"""RAPKP v26 PDF chart report generator."""
from io import BytesIO
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)


def _p(text):
    return str(text if text is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _table(data, widths=None, font=8, header=True):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), font),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9ca3af")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    for r in range(1 if header else 0, len(data)):
        if r % 2 == 0:
            style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f8fafc")))
    t.setStyle(TableStyle(style))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(16 * mm, 10 * mm, "RAPKP v26 MASTER - MIT openephem / JPL DE421 - For research and decision support")
    canvas.drawRightString(194 * mm, 10 * mm, "Page %d" % doc.page)
    canvas.restoreState()


def make_chart_pdf(payload):
    """Return PDF bytes for chart_payload()."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=13 * mm, bottomMargin=15 * mm,
        title="RAPKP v26 Chart Report",
        author="RAPKP v26"
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CenterTitle", parent=styles["Title"], alignment=TA_CENTER,
                              fontName="Helvetica-Bold", fontSize=18, leading=22,
                              textColor=colors.HexColor("#4c1d95")))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8, leading=10,
                              textColor=colors.HexColor("#475569")))
    styles.add(ParagraphStyle(name="H", parent=styles["Heading2"], fontName="Helvetica-Bold",
                              fontSize=12, leading=14, textColor=colors.HexColor("#111827")))
    story = []
    person = payload.get("person", {})

    story.append(Paragraph("RAPKP v26 MASTER - KP Chart PDF Report", styles["CenterTitle"]))
    story.append(Paragraph("Generated: %s UTC" % datetime.now(timezone.utc).isoformat(timespec="seconds"), styles["Small"]))
    story.append(Spacer(1, 6))

    summary = [
        ["Name", _p(person.get("name")), "Place", _p(person.get("place", ""))],
        ["DOB / TOB", "%s %s" % (_p(person.get("dob")), _p(person.get("tob"))), "TZ", _p(person.get("tz"))],
        ["Lat / Lon", "%s / %s" % (_p(person.get("lat")), _p(person.get("lon"))), "House", _p(payload.get("house_system"))],
        ["Ascendant", "%s (%s)" % (_p(payload.get("asc_dms")), _p(payload.get("asc_sign"))), "Moon", "%s %s P%s" % (_p(payload.get("moon_sign")), _p(payload.get("moon_nakshatra")), _p(payload.get("moon_pada")))],
        ["Ayanamsa", "%s - %s" % (_p(payload.get("ayanamsa_dms")), _p(payload.get("ayanamsa_label"))), "Calc", "%s / %s" % (_p(payload.get("calculator")), _p(payload.get("position")))],
    ]
    story.append(_table(summary, widths=[28*mm, 63*mm, 25*mm, 62*mm], font=8, header=False))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Planets - Sign, Nakshatra, Pada, KP Star/Sub/Sub-Sub", styles["H"]))
    pdata = [["Planet", "Longitude", "Sign", "Nakshatra", "P", "House", "Star", "Sub", "Sub-Sub", "R"]]
    for p in payload.get("planets", []):
        pdata.append([_p(p.get("name")), _p(p.get("dms")), _p(p.get("sign")), _p(p.get("nak")),
                      _p(p.get("pada")), _p(p.get("house")), _p(p.get("star")),
                      _p(p.get("sub")), _p(p.get("sub_sub")), "R" if p.get("retro") else ""])
    story.append(_table(pdata, widths=[20*mm, 25*mm, 22*mm, 31*mm, 8*mm, 12*mm, 18*mm, 18*mm, 19*mm, 7*mm], font=7))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Cusps - Placidus KP Sub-Lords", styles["H"]))
    cdata = [["Cusp", "Longitude", "Sign", "Degree in Sign", "Sub-Lord"]]
    for c in payload.get("cusps", []):
        cdata.append([_p(c.get("c")), _p(c.get("dms")), _p(c.get("sign")), _p(c.get("deg")), _p(c.get("sub"))])
    story.append(_table(cdata, widths=[16*mm, 40*mm, 35*mm, 35*mm, 35*mm], font=8))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Vimshottari Dasha", styles["H"]))
    v = payload.get("vimshottari", {})
    cur = v.get("current", {})
    story.append(Paragraph("Current: <b>%s / %s / %s</b> &nbsp;&nbsp; Balance at birth: <b>%s years of %s</b>" % (
        _p(cur.get("maha")), _p(cur.get("antar")), _p(cur.get("pratyantar")),
        _p(v.get("balance_years")), _p(v.get("first_lord"))), styles["Normal"]))
    story.append(Spacer(1, 4))
    ddata = [["Maha", "Years", "Start", "End"]]
    for d in v.get("maha", []):
        ddata.append([_p(d.get("lord")), _p(d.get("years")), _p(d.get("start")), _p(d.get("end"))])
    story.append(_table(ddata, widths=[30*mm, 25*mm, 40*mm, 40*mm], font=8))

    story.append(PageBreak())
    story.append(Paragraph("KP Significators", styles["H"]))
    sig = payload.get("significators", {})
    sdata = [["Planet", "Signified Houses"]]
    for k in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]:
        if k in sig:
            sdata.append([k, ", ".join(map(str, sig[k]))])
    story.append(_table(sdata, widths=[35*mm, 120*mm], font=9))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Engine Notes", styles["H"]))
    notes = [
        "Ephemeris: JPL DE421 via Skyfield (MIT).",
        "Ayanamsa selectable: KP New, KP Traditional/Old, KP Swiss, Lahiri reference.",
        "Position options: Swiss apparent, Classic astrometric, or Geometric/true position.",
        "Houses: Placidus numeric solve. KP sub-lord work uses star/sub/sub-sub divisions by Vimshottari proportions.",
        "This report is for research and decision support; astrological interpretation is not a guarantee."
    ]
    for n in notes:
        story.append(Paragraph("- " + _p(n), styles["Normal"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
