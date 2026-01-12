from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.core.exceptions import ValidationError

from import_export.admin import ImportExportModelAdmin

from .models import Organization, User, Student, Event
from .resources import StudentResource
from django.utils.html import format_html



admin.site.site_header = "UCMAS Admin"
admin.site.site_title = "UCMAS Admin"
admin.site.index_title = "Administration"

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "deadline", "city")
    list_filter = ("status", "city")
    search_fields = ("code", "name", "season", "city")

    # Hide Events from school users (only admin can see it)
    def has_module_permission(self, request):
        return request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name_en", "org_type", "city", "status", "contact_phone")
    list_filter = ("org_type", "status", "city")
    search_fields = ("name_en", "name_ar", "contact_phone", "contact_email")

    # Hide Organizations from school users
    def has_module_permission(self, request):
        return request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("UCMAS", {"fields": ("role", "organization")}),
    )
    list_display = ("username", "email", "role", "organization", "is_active", "is_staff")
    list_filter = ("role", "organization", "is_active")

    # Hide Users from school users
    def has_module_permission(self, request):
        return request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"




@admin.register(Student)
class StudentAdmin(ImportExportModelAdmin):
    resource_class = StudentResource

    list_display = (
        "sa_registration_no",
        "first_name_en",
        "last_name_en",
        "event",
        "organization",
        "status",
        "created_at",
    )
    list_filter = ("status", "organization", "event")
    search_fields = ("sa_registration_no", "first_name_en", "last_name_en", "guardian_phone")

    actions = ["submit_selected_students"]

    # ✅ Pass user to import/export resource (locks org + prevents staff submit via Excel)
    def get_import_resource_kwargs(self, request, *args, **kwargs):
        return {"user": request.user}

    def get_export_resource_kwargs(self, request, *args, **kwargs):
        return {"user": request.user}

    # ✅ Restrict list to user's organization
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        is_admin = request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"
        if is_admin:
            return qs
        if getattr(request.user, "organization_id", None):
            return qs.filter(organization=request.user.organization)
        return qs.none()

    # ✅ Hide organization + submitted_by from form for org users
    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        is_admin = request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"

        if not is_admin:
            for f in ("organization", "submitted_by"):
                if f in fields:
                    fields.remove(f)

        return fields

    # ✅ Readonly rules
    def get_readonly_fields(self, request, obj=None):
        is_admin = request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"

        # Admin can edit everything
        if is_admin:
            return list(super().get_readonly_fields(request, obj))

        # Org users: once submitted -> everything readonly
        if obj and obj.status == "SUBMITTED":
            return [f.name for f in obj._meta.fields]

        # Otherwise, lock these always
        readonly = list(super().get_readonly_fields(request, obj))
        readonly += ["organization", "submitted_by", "submitted_at"]
        return readonly

    # ✅ Restrict FK dropdowns (event only for org users)
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        is_admin = request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"

        if db_field.name == "event" and not is_admin:
            kwargs["queryset"] = Event.objects.filter(status="OPEN")

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # ✅ Save rules (manual add/edit)
    def save_model(self, request, obj, form, change):
        is_admin = request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"
        role = getattr(request.user, "role", "")

        # Force organization always for org users
        if not is_admin:
            if getattr(request.user, "organization_id", None):
                obj.organization = request.user.organization

        # Require event for org users (nice error instead of server crash)
        if not is_admin and not obj.event_id:
            raise ValidationError("Event is required for registration.")

        # ORG_STAFF cannot submit (force Draft)
        if not is_admin and role == "ORG_STAFF" and obj.status == "SUBMITTED":
            obj.status = "DRAFT"
            messages.error(request, "ORG_STAFF cannot submit. Please ask ORG_MANAGER to submit.")

        super().save_model(request, obj, form, change)

    # ❌ Delete rules
    def has_delete_permission(self, request, obj=None):
        is_admin = request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"
        if is_admin:
            return True
        # org users cannot delete submitted
        if obj and obj.status == "SUBMITTED":
            return False
        return True

    # ✅ Bulk action: Draft -> Submitted (only ADMIN or ORG_MANAGER)
    def submit_selected_students(self, request, queryset):
        is_admin = request.user.is_superuser or getattr(request.user, "role", "") == "ADMIN"
        is_manager = getattr(request.user, "role", "") == "ORG_MANAGER"

        if not (is_admin or is_manager):
            self.message_user(
                request,
                "Only ADMIN or ORG_MANAGER can submit students.",
                level=messages.ERROR,
            )
            return

        # Only submit Draft
        draft_qs = queryset.filter(status="DRAFT")
        count = 0

        for obj in draft_qs:
            obj.status = "SUBMITTED"
            obj.submitted_at = timezone.now()
            obj.submitted_by = request.user
            obj.save(update_fields=["status", "submitted_at", "submitted_by"])
            count += 1

        if count == 0:
            self.message_user(request, "No Draft students selected.", level=messages.WARNING)
        else:
            self.message_user(request, f"Submitted {count} student(s).", level=messages.SUCCESS)

    submit_selected_students.short_description = "Submit selected students (Draft → Submitted)"

