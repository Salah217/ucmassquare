from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class Organization(models.Model):
    ORG_TYPES = [
        ("SCHOOL", "School"),
        ("ASSOCIATION", "Association"),
    ]
    STATUS = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("SUSPENDED", "Suspended"),
    ]

    name_en = models.CharField(max_length=200)
    name_ar = models.CharField(max_length=200, blank=True)
    org_type = models.CharField(max_length=20, choices=ORG_TYPES)
    city = models.CharField(max_length=100)

    contact_name = models.CharField(max_length=150)
    contact_phone = models.CharField(
        max_length=14,
        validators=[RegexValidator(regex=r"^\+9665\d{8}$", message="Use +9665XXXXXXXX")],
    )
    contact_email = models.EmailField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name_en


class User(AbstractUser):
    ROLES = [
        ("ADMIN", "UCMAS Admin"),
        ("ORG_MANAGER", "Organization Manager"),
        ("ORG_STAFF", "Organization Staff"),
    ]

    role = models.CharField(max_length=20, choices=ROLES, default="ORG_STAFF")
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL)

    def is_org_user(self):
        return self.role in ("ORG_MANAGER", "ORG_STAFF")


class Event(models.Model):
    STATUS = [
        ("OPEN", "Open"),
        ("CLOSED", "Closed"),
    ]
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=200)
    season = models.CharField(max_length=50, blank=True)
    city = models.CharField(max_length=100, blank=True)
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="OPEN")
    notes = models.TextField(blank=True)

    # ✅ NEW: event fee (admin sets)
    fee_per_student = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Student(models.Model):
    """
    Permanent student database record (per organization).
    Not tied to any event.
    """
    GENDER = [("M", "Male"), ("F", "Female")]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="students")

    first_name_en = models.CharField(max_length=100)
    last_name_en = models.CharField(max_length=100)
    first_name_ar = models.CharField(max_length=100, blank=True)
    last_name_ar = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=1, choices=GENDER)

    guardian_name = models.CharField(max_length=150)
    guardian_phone = models.CharField(
        max_length=14,
        validators=[RegexValidator(regex=r"^\+9665\d{8}$", message="Use +9665XXXXXXXX")],
    )
    guardian_email = models.EmailField(blank=True)

    # ✅ Student level (1..10)
    current_level = models.PositiveSmallIntegerField(default=1)

    notes = models.TextField(blank=True)

    # ✅ Keep as permanent Student ID (minimum change)
    sa_registration_no = models.CharField(max_length=30, unique=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
    super().clean()
    if self.current_level < 0 or self.current_level > 10:
        raise ValidationError({"current_level": _("Level must be between 0 and 10.")})

    def save(self, *args, **kwargs):
        if not self.sa_registration_no:
            year = timezone.now().year
            prefix = f"UCMAS-KSA-{year}-"
            last = Student.objects.filter(sa_registration_no__startswith=prefix).order_by("-sa_registration_no").first()
            if last and last.sa_registration_no.replace(prefix, "").isdigit():
                next_num = int(last.sa_registration_no.replace(prefix, "")) + 1
            else:
                next_num = 1
            self.sa_registration_no = f"{prefix}{next_num:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sa_registration_no} - {self.first_name_en} {self.last_name_en}"


class Course(models.Model):
    """
    Courses offered by UCMAS (e.g., Level 1..10).
    Admin creates them.
    """
    level = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    # Optional fee per course
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField(null=True, blank=True)

    def clean(self):
        super().clean()
        if self.level < 1 or self.level > 10:
            raise ValidationError({"level": _("Level must be between 1 and 10.")})

    def __str__(self):
        return f"Level {self.level} - {self.name}"


class CourseEnrollment(models.Model):
    STATUS = [
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted"),
        ("ACCEPTED", "Accepted"),
        ("REJECTED", "Rejected"),
        ("PENDING_PAYMENT", "Pending Payment"),
        ("PAID", "Paid"),
        ("ENROLLED", "Enrolled"),
        ("COMPLETED", "Completed"),
        ("DROPPED", "Dropped"),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="course_enrollments"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="course_enrollments"
    )
    course = models.ForeignKey(
        Course, on_delete=models.PROTECT, related_name="enrollments"
    )

    status = models.CharField(max_length=20, choices=STATUS, default="DRAFT")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="submitted_course_enrollments",
    )

    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_course_enrollments",
    )

    rejection_reason = models.CharField(max_length=255, blank=True)

    invoice_no = models.CharField(max_length=50, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_ref = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "course"], name="uniq_student_course")
        ]

    def __str__(self):
        return f"{self.student} -> {self.course} ({self.status})"


class EventRegistration(models.Model):
    STATUS = [
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted"),
        ("PENDING_PAYMENT", "Pending Payment"),
        ("PAID", "Paid"),
        ("ACCEPTED", "Accepted"),
        ("REJECTED", "Rejected"),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="event_registrations")
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="registrations")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="event_registrations")

    status = models.CharField(max_length=20, choices=STATUS, default="DRAFT")

    # fee snapshot at the time of submission
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    rejection_reason = models.CharField(max_length=255, blank=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="submitted_event_registrations",
    )

    # payment tracking (Tabby later)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_ref = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "student"], name="uniq_event_student")
        ]

    def clean(self):
        super().clean()
        # Ensure student belongs to same org
        if self.student_id and self.organization_id and self.student.organization_id != self.organization_id:
            raise ValidationError(_("Student must belong to the same organization."))

    def __str__(self):
        return f"{self.event.code} - {self.student.sa_registration_no} ({self.status})"
