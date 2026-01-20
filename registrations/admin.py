from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone

from import_export.admin import ImportExportModelAdmin

from .models import (
    Organization, User,
    Student, Event,
    Course, CourseEnrollment,
    EventRegistration,
)

# If you already have StudentResource in resources.py keep it
from .resources import StudentResource  # make sure it no longer references event/status


admin.site.site_header = "UCMAS Admin"
admin.site.site_title = "UCMAS Admin"
admin.site.index_title = "Administration"


# ---------------------------
# Helpers
# ---------------------------
def is_admin_user(u):
    return u.is_superuser or getattr(u, "role", "") == "ADMIN"

def is_manager_user(u):
    return getattr(u, "role", "") == "ORG_MANAGER"


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
# Student (Permanent DB)  ✅ Import/Export kept
# =========================================================
@admin.register(Student)
class StudentAdmin(ImportExportModelAdmin):
    resource_class = StudentResource

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

    # ✅ Pass user to resource (locks org, if your resource uses it)
    def get_import_resource_kwargs(self, request, *args, **kwargs):
        return {"user": request.user}

    def get_export_resource_kwargs(self, request, *args, **kwargs):
        return {"user": request.user}

    # ✅ Restrict list to user's organization
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_admin_user(request.user):
            return qs
        if getattr(request.user, "organization_id", None):
            return qs.filter(organization=request.user.organization)
        return qs.none()

    # ✅ Hide organization from form for org users (auto-assigned)
    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if not is_admin_user(request.user):
            if "organization" in fields:
                fields.remove("organization")
        return fields

    # ✅ Readonly fields
    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        ro += ["sa_registration_no", "created_at"]
        if not is_admin_user(request.user):
            ro += ["organization"]
        return ro

    # ✅ Save rules
    def save_model(self, request, obj, form, change):
        # Force org for org users
        if not is_admin_user(request.user):
            if getattr(request.user, "organization_id", None):
                obj.organization = request.user.organization
        super().save_model(request, obj, form, change)


# =========================================================
# Course (ADMIN only – usually)
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
# CourseEnrollment  (ADMIN + Org users can VIEW their own)
# =========================================================
@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("organization", "student", "course", "status", "created_at", "created_by")
    list_filter = ("organization", "status", "course")
    search_fields = ("student__sa_registration_no", "student__first_name_en", "student__last_name_en", "course__name")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_admin_user(request.user):
            return qs
        if getattr(request.user, "organization_id", None):
            return qs.filter(organization=request.user.organization)
        return qs.none()

    def has_change_permission(self, request, obj=None):
        # Keep it simple: allow admins only to edit in admin (org edits happen in portal UI)
        return is_admin_user(request.user)

    def has_add_permission(self, request):
        return is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_admin_user(request.user)


# =========================================================
# EventRegistration  (ADMIN + Org users can VIEW their own)
# =========================================================
@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "student",
        "organization",
        "status",
        "fee_amount",
        "submitted_at",
        "paid_at",
        "created_at",
    )
    list_filter = ("status", "event", "organization")
    search_fields = ("student__sa_registration_no", "student__first_name_en", "student__last_name_en", "event__code")
    actions = ["mark_as_paid"]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("event", "student", "organization")
        if is_admin_user(request.user):
            return qs
        if getattr(request.user, "organization_id", None):
            return qs.filter(organization=request.user.organization)
        return qs.none()

    def has_add_permission(self, request):
        # registrations should be made from portal UI (admin can still add manually if needed)
        return is_admin_user(request.user)

    def has_change_permission(self, request, obj=None):
        # Allow admin only (portal handles flow for org users)
        return is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_admin_user(request.user)

    # Optional admin action
    def mark_as_paid(self, request, queryset):
        if not is_admin_user(request.user):
            self.message_user(request, "Admins only.", level=messages.ERROR)
            return
        now = timezone.now()
        updated = queryset.filter(status="PENDING_PAYMENT").update(status="PAID", paid_at=now)
        self.message_user(request, f"Marked {updated} registration(s) as PAID.", level=messages.SUCCESS)

    mark_as_paid.short_description = "Mark selected PENDING_PAYMENT as PAID"
