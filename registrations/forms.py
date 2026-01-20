from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from .models import Student, Event, Course


# ---------------------------
# Helpers (Tabler styling)
# ---------------------------
class TablerMixin:
    """
    Apply Tabler-friendly CSS classes automatically to all fields.
    """
    def _apply_tabler(self):
        for name, field in self.fields.items(): # pyright: ignore[reportAttributeAccessIssue]
            w = field.widget
            if isinstance(w, forms.Textarea):
                w.attrs.update({"class": "form-control", "rows": 3})
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs.update({"class": "form-select"})
            else:
                w.attrs.update({"class": "form-control"})


# ---------------------------
# Student ModelForm (permanent DB)
# ---------------------------
class StudentForm(forms.ModelForm, TablerMixin):
    """
    One-page student form (permanent student database record).
    """

    class Meta:
        model = Student
        fields = [
            "first_name_en", "last_name_en",
            "first_name_ar", "last_name_ar",
            "date_of_birth", "gender",
            "guardian_name", "guardian_phone", "guardian_email",
            "current_level", "notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Apply Tabler classes
        self._apply_tabler()

        # Make level a bit nicer in UI
        self.fields["current_level"].widget.attrs.update({"min": 1, "max": 10})

    def clean_current_level(self):
        lvl = self.cleaned_data.get("current_level")
        if lvl is None:
            return lvl
        if lvl < 1 or lvl > 10:
            raise ValidationError("Level must be between 1 and 10.")
        return lvl


# ---------------------------
# Wizard Step 1 Form (Student details)
# ---------------------------
class StudentStep1Form(forms.Form, TablerMixin):
    """
    Step 1: Student details (NO event selection anymore).
    """
    first_name_en = forms.CharField(max_length=100)
    last_name_en = forms.CharField(max_length=100)
    first_name_ar = forms.CharField(required=False, max_length=100)
    last_name_ar = forms.CharField(required=False, max_length=100)

    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    gender = forms.ChoiceField(choices=Student.GENDER)

    # replaced old 'level' with current_level (1..10)
    current_level = forms.IntegerField(min_value=1, max_value=10, required=True, initial=1)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_tabler()
        self.fields["current_level"].widget.attrs.update({"min": 1, "max": 10})


# ---------------------------
# Wizard Step 2 Form (Guardian details)
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


# ---------------------------
# NEW: Course registration picker (Step 0)
# ---------------------------
class CourseRegisterForm(forms.Form, TablerMixin):
    """
    Select a course to enroll students in.
    Student selection will be done in the view (checkbox list from Student DB).
    """
    course = forms.ModelChoiceField(queryset=Course.objects.none(), required=True)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # show only active courses
        self.fields["course"].queryset = Course.objects.filter(is_active=True).order_by("level", "name")
        self._apply_tabler()


# ---------------------------
# NEW: Competition registration picker (Step 0)
# ---------------------------
class CompetitionRegisterForm(forms.Form, TablerMixin):
    """
    Select an OPEN event to register students in.
    Student selection will be done in the view (checkbox list from Student DB).
    """
    event = forms.ModelChoiceField(queryset=Event.objects.none(), required=True)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        today = None
        try:
            from django.utils import timezone
            today = timezone.localdate()
        except Exception:
            today = None

        qs = Event.objects.filter(status="OPEN").order_by("deadline", "name")
        if today is not None:
            qs = qs.filter(models.Q(deadline__isnull=True) | models.Q(deadline__gte=today))

        self.fields["event"].queryset = qs
        self._apply_tabler()
