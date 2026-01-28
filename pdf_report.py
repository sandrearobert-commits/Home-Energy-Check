# pdf_report.py
from __future__ import annotations
from typing import Dict, Any, List, Optional
from io import BytesIO

def _draw_energy_label(c, x, y, w, h, cls: str):
    """
    Draws a simple A–G label (non-official) like appliance stickers.
    (x,y) is bottom-left.
    """
    from reportlab.lib import colors
    from reportlab.pdfbase.pdfmetrics import stringWidth

    classes = ["A", "B", "C", "D", "E", "F", "G"]
    # colors left->right (green->red)
    bar_colors = [
        colors.HexColor("#00a651"),
        colors.HexColor("#39b54a"),
        colors.HexColor("#8dc63f"),
        colors.HexColor("#fff200"),
        colors.HexColor("#f7941d"),
        colors.HexColor("#ed1c24"),
        colors.HexColor("#b11116"),
    ]
    bar_h = h / len(classes)
    # draw bars top-down
    for i, cl in enumerate(classes):
        yy = y + h - (i+1)*bar_h
        c.setFillColor(bar_colors[i])
        c.rect(x, yy, w, bar_h, stroke=0, fill=1)
        c.setFillColor(colors.black if cl in ["D","E"] else colors.white)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x + 6, yy + bar_h/2 - 4, cl)

    # arrow pointing to class
    if cls not in classes:
        cls = "E"
    idx = classes.index(cls)
    yy = y + h - (idx+0.5)*bar_h
    ax = x + w + 10
    c.setFillColor(colors.black)
    # triangle arrow
    c.saveState()
    c.translate(ax, yy)
    c.beginPath()
    p = c.beginPath()
    p.moveTo(0, 0)
    p.lineTo(14, 6)
    p.lineTo(14, -6)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.restoreState()

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(ax + 18, yy - 4, f"Besorolás: {cls} (light)")

def build_pdf_report(results: Dict[str, Any], inputs: Dict[str, Any], photos: Optional[List[bytes]] = None) -> bytes:
    """
    Digitális Energetikai Gyorsjelentés PDF (nem hivatalos).
    - A–G vizuális skála nyíllal
    - veszteség-analízis
    - TOP javaslatok + megtakarítás
    - opcionális fotók beillesztése
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    lm, rm = 18*mm, 18*mm
    top = H - 16*mm

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(lm, top, "Digitális Energetikai Gyorsjelentés")
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.grey)
    c.drawString(lm, top-16, "Tájékoztató becslés – nem helyettesíti a hiteles energetikai tanúsítványt.")
    c.setFillColor(colors.black)

    # Meta block
    date_str = inputs.get("date") or ""
    if not date_str:
        import datetime as _dt
        date_str = _dt.date.today().isoformat()

    addr = inputs.get("address") or ""
    town = inputs.get("town") or ""
    zipc = inputs.get("zip") or ""
    area = inputs.get("area_m2", 0)
    typ = inputs.get("property_type") or "Lakóingatlan (becslés)"
    build_year = inputs.get("build_year") or "Nem ismert"

    y = top - 40
    c.setFont("Helvetica-Bold", 10)
    c.drawString(lm, y, "Alapadatok")
    y -= 12
    c.setFont("Helvetica", 10)
    def line(label, value):
        nonlocal y
        c.drawString(lm, y, f"{label}: {value}")
        y -= 12
    line("Készült", date_str)
    if any([zipc, town, addr]):
        line("Hely", f"{zipc} {town} {addr}".strip())
    line("Ingatlan típusa", typ)
    line("Becsült alapterület", f"{area} m²")
    line("Építés éve (becslés)", str(build_year))
    line("Fűtés", inputs.get("heating_type","-"))
    line("Melegvíz", inputs.get("dhw_type","-"))

    # Section 1: Class + big numbers
    y -= 6
    c.setFont("Helvetica-Bold", 12)
    c.drawString(lm, y, "1. Becsült energetikai állapot")
    y -= 16

    cls = results.get("energy_class_light","E")
    _draw_energy_label(c, lm, y-110, 70, 110, cls)

    e = results.get("energy_kwh", {})
    cost = results.get("cost_huf", {})
    co2 = results.get("co2_kg", {})

    c.setFont("Helvetica", 10)
    c.drawString(lm+95, y-10, f"Összes energia: {e.get('total',0):.0f} kWh/év")
    c.drawString(lm+95, y-24, f"Költség (becsült): {cost.get('total',0):.0f} Ft/év")
    c.drawString(lm+95, y-38, f"CO₂ (becsült): {co2.get('total',0):.0f} kg/év")
    c.setFillColor(colors.grey)
    c.drawString(lm+95, y-54, "Megjegyzés: algoritmus által generált becslés a megadott adatok alapján.")
    c.setFillColor(colors.black)

    # Section 2: Loss analysis (simple rule-based)
    y2 = y - 130
    c.setFont("Helvetica-Bold", 12)
    c.drawString(lm, y2, "2. Veszteség-analízis (Hol szökik a pénz?)")
    y2 -= 18
    # Use qualities if present; else default weights
    bq = (results.get("meta",{}).get("building_quality") or "közepes").lower()
    if bq == "jó":
        loss = [("Födém/Tető", 28), ("Külső falak", 26), ("Nyílászárók", 20), ("Padló/Egyéb", 26)]
    elif bq == "közepes":
        loss = [("Födém/Tető", 32), ("Külső falak", 28), ("Nyílászárók", 22), ("Padló/Egyéb", 18)]
    else:
        loss = [("Födém/Tető", 34), ("Külső falak", 30), ("Nyílászárók", 22), ("Padló/Egyéb", 14)]

    # Draw mini bars
    bar_x = lm
    bar_w = 160
    bar_h = 10
    c.setFont("Helvetica", 10)
    for name, pct in loss:
        c.drawString(bar_x, y2, f"{name}: {pct}%")
        c.setFillColor(colors.HexColor("#2dd4bf"))
        c.rect(bar_x+95, y2-3, bar_w*(pct/100), bar_h, stroke=0, fill=1)
        c.setFillColor(colors.lightgrey)
        c.rect(bar_x+95 + bar_w*(pct/100), y2-3, bar_w*(1-pct/100), bar_h, stroke=0, fill=1)
        c.setFillColor(colors.black)
        y2 -= 14

    # Section 3: Plan
    y3 = y2 - 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(lm, y3, "3. Javasolt fejlesztési terv (prioritási sorrendben)")
    y3 -= 18
    recs = results.get("recommendations", []) or []
    c.setFont("Helvetica", 10)
    if recs:
        for i, r in enumerate(recs, 1):
            title = r.get("title","")
            why = r.get("why","")
            save_huf = r.get("save_huf_y",0)
            save_kwh = r.get("save_kwh_y",0)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(lm, y3, f"{i}. {title}")
            y3 -= 12
            c.setFont("Helvetica", 10)
            c.drawString(lm+10, y3, f"- Becsült megtakarítás: ~{save_huf:.0f} Ft/év (~{save_kwh:.0f} kWh/év)")
            y3 -= 12
            if why:
                c.setFillColor(colors.grey)
                c.drawString(lm+10, y3, f"- {why[:110]}")
                c.setFillColor(colors.black)
                y3 -= 12
            y3 -= 2
    else:
        c.drawString(lm, y3, "Nincs elegendő adat a javaslatokhoz.")

    # Section 4: Economic benefits
    y4 = y3 - 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(lm, y4, "4. Gazdasági előnyök (becslés)")
    y4 -= 16
    # Compute savings range from recs
    total_save = sum(float(r.get("save_huf_y",0)) for r in recs[:3])
    low = total_save * 0.8
    high = total_save * 1.2
    c.setFont("Helvetica", 10)
    c.drawString(lm, y4, f"Becsült éves megtakarítás (TOP 3 után): kb. {low:,.0f} – {high:,.0f} Ft/év".replace(",", " "))
    y4 -= 12
    c.drawString(lm, y4, "Ingatlanérték növekedés (tájékoztató): kb. 5–8% (helyszíntől és piactól függ).")
    y4 -= 16

    # Optional coupon / CTA placeholder
    coupon = inputs.get("coupon_code")
    if coupon:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(lm, y4, "🎁 Az Ön egyedi kedvezménye")
        y4 -= 14
        c.setFont("Helvetica", 10)
        c.drawString(lm, y4, f"Kuponkód: {coupon}")
        y4 -= 12
        c.setFillColor(colors.grey)
        c.drawString(lm, y4, "A kedvezmény feltételei partnerenként eltérhetnek.")
        c.setFillColor(colors.black)
        y4 -= 16

    # Photos section (new page if needed)
    if photos:
        c.showPage()
        c.setFont("Helvetica-Bold", 14)
        c.drawString(lm, H-40, "Feltöltött fotók (opcionális)")
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.grey)
        c.drawString(lm, H-56, "A felhasználó által feltöltött képek. Tájékoztató jellegűek.")
        c.setFillColor(colors.black)

        px = lm
        py = H - 90
        max_w = W - lm - rm
        max_h = 110*mm
        for i, b in enumerate(photos[:2], 1):
            try:
                img = ImageReader(BytesIO(b))
                # draw with keep ratio - simple fit
                c.drawImage(img, px, py-max_h, width=max_w, height=max_h, preserveAspectRatio=True, anchor='n')
                py -= (max_h + 18)
            except Exception:
                c.setFont("Helvetica", 10)
                c.drawString(lm, py, f"(Nem sikerült beilleszteni a {i}. képet)")
                py -= 14

    # Disclaimer footer (last page)
    c.showPage()
    c.setFont("Helvetica-Bold", 12)
    c.drawString(lm, H-50, "Jogi nyilatkozat")
    c.setFont("Helvetica", 9)
    text = (
        "NYILATKOZAT: Ez a dokumentum egy automatizált algoritmus által készített tájékoztató jellegű becslés, "
        "amely kizárólag a Felhasználó által megadott adatokon alapul.\n\n"
        "Ez az elemzés NEM minősül a 176/2008. (VI. 30.) Korm. rendelet szerinti hiteles energetikai tanúsítványnak.\n\n"
        "A számított értékek (megtakarítás, besorolás) tájékoztató jellegűek; a tényleges adatok ingatlanonként eltérhetnek.\n\n"
        "Az üzemeltető nem vállal felelősséget az adatok pontatlanságából eredő esetleges károkért vagy meghiúsult pályázatokért.\n\n"
        "Hivatalos ügyintézéshez, ingatlan eladáshoz vagy állami támogatás végső elszámolásához minden esetben jogosult "
        "energetikai tanúsító bevonása szükséges."
    )
    # Simple wrapped text
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    styles = getSampleStyleSheet()
    p = Paragraph(text.replace("\n", "<br/>"), styles["Normal"])
    w, h = p.wrap(W-lm-rm, H-120)
    p.drawOn(c, lm, H-90-h)

    c.save()
    return buf.getvalue()
