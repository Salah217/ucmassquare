from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Invoice, InvoiceItem, InvoiceSequence, CompanyProfile


def next_invoice_no(invoice_type: str) -> str:
    """
    Examples:
      COURSE-2026-000001
      EVENT-2026-000001
    """
    year = timezone.now().year
    with transaction.atomic():
        seq, _ = InvoiceSequence.objects.select_for_update().get_or_create(
            invoice_type=invoice_type,
            year=year,
            defaults={"last_number": 0},
        )
        seq.last_number += 1
        seq.save(update_fields=["last_number"])
        return f"{invoice_type}-{year}-{seq.last_number:06d}"


def get_active_seller() -> CompanyProfile:
    seller = CompanyProfile.objects.filter(is_active=True).order_by("-id").first()
    if not seller:
        raise ValueError("No active CompanyProfile found. Create one in admin and mark is_active=True.")
    return seller


def recalc_invoice_totals(invoice: Invoice):
    agg = invoice.items.aggregate(
        subtotal=Sum("line_subtotal"),
        vat=Sum("line_vat"),
        total=Sum("line_total"),
    )
    invoice.subtotal = agg["subtotal"] or Decimal("0.00")
    invoice.vat_amount = agg["vat"] or Decimal("0.00")
    invoice.total = agg["total"] or Decimal("0.00")
    invoice.save(update_fields=["subtotal", "vat_amount", "total"])


@transaction.atomic
def issue_invoice_for_course_enrollments(*, org, course, enrollments, issued_by=None, vat_rate=Decimal("0.1500")) -> Invoice:
    """
    Creates ONE COURSE invoice for selected enrollments and links each enrollment.invoice = invoice.
    """
    seller = get_active_seller()

    inv = Invoice.objects.create(
        invoice_no=next_invoice_no("COURSE"),
        invoice_type="COURSE",
        invoice_date=timezone.now().date(),
        seller=seller,
        organization=org,

        # buyer snapshot
        buyer_name=org.name_en,
        buyer_vat_number=getattr(org, "vat_number", "") or "",
        buyer_national_address=getattr(org, "national_address", "") or "",

        vat_rate=vat_rate,
        status="ISSUED",
        issued_by=issued_by,
        issued_at=timezone.now(),
    )

    fee = Decimal(str(getattr(course, "fee", 0) or 0))

    for e in enrollments:
        InvoiceItem.objects.create(
            invoice=inv,
            student=e.student,
            course_enrollment=e,
            description=f"Course Enrollment: {course.name} (Level {course.level})",
            qty=1,
            unit_price=fee,
        )

    # link enrollments to invoice
    for e in enrollments:
        e.invoice = inv
        e.save(update_fields=["invoice"])

    recalc_invoice_totals(inv)
    return inv


@transaction.atomic
def issue_invoice_for_event_regs(*, org, event, regs, issued_by=None, vat_rate=Decimal("0.1500")) -> Invoice:
    """
    Creates ONE EVENT invoice for selected registrations and links each reg.invoice = invoice.
    """
    seller = get_active_seller()

    inv = Invoice.objects.create(
        invoice_no=next_invoice_no("EVENT"),
        invoice_type="EVENT",
        invoice_date=timezone.now().date(),
        seller=seller,
        organization=org,

        # buyer snapshot
        buyer_name=org.name_en,
        buyer_vat_number=getattr(org, "vat_number", "") or "",
        buyer_national_address=getattr(org, "national_address", "") or "",

        vat_rate=vat_rate,
        status="ISSUED",
        issued_by=issued_by,
        issued_at=timezone.now(),
    )

    fee = Decimal(str(getattr(event, "fee_per_student", 0) or 0))

    for r in regs:
        InvoiceItem.objects.create(
            invoice=inv,
            student=r.student,
            event_registration=r,
            description=f"Competition Registration: {event.code} - {event.name}",
            qty=1,
            unit_price=fee,
        )

    # link regs to invoice
    for r in regs:
        r.invoice = inv
        r.save(update_fields=["invoice"])

    recalc_invoice_totals(inv)
    return inv
