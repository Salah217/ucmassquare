from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.db import transaction

try:
    from import_export.admin import ImportExportModelAdmin
except ImportError:
    ImportExportModelAdmin = admin.ModelAdmin

from .models import (
    Organization, User,
    Student, Event,
    Course, CourseEnrollment,
    EventRegistration,
    CompanyProfile, Invoice, InvoiceItem, InvoiceSequence
)

from .invoicing import (
    issue_invoice_for_course_enrollments,
    issue_invoice_for_event_regs
)

# ---------------------------
# Admin labels
# ---------------------------
admin.site.site_header = "UCMAS Admin"
admin.site.site_title = "UCMAS Admin"
admin.site.index_title = "Administration"


# ---------------------------
# Helpers
# ---------------------------
def is_admin_user(u):
    return u.is_superuser or getattr(u, "role", "") == "ADMIN"


# =========================================================
# Event (ADMIN only)
# =========================================================
@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "deadline", "city", "fee_per_student", "created_at")
    list_filter = ("status", "city")
    search_fields = ("code", "name", "season", "city")

    def has_module_permission(self, request):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)


# =========================================================
# Organization (ADMIN only)
# =========================================================
@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name_en", "org_type", "city", "status", "contact_phone", "created_at")
    list_filter = ("org_type", "status", "city")
    search_fields = ("name_en", "name_ar", "contact_phone", "contact_email", "contact_name")

    def has_module_permission(self, request):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)


# =========================================================
# User (ADMIN only)
# =========================================================
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("UCMAS", {"fields": ("role", "organization")}),
    )
    list_display = ("username", "email", "role", "organization", "is_active", "is_staff")
    list_filter = ("role", "organization", "is_active", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name")

    def has_module_permission(self, request):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)


# =========================================================
# Student (Import/Export optional)
# =========================================================
@admin.register(Student)
class StudentAdmin(ImportExportModelAdmin):
    list_display = (
        "sa_registration_no",
        "first_name_en",
        "last_name_en",
        "organization",
        "current_level",
        "guardian_phone",
        "created_at",
    )
    list_filter = ("organization", "current_level", "gender")
    search_fields = ("sa_registration_no", "first_name_en", "last_name_en", "guardian_phone", "guardian_name")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_admin_user(request.user):
            return qs
        if getattr(request.user, "organization_id", None):
            return qs.filter(organization=request.user.organization)
        return qs.none()


# =========================================================
# Course (ADMIN only)
# =========================================================
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("level", "name", "is_active", "fee", "created_at")
    list_filter = ("is_active", "level")
    search_fields = ("name",)

    def has_module_permission(self, request):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)


# =========================================================
# CourseEnrollment (Admin approve + invoice)
# =========================================================
@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("organization", "student", "course", "status", "created_at", "invoice", "created_by")
    list_filter  = ("organization", "status", "course")
    search_fields = (
        "student__sa_registration_no",
        "student__first_name_en",
        "student__last_name_en",
        "course__name",
        "organization__name_en",
    )
    actions = ["mark_pending_payment", "issue_course_invoice"]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("student", "course", "organization", "invoice")
        if is_admin_user(request.user):
            return qs
        return qs.none()

    def has_module_permission(self, request):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)

    @admin.action(description="Approve: SUBMITTED → PENDING_PAYMENT")
    def mark_pending_payment(self, request, queryset):
        now = timezone.now()
        updated = queryset.filter(status="SUBMITTED").update(
            status="PENDING_PAYMENT",
            approved_at=now,
            approved_by=request.user,
        )
        self.message_user(request, f"Moved {updated} enrollment(s) to PENDING_PAYMENT.", level=messages.SUCCESS)

    @admin.action(description="Issue COURSE invoice (PENDING_PAYMENT only)")
    def issue_course_invoice(self, request, queryset):
        qs = queryset.filter(status="PENDING_PAYMENT", invoice__isnull=True).select_related("course", "student", "organization")
        if not qs.exists():
            self.message_user(request, "Nothing to invoice. Select PENDING_PAYMENT rows with empty invoice.", level=messages.WARNING)
            return

        grouped = {}
        for e in qs:
            grouped.setdefault((e.organization_id, e.course_id), []).append(e)

        created_count = 0
        for (_org_id, _course_id), enroll_list in grouped.items():
            org = enroll_list[0].organization
            course = enroll_list[0].course

            with transaction.atomic():
                lock_qs = CourseEnrollment.objects.select_for_update().filter(
                    id__in=[x.id for x in enroll_list],
                    status="PENDING_PAYMENT",
                    invoice__isnull=True,
                )
                if lock_qs.exists():
                    issue_invoice_for_course_enrollments(
                        org=org, course=course, enrollments=lock_qs, issued_by=request.user
                    )
                    created_count += 1

        self.message_user(request, f"Created {created_count} COURSE invoice(s).", level=messages.SUCCESS)


# =========================================================
# EventRegistration (Admin approve + invoice + mark paid)
# =========================================================
@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = ("event", "student", "organization", "status", "fee_amount", "created_at", "invoice", "paid_at")
    list_filter  = ("status", "event", "organization")
    search_fields = (
        "student__sa_registration_no",
        "student__first_name_en",
        "student__last_name_en",
        "event__code",
        "event__name",
        "organization__name_en",
    )
    actions = ["mark_pending_payment", "issue_event_invoice", "mark_as_paid"]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("event", "student", "organization", "invoice")
        if is_admin_user(request.user):
            return qs
        return qs.none()

    def has_module_permission(self, request):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)

    @admin.action(description="Approve: SUBMITTED → PENDING_PAYMENT")
    def mark_pending_payment(self, request, queryset):
        updated = queryset.filter(status="SUBMITTED").update(status="PENDING_PAYMENT")
        self.message_user(request, f"Moved {updated} registration(s) to PENDING_PAYMENT.", level=messages.SUCCESS)

    @admin.action(description="Issue EVENT invoice (PENDING_PAYMENT only)")
    def issue_event_invoice(self, request, queryset):
        qs = queryset.filter(status="PENDING_PAYMENT", invoice__isnull=True).select_related("event", "student", "organization")
        if not qs.exists():
            self.message_user(request, "Nothing to invoice. Select PENDING_PAYMENT rows with empty invoice.", level=messages.WARNING)
            return

        grouped = {}
        for r in qs:
            grouped.setdefault((r.organization_id, r.event_id), []).append(r)

        created_count = 0
        for (_org_id, _event_id), regs_list in grouped.items():
            org = regs_list[0].organization
            event = regs_list[0].event

            with transaction.atomic():
                lock_qs = EventRegistration.objects.select_for_update().filter(
                    id__in=[x.id for x in regs_list],
                    status="PENDING_PAYMENT",
                    invoice__isnull=True,
                )
                if lock_qs.exists():
                    issue_invoice_for_event_regs(
                        org=org, event=event, regs=lock_qs, issued_by=request.user
                    )
                    created_count += 1

        self.message_user(request, f"Created {created_count} EVENT invoice(s).", level=messages.SUCCESS)

    @admin.action(description="Mark selected PENDING_PAYMENT as PAID")
    def mark_as_paid(self, request, queryset):
        now = timezone.now()
        updated = queryset.filter(status="PENDING_PAYMENT").update(status="PAID", paid_at=now)
        self.message_user(request, f"Marked {updated} registration(s) as PAID.", level=messages.SUCCESS)


# =========================================================
# CompanyProfile / Invoice
# =========================================================
@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("legal_name", "vat_number", "city", "is_active")
    list_filter = ("is_active", "city")
    search_fields = ("legal_name", "vat_number", "cr_number")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_no", "invoice_type", "organization", "status", "total", "invoice_date", "issued_at", "paid_at")
    list_filter = ("invoice_type", "status", "organization", "invoice_date")
    search_fields = ("invoice_no", "organization__name_en", "buyer_name")
    date_hierarchy = "invoice_date"
    actions = ["mark_paid"]

    @admin.action(description="Mark selected invoices as PAID")
    def mark_paid(self, request, queryset):
        now = timezone.now()
        updated = queryset.filter(status="ISSUED").update(status="PAID", paid_at=now)
        self.message_user(request, f"Marked {updated} invoice(s) as PAID.", level=messages.SUCCESS)


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ("invoice", "student", "description", "qty", "unit_price", "line_total")
    search_fields = ("invoice__invoice_no", "student__sa_registration_no", "description")


@admin.register(InvoiceSequence)
class InvoiceSequenceAdmin(admin.ModelAdmin):
    list_display = ("invoice_type", "year", "last_number")
    list_filter = ("invoice_type", "year")
