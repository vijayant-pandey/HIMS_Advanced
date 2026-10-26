from django.urls import path

from .views import (
    CsrfTokenView,
    CurrentUserView,
    InvitationAcceptView,
    InvitationInspectView,
    LoginView,
    LogoutView,
)

urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", CurrentUserView.as_view(), name="auth-me"),
    path("invitations/inspect/", InvitationInspectView.as_view(), name="auth-invitation-inspect"),
    path("invitations/accept/", InvitationAcceptView.as_view(), name="auth-invitation-accept"),
]
