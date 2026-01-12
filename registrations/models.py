from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


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
    code = models.CharField(max_length=30, unique=True)  # e.g. NF-2026, RIY-R1-2026, INT-2026
    name = models.CharField(max_length=200)   # e.g. National Final 2026
    season = models.CharField(max_length=50, blank=True)  # e.g. 2026
    city = models.CharField(max_length=100, blank=True)
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="OPEN")
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Student(models.Model):
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="students")

    GENDER = [("M", "Male"), ("F", "Female")]
    STATUS = [
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted"),
        ("ACCEPTED", "Accepted"),
        ("REJECTED", "Rejected"),
    ]

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

    level = models.CharField(max_length=50, blank=True)
    
    notes = models.TextField(blank=True)

    sa_registration_no = models.CharField(max_length=30, unique=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="DRAFT")
    rejection_reason = models.CharField(max_length=255, blank=True) 
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
    "registrations.User",
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="submitted_students",    

)  

    def clean(self):
     super().clean()
    # Event must be selected
     if not self.event_id:
      raise ValidationError({"event": _("Event is required for registration.")})

    created_at = models.DateTimeField(auto_now_add=True)

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
