from io import BytesIO
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)


def _money(x):
    try:
        return f"{Decimal(x):.2f}"
    except Exception:
        return "0.00"


def build_invoice_pdf(invoice, items):
    """
    Returns PDF bytes for an invoice using ReportLab Platypus.
    - Nice table (borders, header background)
    - Text wrapping for description/address
    - Header/footer per page
    """

    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        title=f"Invoice {invoice.invoice_no}",
    )

    styles = getSampleStyleSheet()

    h1 = ParagraphStyle(
        "h1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        spaceAfter=6,
    )

    small = ParagraphStyle(
        "small",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=11,
    )

    label = ParagraphStyle(
        "label",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        spaceAfter=2,
    )

    # ---- Header/footer on each page ----
    def on_page(c, d):
        c.saveState()
        w, h = A4
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.grey)
        c.drawRightString(w - 16 * mm, 10 * mm, f"Page {c.getPageNumber()}")
        c.restoreState()

    story = []

    # ---- Title ----
    story.append(Paragraph(f"Invoice {invoice.invoice_no}", h1))
    story.append(Paragraph(
        f"<b>Date:</b> {invoice.invoice_date} &nbsp;&nbsp; "
        f"<b>Status:</b> {invoice.status} &nbsp;&nbsp; "
        f"<b>Type:</b> {invoice.invoice_type}",
        small
    ))
    story.append(Spacer(1, 10))

    # ---- Seller/Buyer blocks ----
    seller_lines = [
        f"<b>{invoice.seller.legal_name}</b>",
        f"VAT: {invoice.seller.vat_number}",
    ]
    if getattr(invoice.seller, "cr_number", ""):
        seller_lines.append(f"CR: {invoice.seller.cr_number}")
    if getattr(invoice.seller, "address_line", ""):
        seller_lines.append(invoice.seller.address_line)
    city = (getattr(invoice.seller, "city", "") or "").strip()
    pc = (getattr(invoice.seller, "postal_code", "") or "").strip()
    if city or pc:
        seller_lines.append(f"{city}{(', ' + pc) if pc else ''}")
    if getattr(invoice.seller, "phone", ""):
        seller_lines.append(f"Phone: {invoice.seller.phone}")
    if getattr(invoice.seller, "email", ""):
        seller_lines.append(f"Email: {invoice.seller.email}")

    buyer_lines = [f"<b>{invoice.buyer_name}</b>"]
    if invoice.buyer_vat_number:
        buyer_lines.append(f"VAT: {invoice.buyer_vat_number}")
    if invoice.buyer_national_address:
        # Convert newlines to <br/>
        buyer_lines.append(invoice.buyer_national_address.replace("\n", "<br/>"))

    seller_block = Paragraph("<br/>".join(seller_lines), small)
    buyer_block = Paragraph("<br/>".join(buyer_lines), small)

    blocks = Table(
        [
            [Paragraph("Seller", label), Paragraph("Buyer", label)],
            [seller_block, buyer_block],
        ],
        colWidths=[(A4[0] - 32 * mm) / 2, (A4[0] - 32 * mm) / 2],
    )
    blocks.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(blocks)
    story.append(Spacer(1, 12))

    # ---- Items table ----
    data = [
        ["Student", "Description", "Qty", "Unit", "Subtotal", "VAT", "Total"]
    ]

    for it in items:
        student_label = getattr(it.student, "sa_registration_no", "") or str(it.student_id)
        student_name = f"{getattr(it.student, 'first_name_en', '')} {getattr(it.student, 'last_name_en', '')}".strip()
        student_cell = f"<b>{student_label}</b><br/><font color='grey'>{student_name}</font>"

        data.append([
            Paragraph(student_cell, small),
            Paragraph((it.description or ""), small),
            str(it.qty),
            _money(it.unit_price),
            _money(it.line_subtotal),
            _money(it.line_vat),
            _money(it.line_total),
        ])

    table = Table(
        data,
        colWidths=[
            32 * mm,   # Student
            66 * mm,   # Description
            10 * mm,   # Qty
            16 * mm,   # Unit
            18 * mm,   # Subtotal
            16 * mm,   # VAT
            18 * mm,   # Total
        ],
        repeatRows=1,
        hAlign="LEFT",
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))

    # ---- Totals block ----
    totals_data = [
        ["Subtotal", _money(invoice.subtotal)],
        ["VAT", _money(invoice.vat_amount)],
        ["Grand Total (SAR)", _money(invoice.total)],
    ]
    totals = Table(totals_data, colWidths=[40 * mm, 30 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LINEABOVE", (0, -1), (-1, -1), 0.75, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(totals)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
