from django.urls import path

from .views import (
    CsrfTokenView,
    CurrentUserView,
    InvitationAcceptView,
    InvitationInspectView,
    LoginView,
    LogoutView,
    NoAccessReportView,
    PasswordResetConfirmView,
    PasswordResetInspectView,
    PasswordResetRequestView,
)

urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", CurrentUserView.as_view(), name="auth-me"),
    path("no-access-report/", NoAccessReportView.as_view(), name="auth-no-access-report"),
    path("invitations/inspect/", InvitationInspectView.as_view(), name="auth-invitation-inspect"),
    path("invitations/accept/", InvitationAcceptView.as_view(), name="auth-invitation-accept"),
    path(
        "password-reset/request/",
        PasswordResetRequestView.as_view(),
        name="auth-password-reset-request",
    ),
    path(
        "password-reset/inspect/",
        PasswordResetInspectView.as_view(),
        name="auth-password-reset-inspect",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
]
