from django.core.exceptions import ValidationError
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget

from .models import Student, Organization


class StudentResource(resources.ModelResource):
    """
    Import/Export for the permanent Student database (per organization).

    Rules:
    - Non-admin users: organization is forced to the logged-in user's organization
      (ignores any value coming from Excel).
    - We do NOT import sa_registration_no (auto-generated) or created_at.
    - current_level must be between 1 and 10.
    """

    # Optional column in Excel: organization (name_en)
    # For non-admin, this will be forced to user's org anyway.
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
        import_id_fields = ()  # do not require sa_registration_no in Excel

        # IMPORTANT: do NOT import sa_registration_no / created_at
        fields = (
            "organization",
            "first_name_en", "last_name_en",
            "first_name_ar", "last_name_ar",
            "date_of_birth", "gender",
            "guardian_name", "guardian_phone", "guardian_email",
            "current_level",
            "notes",
        )
        export_order = fields

    def _is_admin(self):
        if not self.user:
            return False
        role = getattr(self.user, "role", "")
        return self.user.is_superuser or role == "ADMIN"

    def before_import_row(self, row, **kwargs):
        """
        Force organization for non-admin users.
        Validate current_level.
        """
        if not self.user:
            return

        is_admin = self._is_admin()

        # Force organization for non-admin imports
        if not is_admin and getattr(self.user, "organization_id", None):
            row["organization"] = self.user.organization.name_en

        # Validate level if provided
        lvl = row.get("current_level", None)
        if lvl is not None and str(lvl).strip() != "":
            try:
                lvl_int = int(str(lvl).strip())
            except ValueError:
                raise ValidationError("current_level must be a number between 1 and 10.")

            if lvl_int < 1 or lvl_int > 10:
                raise ValidationError("current_level must be between 1 and 10.")

    def before_save_instance(self, instance, row, **kwargs):
        """
        Force organization again at save time for safety.
        """
        if not self.user:
            return

        is_admin = self._is_admin()

        if not is_admin and getattr(self.user, "organization_id", None):
            instance.organization = self.user.organization

        # Extra safety: ensure correct range
        if instance.current_level < 1 or instance.current_level > 10:
            raise ValidationError("current_level must be between 1 and 10.")
