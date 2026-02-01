from django.urls import path
from django.contrib.auth import views as auth_views
from . import views_portal as v

urlpatterns = [
    # Dashboard
    path("", v.portal_dashboard, name="portal_dashboard"),

    # Auth
    path("login/", auth_views.LoginView.as_view(
        template_name="portal/login.html"
    ), name="portal_login"),
    path("logout/", auth_views.LogoutView.as_view(), name="portal_logout"),

    # Students
    path("students/", v.student_list, name="portal_student_list"),

    # Student Wizard (Create)
    path("students/add/", v.student_wizard_start, name="portal_student_add"),
    path("students/wizard/step-1/", v.student_wizard_step1, name="portal_student_wizard_step1"),
    path("students/wizard/step-2/", v.student_wizard_step2, name="portal_student_wizard_step2"),
    path("students/wizard/review/", v.student_wizard_review, name="portal_student_wizard_review"),
    path("students/wizard/cancel/", v.student_wizard_cancel, name="portal_student_wizard_cancel"),

    # Student Wizard (Edit)
    path("students/<int:pk>/edit/", v.student_wizard_step1, name="portal_student_edit"),
    path("students/<int:pk>/wizard/step-1/", v.student_wizard_step1, name="portal_student_wizard_step1_edit"),
    path("students/<int:pk>/wizard/step-2/", v.student_wizard_step2, name="portal_student_wizard_step2_edit"),
    path("students/<int:pk>/wizard/review/", v.student_wizard_review, name="portal_student_wizard_review_edit"),
    path("students/<int:pk>/wizard/cancel/", v.student_wizard_cancel, name="portal_student_wizard_cancel_edit"),

    # =========================
    # COURSE REGISTRATION FLOW
    # =========================

    # Staff adds students → Draft
    path("courses/register/", v.course_register, name="portal_course_register"),
    path("courses/register/confirm/", v.course_register_confirm, name="portal_course_register_confirm"),
    path("courses/enrollments/", v.course_enrollment_list, name="portal_course_enrollment_list"), 
    # Manager submits to admin
    path("courses/submit/confirm/", v.course_submit_confirm, name="portal_course_submit_confirm"),
    path("courses/submit/final/", v.course_submit_final, name="portal_course_submit_final"),

    path("courses/enrollments/submit/", v.course_enrollment_submit_selected, name="portal_course_enrollment_submit_selected"),
    path("courses/submission-inbox/", v.portal_course_submission_inbox, name="portal_course_submission_inbox"),
    # =============================
    # COMPETITION REGISTRATION FLOW
    # =============================

    path("competitions/register/", v.competition_register, name="portal_competition_register"),
    path("competitions/register/confirm/", v.competition_register_confirm, name="portal_competition_register_confirm"),

    path("competitions/submit/confirm/", v.competition_submit_confirm, name="portal_competition_submit_confirm"),
    path("competitions/submit/final/", v.competition_submit_final, name="portal_competition_submit_final"),
    path("competitions/submission-inbox/", v.competition_submission_inbox, name="portal_competition_submission_inbox"),


    path("invoices/<int:invoice_id>/", v.invoice_detail, name="portal_invoice_detail"),
    path("invoices/", v.invoice_list, name="portal_invoice_list"),
    path("invoices/<int:invoice_id>/pdf/", v.invoice_pdf, name="portal_invoice_pdf"),

]