from django.urls import path
from django.contrib.auth import views as auth_views
from . import views_portal as v

urlpatterns = [
    path("", v.portal_dashboard, name="portal_dashboard"),

    # Auth
    path("login/", auth_views.LoginView.as_view(template_name="portal/login.html"), name="portal_login"),
    path("logout/", auth_views.LogoutView.as_view(template_name="portal/logout.html"), name="portal_logout"),

    # Students list
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

    # Submit (managers only)
    path("submit/", v.submit_students, name="portal_submit"),
    path("submit/confirm/", v.submit_confirm, name="portal_submit_confirm"),

    # Submit Selected (from list)
    path("students/submit-selected/", v.submit_selected_confirm, name="portal_submit_selected_confirm"),
    path("students/submit-selected/final/", v.submit_selected_final, name="portal_submit_selected_final"),
]
