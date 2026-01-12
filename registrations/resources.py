from django.core.exceptions import ValidationError
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget

from .models import Student, Organization, Event


class StudentResource(resources.ModelResource):
    # Excel column: event_code  -> Student.event (FK) by Event.code
    event = fields.Field(
        column_name="event_code",
        attribute="event",
        widget=ForeignKeyWidget(Event, "code"),
    )

    # Optional column in Excel (will be overridden for non-admin users)
    organization = fields.Field(
        column_name="organization",
        attribute="organization",
        widget=ForeignKeyWidget(Organization, "name_en"),
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = Student

        # CREATE-ONLY for schools:
        import_id_fields = ()  # don't require sa_registration_no in the file

        # IMPORTANT: do NOT import sa_registration_no / created_at
        fields = (
            "event",
            "organization",
            "first_name_en", "last_name_en",
            "first_name_ar", "last_name_ar",
            "date_of_birth", "gender",
            "guardian_name", "guardian_phone", "guardian_email",
            "level",
        )

        export_order = fields

    def _is_admin(self):
        if not self.user:
            return False
        role = getattr(self.user, "role", "")
        return self.user.is_superuser or role == "ADMIN"

    def before_import_row(self, row, **kwargs):
        """
        Rules:
        - Event code is required
        - Non-admin: event must be OPEN
        - Non-admin: force organization to user's organization (ignore Excel value)
        """
        if not self.user:
            return

        is_admin = self._is_admin()

        event_code = (row.get("event_code") or "").strip()
        if not event_code:
            raise ValidationError("event_code is required.")

        try:
            ev = Event.objects.get(code=event_code)
        except Event.DoesNotExist:
            raise ValidationError(f"Event code '{event_code}' not found.")

        if not is_admin and ev.status != "OPEN":
            raise ValidationError(f"Event '{event_code}' is CLOSED. Registration not allowed.")

        # Force organization for non-admin imports
        if not is_admin and getattr(self.user, "organization_id", None):
            row["organization"] = self.user.organization.name_en

    def before_save_instance(self, instance, row, **kwargs):
        """
        More rules:
        - Non-admin: force organization
        - ORG_STAFF cannot submit via Excel (force Draft)
        - Non-admin cannot set Accepted/Rejected
        """
        if not self.user:
            return

        role = getattr(self.user, "role", "")
        is_admin = self._is_admin()

        if not is_admin and getattr(self.user, "organization_id", None):
            instance.organization = self.user.organization

        if not is_admin and role == "ORG_STAFF":
            instance.status = "DRAFT"

        if not is_admin and instance.status in ("ACCEPTED", "REJECTED", "SUBMITTED"):
            instance.status = "DRAFT"
