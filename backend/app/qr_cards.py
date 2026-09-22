"""Printable A4 cards, generated in memory; no credential files on the server."""
import base64
import io
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import KeepInFrame, Paragraph

ROLE_LABELS = {"administrator": "Администратор", "chief_judge": "Главный судья", "secretary": "Секретарь",
               "reception": "Ресепшен", "route_judge": "Судья на трассе"}


def qr_drawing(url: str) -> Drawing:
    qr = QrCodeWidget(url, barLevel="M", barBorder=4)
    x1, y1, x2, y2 = qr.getBounds()
    drawing = Drawing(140, 140, transform=[140 / (x2 - x1), 0, 0, 140 / (y2 - y1), 0, 0])
    drawing.add(qr)
    return drawing


def printable_cards(users, keys: dict, origin: str) -> dict:
    font = "QrCard"
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font, str(Path(__file__).with_name("assets") / "DejaVuSans.ttf")))
    output = io.BytesIO()
    pdf = Canvas(output, pagesize=(595.28, 841.89))
    pdf.setTitle("ПаркРок — персональные QR")
    style = ParagraphStyle("card", fontName=font, fontSize=10, leading=12, alignment=1)
    cards = []
    for index, user in enumerate(users):
        if index and index % 6 == 0:
            pdf.showPage()
        url = f"{origin}/login/qr#key={keys[user.id]}"
        drawing = qr_drawing(url)
        role = ROLE_LABELS.get(user.role, user.role)
        x, y = 25 + (index % 2) * 280, 565 - ((index % 6) // 2) * 270
        pdf.setStrokeColorRGB(.7, .75, .8)
        pdf.roundRect(x, y, 265, 250, 8)
        pdf.setFillColorRGB(.08, .2, .3)
        pdf.drawImage(str(Path(__file__).with_name("assets") / "crm-logo-light.png"),
                      x + 67.5, y + 202, width=130, height=130 * 204 / 660, mask="auto")
        name = KeepInFrame(245, 22, [Paragraph(escape(user.full_name), style)], mode="shrink")
        _, height = name.wrapOn(pdf, 245, 22)
        name.drawOn(pdf, x + 10, y + 197 - height)
        renderPDF.draw(drawing, pdf, x + 62.5, y + 35)
        label = KeepInFrame(245, 22, [Paragraph(escape(role), style)], mode="shrink")
        _, height = label.wrapOn(pdf, 245, 22)
        label.drawOn(pdf, x + 10, y + 34 - height)
        pdf.setFont(font, 7)
        pdf.drawCentredString(x + 132.5, y + 8, "Личный ключ входа · Не передавайте другим")
        svg = renderSVG.drawToString(drawing)
        cards.append(dict(user_id=str(user.id), full_name=user.full_name, role_label=role,
                          svg_base64=base64.b64encode(svg.encode()).decode()))
    pdf.save()
    return {"cards": cards, "pdf_base64": base64.b64encode(output.getvalue()).decode()}
