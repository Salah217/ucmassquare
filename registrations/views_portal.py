from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q
from django.core.paginator import Paginator
from django.db import transaction
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.views.decorators.http import require_POST
from django.db.models import Count
from django.http import HttpResponseForbidden
from .invoicing import issue_invoice_for_event_regs



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
# ---------------------------@login_required
def portal_dashboard(request):
    org = getattr(request.user, "organization", None)
    today = timezone.now().date()

    # ✅ Students KPI
    total_students = 0
    if org:
        total_students = Student.objects.filter(organization=org).count()

    # ---- COURSE ENROLLMENT COUNTS (per org) ----
    course_draft_count = 0
    course_submitted_count = 0

    if org:
        course_draft_count = CourseEnrollment.objects.filter(
            organization=org, status="DRAFT"
        ).count()

        course_submitted_count = CourseEnrollment.objects.filter(
            organization=org, status="SUBMITTED"
        ).count()

    # ✅ ---- COMPETITION REGISTRATION COUNTS (per org) ----
    comp_draft_count = 0
    comp_unpaid_count = 0
    comp_paid_count = 0
    comp_accepted_count = 0

    if org:
        comp_draft_count = EventRegistration.objects.filter(
            organization=org, status="DRAFT"
        ).count()

        comp_unpaid_count = EventRegistration.objects.filter(
            organization=org, status="PENDING_PAYMENT"
        ).count()

        comp_paid_count = EventRegistration.objects.filter(
            organization=org, status="PAID"
        ).count()

        comp_accepted_count = EventRegistration.objects.filter(
            organization=org, status="ACCEPTED"
        ).count()

    # ---- OPEN COURSES ----
    open_courses = (
        Course.objects
        .filter(is_active=True)
        .order_by("start_date", "-created_at")
    )[:6]

    # ---- OPEN EVENTS ----
    open_events = (
        Event.objects
        .filter(status="OPEN", deadline__gte=today)
        .order_by("deadline", "-created_at")
    )[:6]

    notices = []

    ctx = {
        "org": org,
        "total_students": total_students,

        # courses
        "course_draft_count": course_draft_count,
        "course_submitted_count": course_submitted_count,

        # ✅ competitions
        "comp_draft_count": comp_draft_count,
        "comp_unpaid_count": comp_unpaid_count,
        "comp_paid_count": comp_paid_count,
        "comp_accepted_count": comp_accepted_count,

        # lists
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
    org = user.organization
    if not org:
        return render(request, "portal/no_organization.html")

    courses = Course.objects.filter(is_active=True).order_by("level")

    course_id = request.GET.get("course_id") or request.POST.get("course_id")
    selected_course = None
    students = Student.objects.none()

    if course_id:
        selected_course = get_object_or_404(Course, id=course_id, is_active=True)

        prereq_level = selected_course.level - 1  # Level 1 -> prereq 0

        # ✅ Base eligible by level + organization
        students = Student.objects.filter(
            organization=org,
            current_level=prereq_level
        ).order_by("first_name_en", "last_name_en")

        # ✅ Exclude students who already have an enrollment for this course
        #    Block DRAFT too, so draft students won't appear again
        BLOCK = {
            "DRAFT", "SUBMITTED", "ACCEPTED", "PENDING_PAYMENT",
            "PAID", "ENROLLED", "COMPLETED"
        }

        enrolled_ids = CourseEnrollment.objects.filter(
            organization=org,          # ✅ IMPORTANT
            course=selected_course,
            status__in=BLOCK
        ).values_list("student_id", flat=True)

        students = students.exclude(id__in=enrolled_ids)

    return render(request, "portal/course_register.html", {
        "courses": courses,
        "selected_course": selected_course,
        "students": students,
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

    course_id = request.POST.get("course_id")
    selected_ids = request.POST.getlist("selected_ids")

    if not course_id:
        messages.warning(request, "Please choose a course.")
        return redirect("portal_course_register")

    course = get_object_or_404(Course, id=course_id, is_active=True)

    if not selected_ids:
        messages.warning(request, "Please select at least one student.")
        return redirect(f"{reverse('portal_course_register')}?course_id={course.id}")

    students_qs = Student.objects.filter(
        organization=user.organization,
        id__in=selected_ids
    ).order_by("first_name_en", "last_name_en")

    students = list(students_qs)

    created = 0
    already = 0
    reactivated = 0
    RESETTABLE = {"REJECTED", "DROPPED"}

    with transaction.atomic():
        for s in students:
            enrollment, was_created = CourseEnrollment.objects.get_or_create(
                organization=user.organization,
                student=s,
                course=course,
                defaults={"created_by": user, "status": "DRAFT"},
            )

            if was_created:
                created += 1
            else:
                if enrollment.status in RESETTABLE:
                    enrollment.status = "DRAFT"
                    enrollment.created_by = user
                    enrollment.submitted_at = None
                    enrollment.submitted_by = None
                    enrollment.approved_at = None
                    enrollment.approved_by = None
                    enrollment.rejection_reason = ""
                    enrollment.invoice_no = ""
                    enrollment.paid_at = None
                    enrollment.payment_ref = ""
                    enrollment.save()
                    reactivated += 1
                else:
                    already += 1

            s.enrollment_status = enrollment.status

    return render(request, "portal/course_register_confirm.html", {
        "course": course,
        "students": students,
        "created_count": created,
        "reactivated_count": reactivated,
        "already_count": already,
        "is_manager": is_manager(user),
    })

@login_required
def course_submit(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    if request.method != "POST":
        return redirect("portal_course_register")

    if not is_manager(user):
        return HttpResponseForbidden("Manager access required")

    course_id = request.POST.get("course_id")
    course = get_object_or_404(Course, id=course_id, is_active=True)

    qs = CourseEnrollment.objects.filter(
        organization=user.organization,
        course=course,
        status="DRAFT",
    )

    count = qs.count()
    if count == 0:
        messages.warning(request, "No draft enrollments to submit.")
        return redirect(f"{reverse('portal_course_register')}?course_id={course.id}")

    now = timezone.now()
    qs.update(
        status="SUBMITTED",
        submitted_at=now,
        submitted_by=user,
    )

    messages.success(request, f"Submitted {count} enrollment(s).")
    return redirect(f"{reverse('portal_course_register')}?course_id={course.id}")

# =========================================================
# COURSE MANAGER SUBMIT (CourseEnrollment workflow)
# =========================================================

from django.views.decorators.http import require_POST

@login_required
def course_submit_confirm(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")
    if not is_manager(user):
        return HttpResponseForbidden("Manager access required")

    course_id = request.GET.get("course_id")
    if not course_id:
        messages.warning(request, "Missing course_id.")
        return redirect("portal_course_enrollment_list")

    course = get_object_or_404(Course, id=course_id, is_active=True)

    drafts = CourseEnrollment.objects.filter(
        organization=user.organization,
        course=course,
        status="DRAFT",
    ).select_related("student").order_by("student__sa_registration_no")

    selected_count = drafts.count()
    fee_per_student = course.fee or 0
    total_amount = fee_per_student * selected_count

    return render(request, "portal/course_submit_confirm.html", {
        "course": course,
        "drafts": drafts,
        "selected_count": selected_count,
        "fee_per_student": fee_per_student,
        "total_amount": total_amount,
        "is_manager": True,
    })
    
@login_required
@require_POST
def course_submit_final(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")
    if not is_manager(user):
        return HttpResponseForbidden("Manager access required")

    course_id = request.POST.get("course_id")
    selected_ids = request.POST.getlist("selected_ids")

    if not course_id:
        messages.warning(request, "Missing course_id.")
        return redirect("portal_course_enrollment_list")

    course = get_object_or_404(Course, id=course_id, is_active=True)

    if not selected_ids:
        messages.warning(request, "Please select at least one draft enrollment.")
        return HttpResponseRedirect(reverse("portal_course_submit_confirm") + f"?course_id={course.id}")

    now = timezone.now()

    qs = CourseEnrollment.objects.filter(
        id__in=selected_ids,
        organization=user.organization,
        course=course,
        status="DRAFT",
    )

    with transaction.atomic():
        updated = qs.update(
            status="SUBMITTED",
            submitted_at=now,
            submitted_by=user,
        )

    messages.success(request, f"Submitted {updated} enrollment(s) to admin.")
    return redirect("portal_course_enrollment_list")

@login_required
def course_enrollment_list(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    qs = (
        CourseEnrollment.objects
        .filter(organization=user.organization)
        .select_related("student", "course")
        .order_by("-created_at")
    )

    status = (request.GET.get("status") or "").strip()
    q = (request.GET.get("q") or "").strip()

    if status:
        qs = qs.filter(status=status)

    if q:
        qs = qs.filter(
            Q(student__sa_registration_no__icontains=q) |
            Q(student__first_name_en__icontains=q) |
            Q(student__last_name_en__icontains=q) |
            Q(course__name__icontains=q)
        )

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    # ✅ safest: read choices from model field directly (never breaks)
    status_choices = CourseEnrollment._meta.get_field("status").choices

    return render(request, "portal/course_enrollment_list.html", {
        "enrollments": page_obj,
        "page_obj": page_obj,
        "status": status,
        "q": q,
        "is_manager": is_manager(user),
        "STATUS_CHOICES": status_choices,
    })



@login_required
@require_POST
def course_enrollment_submit_selected(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    ids = request.POST.getlist("enrollment_ids")
    if not ids:
        messages.warning(request, "Please select at least one enrollment to submit.")
        return redirect("portal_course_enrollment_list")

    with transaction.atomic():
        updated = CourseEnrollment.objects.filter(
            organization=user.organization,
            id__in=ids,
            status="DRAFT",
        ).update(status="SUBMITTED")

    messages.success(request, f"Submitted {updated} enrollment(s) for admin approval.")
    return redirect("portal_course_enrollment_list")


@login_required
def portal_course_submission_inbox(request):
    user = request.user

    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")
    if not is_manager(user):
        return HttpResponseForbidden("Manager access required")

    org = user.organization

    rows = (
        CourseEnrollment.objects
        .filter(organization=org, status="DRAFT", course__is_active=True)
        .values("course_id", "course__name", "course__level", "course__fee")
        .annotate(draft_count=Count("id"))
        .order_by("course__level", "course__name")
    )

    total_drafts = sum(r["draft_count"] for r in rows) if rows else 0
    course_with_drafts = len(rows)

    return render(request, "portal/course_submission_inbox.html", {
        "rows": rows,
        "total_drafts": total_drafts,
        "course_with_drafts": course_with_drafts,
        "is_manager": True,
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

    submitted = request.GET.get("submitted")
    try:
        submitted = int(submitted) if submitted is not None else None
    except ValueError:
        submitted = None

    fee_per_student = event.fee_per_student or 0

    # Always show current drafts for review table
    regs = (
        EventRegistration.objects
        .filter(organization=user.organization, event=event, status="DRAFT")
        .select_related("student")
        .order_by("-created_at")
    )

    draft_count = regs.count()

    # If we just submitted, show the submitted count on the page (not draft_count)
    display_count = submitted if submitted is not None else draft_count
    total_amount = fee_per_student * display_count

    return render(request, "portal/competition_submit_confirm.html", {
        "event": event,
        "regs": regs,
        "count": draft_count,              # drafts remaining (table)
        "created_count": display_count,    # KPI number to display
        "fee_per_student": fee_per_student,
        "total_amount": total_amount,
        "just_submitted": submitted is not None,
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
        return HttpResponseRedirect(
            reverse("portal_competition_submit_confirm") + f"?event_id={event.id}"
        )

    now = timezone.now()
    fee_per_student = event.fee_per_student or 0

    # only drafts can be submitted
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

        # ✅ create invoice for the now-pending regs that have no invoice yet
        regs_pending = (
            EventRegistration.objects
            .filter(
                id__in=selected_ids,
                organization=user.organization,
                event=event,
                status="PENDING_PAYMENT",
                invoice__isnull=True,
            )
            .select_related("student")
        )

        inv = None
        if regs_pending.exists():
            inv = issue_invoice_for_event_regs(
                org=user.organization,
                event=event,
                regs=regs_pending,
                issued_by=None,  # optional: keep empty for manager-issued
            )

    # message + redirect
    if updated == 0:
        messages.warning(request, "No draft registrations were submitted (maybe already submitted).")
        return redirect("portal_dashboard")

    if inv:
        messages.success(
            request,
            f"Submitted {updated} registration(s). Invoice {inv.invoice_no} created. Total: {inv.total} SAR."
        )
        return redirect("portal_invoice_detail", invoice_id=inv.id)

    # fallback (shouldn't happen unless all had invoices already)
    messages.success(
        request,
        f"Submitted {updated} registration(s). Total due: {fee_per_student * updated:.2f} SAR."
    )
    return redirect("portal_dashboard")


@login_required
def competition_submission_inbox(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")
    if not is_manager(user):
        return render(request, "portal/forbidden.html", status=403)

    org = user.organization
    event_id = request.GET.get("event_id")  # optional filter

    qs = (
        EventRegistration.objects
        .filter(organization=org, status="DRAFT", event__status="OPEN")
    )

    if event_id:
        qs = qs.filter(event_id=event_id)

    rows = (
        qs.values(
            "event_id",
            "event__code",
            "event__name",
            "event__deadline",
            "event__fee_per_student",
        )
        .annotate(draft_count=Count("id"))
        .order_by("event__deadline", "event__name")
    )

    total_drafts = sum(r["draft_count"] for r in rows) if rows else 0
    events_with_drafts = len(rows)

    return render(request, "portal/competition_submission_inbox.html", {
        "rows": rows,
        "total_drafts": total_drafts,
        "events_with_drafts": events_with_drafts,
        "is_manager": True,
        "filtered_event_id": event_id,
    })

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import Invoice

def is_admin(user):
    return getattr(user, "role", "") == "ADMIN" or user.is_superuser

@login_required
def invoice_detail(request, invoice_id):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")

    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    invoice = get_object_or_404(
        Invoice.objects.select_related("seller", "organization").prefetch_related("items__student"),
        pk=invoice_id,
        organization=user.organization
    )

    return render(request, "portal/invoice_detail.html", {
        "invoice": invoice,
        "items": invoice.items.all(),
    })

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from .models import Invoice

def is_admin(user):
    return getattr(user, "role", "") == "ADMIN" or user.is_superuser

@login_required
def invoice_list(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")
    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    qs = (
        Invoice.objects
        .filter(organization=user.organization)
        .select_related("seller", "organization")
        .order_by("-created_at")
    )

    # optional filter: ?status=PAID or ?type=EVENT
    status = request.GET.get("status")
    inv_type = request.GET.get("type")
    if status:
        qs = qs.filter(status=status)
    if inv_type:
        qs = qs.filter(invoice_type=inv_type)

    return render(request, "portal/invoice_list.html", {
        "invoices": qs[:200],
        "status": status,
        "inv_type": inv_type,
    })
