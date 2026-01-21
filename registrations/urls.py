from django.urls import path
from django.contrib.auth import views as auth_views
from . import views_portal as v

urlpatterns = [
    path("", v.portal_dashboard, name="portal_dashboard"),

    # Auth
    path("login/", auth_views.LoginView.as_view(template_name="portal/login.html"), name="portal_login"),
    path("logout/", auth_views.LogoutView.as_view(template_name="portal/logout.html"), name="portal_logout"),

    # Students
    path("students/", v.student_list, name="portal_student_list"),

    # Wizard (Create)
    path("students/add/", v.student_wizard_start, name="portal_student_add"),
    path("students/wizard/step-1/", v.student_wizard_step1, name="portal_student_wizard_step1"),
    path("students/wizard/step-2/", v.student_wizard_step2, name="portal_student_wizard_step2"),
    path("students/wizard/review/", v.student_wizard_review, name="portal_student_wizard_review"),
    path("students/wizard/cancel/", v.student_wizard_cancel, name="portal_student_wizard_cancel"),

    # Wizard (Edit)
    path("students/<int:pk>/edit/", v.student_wizard_step1, name="portal_student_edit"),
    path("students/<int:pk>/wizard/step-1/", v.student_wizard_step1, name="portal_student_wizard_step1_edit"),
    path("students/<int:pk>/wizard/step-2/", v.student_wizard_step2, name="portal_student_wizard_step2_edit"),
    path("students/<int:pk>/wizard/review/", v.student_wizard_review, name="portal_student_wizard_review_edit"),
    path("students/<int:pk>/wizard/cancel/", v.student_wizard_cancel, name="portal_student_wizard_cancel_edit"),

    # Course registration
    path("courses/register/", v.course_register, name="portal_course_register"),
    path("courses/register/confirm/", v.course_register_confirm, name="portal_course_register_confirm"),

    # Competition registration
    path("competitions/register/", v.competition_register, name="portal_competition_register"),
    path("competitions/register/confirm/", v.competition_register_confirm, name="portal_competition_register_confirm"),

    # Manager submit + payment step
    path("competitions/submit/confirm/", v.competition_submit_confirm, name="portal_competition_submit_confirm"),
    path("competitions/submit/final/", v.competition_submit_final, name="portal_competition_submit_final"),
]

