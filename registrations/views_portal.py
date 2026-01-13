from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Count, Q
from django.core.paginator import Paginator
from .models import Student, Event
from .forms import StudentForm,StudentStep1Form, StudentStep2Form
from datetime import date



def is_admin(user):
    return user.is_superuser or getattr(user, "role", "") == "ADMIN"

def is_manager(user):
    return getattr(user, "role", "") == "ORG_MANAGER"


@login_required
def portal_dashboard(request):
    user = request.user

    if is_admin(user):
        return redirect("/admin/")

    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    org = user.organization
    today = timezone.localdate()
    open_events = (
    Event.objects
    .filter(status="OPEN")
    .filter(Q(deadline__isnull=True) | Q(deadline__gte=today))
    .order_by("deadline", "name")
)

    # KPI counts (scoped to this organization only)
    counts = (
        Student.objects.filter(organization=org)
        .values("status")
        .annotate(c=Count("id"))
    )
    counts_map = {x["status"]: x["c"] for x in counts}

    draft_count = counts_map.get("DRAFT", 0)
    submitted_count = counts_map.get("SUBMITTED", 0)
    accepted_count = counts_map.get("ACCEPTED", 0)
    rejected_count = counts_map.get("REJECTED", 0)

    # Recent students (last 10)
    recent_students = (
        Student.objects.filter(organization=org)
        .select_related("event")
        .order_by("-created_at")[:10]
    )

    return render(request, "portal/dashboard.html", {
        "org_name": org.name_en,          # ✅ add this for the header text
        "open_events": open_events,
        "draft_count": draft_count,
        "submitted_count": submitted_count,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "recent_students": recent_students,
    })


@login_required
def student_list(request):
    user = request.user

    if is_admin(user):
        return redirect("/admin/")

    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    qs = Student.objects.filter(organization=user.organization).select_related("event").order_by("-created_at")

    # Filters
    status = (request.GET.get("status") or "").strip()
    event = (request.GET.get("event") or "").strip()
    q = (request.GET.get("q") or "").strip()

    if status:
        qs = qs.filter(status=status)

    if event:
        qs = qs.filter(event__code=event)

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

    # Event filter dropdown (OPEN events)
    today = timezone.localdate()
    open_events = (
    Event.objects
    .filter(status="OPEN")
    .filter(Q(deadline__isnull=True) | Q(deadline__gte=today))
    .order_by("deadline", "name")
)

    # Pagination
    paginator = Paginator(qs, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "portal/student_list.html", {
        "students": page_obj,            # now this is a Page object
        "page_obj": page_obj,
        "open_events": open_events,
        "selected_status": status,
        "selected_event": event,
        "q": q,
        "is_manager": is_manager(user),
    })

@login_required
def submit_selected_confirm(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")

    if not is_manager(user):
        return render(request, "portal/forbidden.html", status=403)

    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    if request.method != "POST":
        return redirect("portal_student_list")

    event_code = (request.POST.get("event_code") or "").strip()
    if not event_code:
        messages.error(request, "Please filter by Event first, then select students to submit.")
        return redirect("portal_student_list")
    today = timezone.localdate()
    event = get_object_or_404(
        Event,
        code=event_code,
        status="OPEN",
    )
    if event.deadline and event.deadline < today:
       messages.error(request, "This event deadline has passed. Please select another event.")
       messages.error(request, "This event deadline has passed. Please select another event.")
       return redirect(f"{redirect('portal_student_list').url}?event={event_code}")


    selected_ids = request.POST.getlist("selected_ids")
    if not selected_ids:
        messages.warning(request, "No students selected.")
        return redirect(f"{redirect('portal_student_list').url}?event={event_code}")

    # Only allow submitting DRAFT students belonging to this org and event
    qs = Student.objects.filter(
        id__in=selected_ids,
        organization=user.organization,
        event=event,
        status="DRAFT",
    ).order_by("-created_at")

    count = qs.count()
    if count == 0:
        messages.warning(request, "Selected students are not Draft (or not in this event). Nothing to submit.")
        return redirect("portal_student_list")

    return render(request, "portal/submit_selected_confirm.html", {
        "event": event,
        "draft_count": count,
        "students": qs[:50],   # show up to 50 in preview
        "selected_ids": list(qs.values_list("id", flat=True)),
    })


@login_required
def submit_selected_final(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")

    if not is_manager(user):
        return render(request, "portal/forbidden.html", status=403)

    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    if request.method != "POST":
        return redirect("portal_student_list")

    event_code = (request.POST.get("event_code") or "").strip()
    today = timezone.localdate()
    event = get_object_or_404(
        Event,
        code=event_code,
        status="OPEN",
    )
    if event.deadline and event.deadline < today:
       messages.error(request, "This event deadline has passed. Please select another event.")
       messages.error(request, "This event deadline has passed. Please select another event.")
       return redirect(f"{redirect('portal_student_list').url}?event={event_code}")


    selected_ids = request.POST.getlist("selected_ids")
    if not selected_ids:
        messages.warning(request, "No students selected.")
        return redirect("portal_student_list")

    qs = Student.objects.filter(
        id__in=selected_ids,
        organization=user.organization,
        event=event,
        status="DRAFT",
    )

    count = qs.count()
    if count == 0:
        messages.warning(request, "No Draft students found to submit.")
        return redirect("portal_student_list")

    now = timezone.now()
    qs.update(status="SUBMITTED", submitted_at=now, submitted_by=user)
    messages.success(request, f"Submitted {count} student(s) for {event.code}.")
    return redirect(f"{redirect('portal_student_list').url}?event={event.code}&status=SUBMITTED")

@login_required
def student_create(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")

    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    if request.method == "POST":
        form = StudentForm(request.POST, user=user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.organization = user.organization  # force bind
            obj.status = "DRAFT"  # always draft on create
            obj.save()
            messages.success(request, "Student saved as Draft.")
            return redirect("portal_student_list")
    else:
        form = StudentForm(user=user)

    return render(request, "portal/student_form.html", {"form": form, "mode": "create"})


@login_required
def student_edit(request, pk):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")

    obj = get_object_or_404(Student, pk=pk)

    # Security: must be same organization
    if not user.organization_id or obj.organization_id != user.organization_id:
        return render(request, "portal/forbidden.html", status=403)

    if obj.status == "SUBMITTED":
        messages.warning(request, "This student is submitted and cannot be edited.")
        return redirect("portal_student_list")

    if request.method == "POST":
        form = StudentForm(request.POST, instance=obj, user=user)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.organization = user.organization  # force bind
            updated.status = "DRAFT"  # keep draft
            updated.save()
            messages.success(request, "Student updated.")
            return redirect("portal_student_list")
    else:
        form = StudentForm(instance=obj, user=user)

    return render(request, "portal/student_form.html", {"form": form, "mode": "edit", "obj": obj})


@login_required
def submit_students(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")

    if not is_manager(user):
        return render(request, "portal/forbidden.html", status=403)

    if not user.organization_id:
        return render(request, "portal/no_organization.html")
    today = timezone.localdate()
    open_events = (
    Event.objects
    .filter(status="OPEN")
    .filter(Q(deadline__isnull=True) | Q(deadline__gte=today))
    .order_by("deadline", "name")
)

    # Step 1: show submit page (event selection)
    return render(request, "portal/submit.html", {
        "open_events": open_events,
    })


@login_required
def submit_confirm(request):
    user = request.user
    if is_admin(user):
        return redirect("/admin/")

    if not is_manager(user):
        return render(request, "portal/forbidden.html", status=403)

    if not user.organization_id:
        return render(request, "portal/no_organization.html")

    if request.method != "POST":
        return redirect("portal_submit")

    event_code = (request.POST.get("event_code") or "").strip()
    if not event_code:
        messages.error(request, "Please select an event.")
        return redirect("portal_submit")
    today = timezone.localdate()
    event = get_object_or_404(
        Event,
        code=event_code,
        status="OPEN",
    )
    if event.deadline and event.deadline < today:
       messages.error(request, "This event deadline has passed. Please select another event.")
       return redirect("portal_submit")

    draft_qs = Student.objects.filter(
        organization=user.organization,
        event=event,
        status="DRAFT",
    )

    draft_count = draft_qs.count()

    # If manager clicked FINAL confirm
    if request.POST.get("final") == "1":
        if draft_count == 0:
            messages.warning(request, "No Draft students to submit for this event.")
            return redirect("portal_submit")

        now = timezone.now()
        draft_qs.update(status="SUBMITTED", submitted_at=now, submitted_by=user)
        messages.success(request, f"Submitted {draft_count} student(s) for {event.code}.")
        return redirect("portal_student_list")

    # Otherwise: show confirmation page
    sample_students = draft_qs.order_by("-created_at")[:10]

    return render(request, "portal/submit_confirm.html", {
        "event": event,
        "draft_count": draft_count,
        "sample_students": sample_students,
    })




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
        instance = get_object_or_404(Student, pk=pk)
        if instance.organization_id != user.organization_id:
            return render(request, "portal/forbidden.html", status=403)
        if instance.status == "SUBMITTED":
            messages.warning(request, "This student is submitted and cannot be edited.")
            return redirect("portal_student_list")

    wiz = _wizard_get(request, pk=pk)

    # If editing and wizard empty, preload from DB
    if pk and not wiz:
        wiz = {
            "event_id": instance.event_id,
            "level": instance.level,
            "first_name_en": instance.first_name_en,
            "last_name_en": instance.last_name_en,
            "first_name_ar": instance.first_name_ar,
            "last_name_ar": instance.last_name_ar,
            "date_of_birth": instance.date_of_birth.isoformat(),
            "gender": instance.gender,
        }
        _wizard_set(request, wiz, pk=pk)

    initial = {}
    if wiz:
        initial = {
            "event": wiz.get("event_id"),
            "level": wiz.get("level"),
            "first_name_en": wiz.get("first_name_en"),
            "last_name_en": wiz.get("last_name_en"),
            "first_name_ar": wiz.get("first_name_ar"),
            "last_name_ar": wiz.get("last_name_ar"),
            "date_of_birth": wiz.get("date_of_birth"),
            "gender": wiz.get("gender"),
        }

    if request.method == "POST":
        form = StudentStep1Form(request.POST, user=user)
        if form.is_valid():
            cd = form.cleaned_data
            wiz.update({
                "event_id": cd["event"].id,
                "level": cd.get("level", ""),
                "first_name_en": cd["first_name_en"],
                "last_name_en": cd["last_name_en"],
                "first_name_ar": cd.get("first_name_ar", ""),
                "last_name_ar": cd.get("last_name_ar", ""),
                "date_of_birth": cd["date_of_birth"].isoformat(),
                "gender": cd["gender"],
            })
            _wizard_set(request, wiz, pk=pk)

            # ✅ FIX (ONLY CHANGE): pass pk when redirecting to the edit URL
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
        instance = get_object_or_404(Student, pk=pk)
        if instance.organization_id != user.organization_id:
            return render(request, "portal/forbidden.html", status=403)

    wiz = _wizard_get(request, pk=pk)

    # guard: must have step1 data
    if not wiz.get("event_id"):
        return redirect("portal_student_wizard_step1_edit" if pk else "portal_student_wizard_step1")

    # preload step2 from DB if editing and missing
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
            return redirect("portal_student_wizard_review_edit" if pk else "portal_student_wizard_review")
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
        instance = get_object_or_404(Student, pk=pk)
        if instance.organization_id != user.organization_id:
            return render(request, "portal/forbidden.html", status=403)

    wiz = _wizard_get(request, pk=pk)
    if not wiz.get("event_id") or not wiz.get("guardian_name"):
        return redirect("portal_student_wizard_step1_edit" if pk else "portal_student_wizard_step1")

    event = get_object_or_404(Event, id=wiz["event_id"])

    if request.method == "POST":
        # Final Save
        if pk:
            obj = instance
        else:
            obj = Student(organization=user.organization, status="DRAFT")

        obj.event = event
        obj.level = wiz.get("level", "")
        obj.first_name_en = wiz["first_name_en"]
        obj.last_name_en = wiz["last_name_en"]
        obj.first_name_ar = wiz.get("first_name_ar", "")
        obj.last_name_ar = wiz.get("last_name_ar", "")

        from datetime import date
        obj.date_of_birth = date.fromisoformat(wiz["date_of_birth"])

        obj.gender = wiz["gender"]
        obj.guardian_name = wiz["guardian_name"]
        obj.guardian_phone = wiz["guardian_phone"]
        obj.guardian_email = wiz.get("guardian_email", "")
        obj.notes = wiz.get("notes", "")

        obj.status = "DRAFT"
        obj.save()

        _wizard_reset(request, pk=pk)
        messages.success(request, "Student saved as Draft.")
        return redirect("portal_student_list")

    return render(request, "portal/student_wizard_review.html", {
        "mode": "edit" if pk else "create",
        "pk": pk,
        "step": 3,
        "event": event,
        "wiz": wiz,
    })


@login_required
def student_wizard_cancel(request, pk=None):
    _wizard_reset(request, pk=pk)
    messages.info(request, "Wizard cancelled.")
    return redirect("portal_student_list")
