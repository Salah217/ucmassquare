from django import forms
from django.core.exceptions import ValidationError

from .models import Student, Event


# ---------------------------
# Helpers (Tabler styling)
# ---------------------------
class TablerMixin:
    """
    Apply Tabler-friendly CSS classes automatically to all fields.
    """
    def _apply_tabler(self):
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, forms.Textarea):
                w.attrs.update({"class": "form-control", "rows": 3})
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs.update({"class": "form-select"})
            else:
                w.attrs.update({"class": "form-control"})


# ---------------------------
# Existing ModelForm (keep)
# ---------------------------
class StudentForm(forms.ModelForm, TablerMixin):
    """
    Your original one-page form (still useful in admin or if you keep non-wizard screens).
    """

    class Meta:
        model = Student
        fields = [
            "event",
            "first_name_en", "last_name_en",
            "first_name_ar", "last_name_ar",
            "date_of_birth", "gender",
            "guardian_name", "guardian_phone", "guardian_email",
            "level", "notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Only OPEN events for org users
        if user and not (user.is_superuser or getattr(user, "role", "") == "ADMIN"):
            self.fields["event"].queryset = Event.objects.filter(status="OPEN").order_by("deadline", "name")
        else:
            self.fields["event"].queryset = Event.objects.all().order_by("deadline", "name")

        # Lock if submitted (extra safety)
        if self.instance and self.instance.pk and self.instance.status == "SUBMITTED":
            for f in self.fields:
                self.fields[f].disabled = True

        # Apply Tabler classes
        self._apply_tabler()

    def clean(self):
        cleaned = super().clean()
        if self.instance and self.instance.pk and self.instance.status == "SUBMITTED":
            raise ValidationError("This record is submitted and cannot be edited.")
        return cleaned


# ---------------------------
# Wizard Step 1 Form
# ---------------------------
class StudentStep1Form(forms.Form, TablerMixin):
    """
    Step 1: Student details
    """
    event = forms.ModelChoiceField(queryset=Event.objects.none(), required=True)
    level = forms.CharField(required=False, max_length=50)

    first_name_en = forms.CharField(max_length=100)
    last_name_en = forms.CharField(max_length=100)
    first_name_ar = forms.CharField(required=False, max_length=100)
    last_name_ar = forms.CharField(required=False, max_length=100)

    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    gender = forms.ChoiceField(choices=Student.GENDER)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Only OPEN events for org users
        if user and not (user.is_superuser or getattr(user, "role", "") == "ADMIN"):
            self.fields["event"].queryset = Event.objects.filter(status="OPEN").order_by("deadline", "name")
        else:
            self.fields["event"].queryset = Event.objects.all().order_by("deadline", "name")

        self._apply_tabler()


# ---------------------------
# Wizard Step 2 Form
# ---------------------------
class StudentStep2Form(forms.Form, TablerMixin):
    """
    Step 2: Guardian details
    """
    guardian_name = forms.CharField(max_length=150)
    guardian_phone = forms.CharField(max_length=14)
    guardian_email = forms.EmailField(required=False)

    notes = forms.CharField(required=False, widget=forms.Textarea)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_tabler()

    def clean_guardian_phone(self):
        phone = (self.cleaned_data.get("guardian_phone") or "").strip()
        # Keep it aligned with your model regex: +9665XXXXXXXX
        if not phone.startswith("+9665") or len(phone) != 13 or not phone[1:].isdigit():
            raise ValidationError("Use +9665XXXXXXXX (Saudi mobile).")
        return phone
