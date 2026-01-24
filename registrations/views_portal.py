from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q
from django.core.paginator import Paginator
from django.db import transaction
from django.urls import reverse
from django.http import HttpResponseRedirect


from .models import Student, Event, Course, CourseEnrollment, EventRegistration
from .forms import (
    StudentForm,
    StudentStep1Form,
    StudentStep2Form,
    CourseRegisterForm,
    CompetitionRegisterForm,
)


# ---------------------------
# Role helpers
# ---------------------------
def is_admin(user):
    return user.is_superuser or getattr(user, "role", "") == "ADMIN"

def is_manager(user):
    return getattr(user, "role", "") == "ORG_MANAGER"


# ---------------------------
# Dashboard
# ---------------------------
from django.contrib.auth.decorators import login_required
from django.utils import timezone
@login_required
def portal_dashboard(request):
    org = getattr(request.user, "organization", None)
    today = timezone.now().date()

    # ---- OPEN COURSES ----
    open_courses = (
        Course.objects
        .filter(is_active=True)
        .order_by("start_date", "-created_at")
    )[:6]

    # ---- OPEN EVENTS ----
    # Your Event model DOES NOT have event_date (based on Render error).
    # So order by deadline (and show upcoming).
    open_events = (
        Event.objects
        .filter(status="OPEN", deadline__gte=today)
        .order_by("deadline", "-created_at")
    )[:6]

    # ---- IMPORTANT NOTICES ----
    # If you don't have Notice model, keep notices empty to avoid 500.
    notices = []
    # If you DO have Notice model, uncomment these 2 lines:
    # from .models import Notice
    # notices = Notice.objects.filter(is_active=True).order_by("-created_at")[:5]

    ctx = {
        "org": org,
        "open_courses": open_courses,
        "open_events": open_events,
        "notices": notices,
        "open_courses_count": len(open_courses),
        "open_events_count": len(open_events),
    }
    return render(request, "portal/dashboard.html", ctx)


# ---------------------------
# Student list (permanent DB)
# ---------------------------
@login_required
def student_list(request):
    user = request.user

    if is_admin(user):
        return redirect("/admin/")

    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    qs = Student.objects.filter(organization=user.organization).order_by("-created_at")

    q = (request.GET.get("q") or "").strip()
    level = (request.GET.get("level") or "").strip()

    if q:
        qs = qs.filter(
            Q(sa_registration_no__icontains=q) |
            Q(first_name_en__icontains=q) |
            Q(last_name_en__icontains=q) |
            Q(first_name_ar__icontains=q) |
            Q(last_name_ar__icontains=q) |
            Q(guardian_phone__icontains=q) |
            Q(guardian_name__icontains=q)
        )

    if level:
        try:
            qs = qs.filter(current_level=int(level))
        except ValueError:
            pass

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "portal/student_list.html", {
        "students": page_obj,
        "page_obj": page_obj,
        "q": q,
        "selected_level": level,
        "is_manager": is_manager(user),
    })


# =========================================================
# STUDENT WIZARD (Create/Edit)
# =========================================================
WIZ_KEY_CREATE = "student_wizard_create"
WIZ_KEY_EDIT_PREFIX = "student_wizard_edit_"  # + pk

def _wizard_key(pk=None):
    return WIZ_KEY_CREATE if pk is None else f"{WIZ_KEY_EDIT_PREFIX}{pk}"

def _wizard_reset(request, pk=None):
    request.session.pop(_wizard_key(pk), None)

def _wizard_get(request, pk=None):
    return request.session.get(_wizard_key(pk), {})

def _wizard_set(request, data, pk=None):
    request.session[_wizard_key(pk)] = data
    request.session.modified = True


@login_required
def student_wizard_start(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    _wizard_reset(request, pk=None)
    return redirect("portal_student_wizard_step1")


@login_required
def student_wizard_step1(request, pk=None):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    instance = None
    if pk:
        instance = get_object_or_404(Student, pk=pk, organization=user.organization)

    wiz = _wizard_get(request, pk=pk)

    # Preload when editing
    if pk and not wiz:
        wiz = {
            "first_name_en": instance.first_name_en,
            "last_name_en": instance.last_name_en,
            "first_name_ar": instance.first_name_ar,
            "last_name_ar": instance.last_name_ar,
            "date_of_birth": instance.date_of_birth.isoformat(),
            "gender": instance.gender,
            "current_level": instance.current_level,
        }
        _wizard_set(request, wiz, pk=pk)

    initial = {
        "first_name_en": wiz.get("first_name_en", ""),
        "last_name_en": wiz.get("last_name_en", ""),
        "first_name_ar": wiz.get("first_name_ar", ""),
        "last_name_ar": wiz.get("last_name_ar", ""),
        "date_of_birth": wiz.get("date_of_birth", ""),
        "gender": wiz.get("gender", ""),
        "current_level": wiz.get("current_level", 1),
    }

    if request.method == "POST":
        form = StudentStep1Form(request.POST, user=user)
        if form.is_valid():
            cd = form.cleaned_data
            wiz.update({
                "first_name_en": cd["first_name_en"],
                "last_name_en": cd["last_name_en"],
                "first_name_ar": cd.get("first_name_ar", ""),
                "last_name_ar": cd.get("last_name_ar", ""),
                "date_of_birth": cd["date_of_birth"].isoformat(),
                "gender": cd["gender"],
                "current_level": cd["current_level"],
            })
            _wizard_set(request, wiz, pk=pk)
            return redirect("portal_student_wizard_step2_edit", pk=pk) if pk else redirect("portal_student_wizard_step2")
    else:
        form = StudentStep1Form(initial=initial, user=user)

    return render(request, "portal/student_wizard_step1.html", {
        "form": form,
        "mode": "edit" if pk else "create",
        "pk": pk,
        "step": 1,
    })


@login_required
def student_wizard_step2(request, pk=None):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    instance = None
    if pk:
        instance = get_object_or_404(Student, pk=pk, organization=user.organization)

    wiz = _wizard_get(request, pk=pk)

    # Guard
    if not wiz.get("first_name_en"):
        return redirect("portal_student_wizard_step1_edit", pk=pk) if pk else redirect("portal_student_wizard_step1")

    # Preload when editing
    if pk and ("guardian_name" not in wiz):
        wiz.update({
            "guardian_name": instance.guardian_name,
            "guardian_phone": instance.guardian_phone,
            "guardian_email": instance.guardian_email,
            "notes": instance.notes,
        })
        _wizard_set(request, wiz, pk=pk)

    initial = {
        "guardian_name": wiz.get("guardian_name", ""),
        "guardian_phone": wiz.get("guardian_phone", ""),
        "guardian_email": wiz.get("guardian_email", ""),
        "notes": wiz.get("notes", ""),
    }

    if request.method == "POST":
        form = StudentStep2Form(request.POST, user=user)
        if form.is_valid():
            cd = form.cleaned_data
            wiz.update({
                "guardian_name": cd["guardian_name"],
                "guardian_phone": cd["guardian_phone"],
                "guardian_email": cd.get("guardian_email", ""),
                "notes": cd.get("notes", ""),
            })
            _wizard_set(request, wiz, pk=pk)
            return redirect("portal_student_wizard_review_edit", pk=pk) if pk else redirect("portal_student_wizard_review")
    else:
        form = StudentStep2Form(initial=initial, user=user)

    return render(request, "portal/student_wizard_step2.html", {
        "form": form,
        "mode": "edit" if pk else "create",
        "pk": pk,
        "step": 2,
    })


@login_required
def student_wizard_review(request, pk=None):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    instance = None
    if pk:
        instance = get_object_or_404(Student, pk=pk, organization=user.organization)

    wiz = _wizard_get(request, pk=pk)
    if not wiz.get("first_name_en") or not wiz.get("guardian_name"):
        return redirect("portal_student_wizard_step1_edit", pk=pk) if pk else redirect("portal_student_wizard_step1")

    if request.method == "POST":
        obj = instance if pk else Student(organization=user.organization)

        obj.first_name_en = wiz["first_name_en"]
        obj.last_name_en = wiz["last_name_en"]
        obj.first_name_ar = wiz.get("first_name_ar", "")
        obj.last_name_ar = wiz.get("last_name_ar", "")
        obj.date_of_birth = timezone.datetime.fromisoformat(wiz["date_of_birth"]).date()
        obj.gender = wiz["gender"]
        obj.current_level = int(wiz.get("current_level", 1))

        obj.guardian_name = wiz["guardian_name"]
        obj.guardian_phone = wiz["guardian_phone"]
        obj.guardian_email = wiz.get("guardian_email", "")
        obj.notes = wiz.get("notes", "")

        obj.save()

        _wizard_reset(request, pk=pk)
        messages.success(request, "Student saved successfully.")
        return redirect("portal_student_list")

    return render(request, "portal/student_wizard_review.html", {
        "mode": "edit" if pk else "create",
        "pk": pk,
        "step": 3,
        "wiz": wiz,
    })


@login_required
def student_wizard_cancel(request, pk=None):
    _wizard_reset(request, pk=pk)
    messages.info(request, "Wizard cancelled.")
    return redirect("portal_student_list")


# =========================================================
# COURSE REGISTRATION (CourseEnrollment)
# =========================================================
@login_required
def course_register(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    form = CourseRegisterForm(user=user)
    students = Student.objects.filter(organization=user.organization).order_by("-created_at")

    return render(request, "portal/course_register.html", {
        "form": form,
        "students": students[:200],
        "org_name": user.organization.name_en,
    })


@login_required
def course_register_confirm(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    if request.method != "POST":
        return redirect("portal_course_register")

    form = CourseRegisterForm(request.POST, user=user)
    selected_ids = request.POST.getlist("selected_ids")

    if not form.is_valid():
        students = Student.objects.filter(organization=user.organization).order_by("-created_at")[:200]
        return render(request, "portal/course_register.html", {
            "form": form,
            "students": students,
            "org_name": user.organization.name_en,
        })

    if not selected_ids:
        messages.warning(request, "Please select at least one student.")
        return redirect("portal_course_register")

    course = form.cleaned_data["course"]

    students = Student.objects.filter(
        organization=user.organization,
        id__in=selected_ids
    ).order_by("first_name_en", "last_name_en")

    created = 0
    with transaction.atomic():
        for s in students:
            _, was_created = CourseEnrollment.objects.get_or_create(
                organization=user.organization,
                student=s,
                course=course,
                defaults={"created_by": user, "status": "DRAFT"},
            )
            if was_created:
                created += 1

    messages.success(request, f"Added {created} student(s) to {course} as Draft.")
    return render(request, "portal/course_register_confirm.html", {
        "course": course,
        "students": students,
        "created_count": created,
        "is_manager": is_manager(user),
    })

# =========================================================
# COMPETITION REGISTRATION (EventRegistration)
# =========================================================
@login_required
def competition_register(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    form = CompetitionRegisterForm(user=user)
    students = Student.objects.filter(organization=user.organization).order_by("-created_at")

    return render(request, "portal/competition_register.html", {
        "form": form,
        "students": students[:200],
        "org_name": user.organization.name_en,
        "is_manager": is_manager(user),
    })


@login_required
def competition_register_confirm(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    if request.method != "POST":
        return redirect("portal_competition_register")

    form = CompetitionRegisterForm(request.POST, user=user)
    selected_ids = request.POST.getlist("selected_ids")

    if not form.is_valid():
        students = Student.objects.filter(organization=user.organization).order_by("-created_at")[:200]
        return render(request, "portal/competition_register.html", {
            "form": form,
            "students": students,
            "org_name": user.organization.name_en,
            "is_manager": is_manager(user),
        })

    if not selected_ids:
        messages.warning(request, "Please select at least one student.")
        return redirect("portal_competition_register")

    event = form.cleaned_data["event"]

    students = Student.objects.filter(
        organization=user.organization,
        id__in=selected_ids
    ).order_by("first_name_en", "last_name_en")

    if students.count() == 0:
        messages.warning(request, "No valid students selected.")
        return redirect("portal_competition_register")

    fee_per_student = event.fee_per_student or 0
    total_fee = fee_per_student * students.count()

    created = 0
    with transaction.atomic():
        for s in students:
            _, was_created = EventRegistration.objects.get_or_create(
                organization=user.organization,
                event=event,
                student=s,
                defaults={
                    "status": "DRAFT",
                    "fee_amount": fee_per_student,  # snapshot
                }
            )
            if was_created:
                created += 1

    return render(request, "portal/competition_register_confirm.html", {
        "event": event,
        "students": students,
        "created_count": created,
        "fee_per_student": fee_per_student,
        "total_fee": total_fee,
        "is_manager": is_manager(user),
    })
@login_required
def competition_submit_confirm(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not is_manager(user):
        return render(request, "portal/forbidden.html", status=403)
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    event_id = request.GET.get("event_id") or request.POST.get("event_id")
    if not event_id:
        messages.warning(request, "Missing event_id.")
        return redirect("portal_dashboard")

    event = get_object_or_404(Event, pk=event_id)

    regs = (
        EventRegistration.objects
        .filter(organization=user.organization, event=event, status="DRAFT")
        .select_related("student")
        .order_by("-created_at")
    )

    count = regs.count()
    fee_per_student = event.fee_per_student or 0
    total_amount = fee_per_student * count

    return render(request, "portal/competition_submit_confirm.html", {
        "event": event,
        "regs": regs,
        "count": count,
        "fee_per_student": fee_per_student,
        "total_amount": total_amount,
    })


@login_required
def competition_submit_final(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not is_manager(user):
        return render(request, "portal/forbidden.html", status=403)
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    if request.method != "POST":
        return redirect("portal_dashboard")

    event_id = request.POST.get("event_id")
    selected_ids = request.POST.getlist("selected_ids")

    if not event_id:
        messages.warning(request, "Missing event_id.")
        return redirect("portal_dashboard")

    event = get_object_or_404(Event, pk=event_id)

    if not selected_ids:
        messages.warning(request, "Please select at least one draft registration.")
        return redirect("portal_competition_submit_confirm") + f"?event_id={event.id}"

    now = timezone.now()
    fee_per_student = event.fee_per_student or 0

    qs = EventRegistration.objects.filter(
        id__in=selected_ids,
        organization=user.organization,
        event=event,
        status="DRAFT",
    )

    with transaction.atomic():
        updated = qs.update(
            status="PENDING_PAYMENT",
            fee_amount=fee_per_student,
            submitted_at=now,
            submitted_by=user,
        )

    messages.success(
        request,
        f"Submitted {updated} registration(s). Total due: {fee_per_student * updated:.2f} SAR."
    )
    return redirect("portal_dashboard")
