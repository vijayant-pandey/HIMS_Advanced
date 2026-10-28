"""Sign-in accounts screen (HIMS-IAM-015): every account, including people who are not staff."""

from django.db.models import Exists, OuterRef, Prefetch, Q, Subquery
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.access_control.catalog import P
from apps.access_control.models import RoleAssignment
from common.idempotency.decorators import idempotent

from .. import accounts, mfa
from ..invitations import issue_invitation
from ..models import Invitation, MfaDevice, User, UserSession
from ..sessions import end_user_sessions


class AccountSerializer(serializers.ModelSerializer):
    activated = serializers.SerializerMethodField(help_text="Has chosen a password.")
    two_factor_enabled = serializers.BooleanField(read_only=True)
    invitation_expires_at = serializers.DateTimeField(read_only=True, allow_null=True)
    staff_member_id = serializers.UUIDField(read_only=True, allow_null=True)
    roles = serializers.SerializerMethodField(help_text="Current roles and where they apply.")

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "display_name",
            "is_active",
            "activated",
            "two_factor_enabled",
            "invitation_expires_at",
            "staff_member_id",
            "roles",
            "last_login",
            "date_joined",
        ]
        read_only_fields = fields

    def get_activated(self, user) -> bool:
        return user.has_usable_password()

    def get_roles(self, user) -> list[str]:
        names = []
        for grant in user.current_grants:
            where = grant.department or grant.facility
            names.append(f"{grant.role.name} ({where.name})" if where else grant.role.name)
        return names


class AccountCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    display_name = serializers.CharField(max_length=150)
    reason = serializers.CharField(max_length=2000, help_text="e.g. External auditor for FY 26-27")


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000)


class AccountViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Everyone who can (or could) sign in. Staff accounts follow the person's employment
    status; accounts of people who are not staff are switched off and on here."""

    serializer_class = AccountSerializer
    required_permissions = {
        "list": P.ROLES_VIEW,
        "retrieve": P.ROLES_VIEW,
        "create": P.ACCOUNTS_MANAGE,
        "deactivate": P.ACCOUNTS_MANAGE,
        "reactivate": P.ACCOUNTS_MANAGE,
        "invitation": P.ACCOUNTS_MANAGE,
        "reset_two_factor": P.ACCOUNTS_MANAGE,
        "sign_out_everywhere": P.ACCOUNTS_MANAGE,
    }

    def get_queryset(self):
        now = timezone.now()
        current = (
            RoleAssignment.objects.filter(revoked_at__isnull=True, valid_from__lte=now)
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
            .select_related("role", "facility", "department")
        )
        open_invitation = Invitation.objects.filter(
            user=OuterRef("pk"),
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=now,
        ).order_by("-expires_at")
        queryset = (
            User.objects.annotate(
                two_factor_enabled=Exists(
                    MfaDevice.objects.filter(user=OuterRef("pk"), confirmed_at__isnull=False)
                ),
                invitation_expires_at=Subquery(open_invitation.values("expires_at")[:1]),
                staff_member_id=Subquery(
                    User.objects.filter(pk=OuterRef("pk")).values("staff_member__id")[:1]
                ),
            )
            .prefetch_related(Prefetch("role_assignments", current, to_attr="current_grants"))
            .order_by("display_name")
        )
        params = self.request.query_params
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) | Q(display_name__icontains=search)
            )
        kind = params.get("kind")
        if kind == "not_staff":
            queryset = queryset.filter(staff_member__isnull=True)
        elif kind == "staff":
            queryset = queryset.filter(staff_member__isnull=False)
        if params.get("status") in ("active", "inactive"):
            queryset = queryset.filter(is_active=params["status"] == "active")
        return queryset

    def _fresh(self, user):
        return AccountSerializer(self.get_queryset().get(pk=user.pk)).data

    @extend_schema(
        parameters=[
            OpenApiParameter("search", str, description="Part of a name or email"),
            OpenApiParameter("kind", str, description="staff or not_staff"),
            OpenApiParameter("status", str, description="active or inactive"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=AccountCreateSerializer, responses={201: AccountSerializer})
    @idempotent("accounts.create")
    def create(self, request):
        serializer = AccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = accounts.create_account(
            actor=request.user, request=request, **serializer.validated_data
        )
        return Response(self._fresh(user), status=status.HTTP_201_CREATED)

    @extend_schema(request=ReasonSerializer, responses=AccountSerializer)
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Switch off an account of someone who is not staff (signs them out everywhere)."""
        return self._set_active(request, active=False)

    @extend_schema(request=ReasonSerializer, responses=AccountSerializer)
    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        return self._set_active(request, active=True)

    def _set_active(self, request, *, active: bool):
        user = self.get_object()
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        accounts.set_account_active(
            actor=request.user,
            user_id=user.pk,
            active=active,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(self._fresh(user))

    @extend_schema(request=None, responses=AccountSerializer)
    @action(detail=True, methods=["post"])
    def invitation(self, request, pk=None):
        """(Re)send the activation email to an account that has not chosen a password yet."""
        user = self.get_object()
        if not user.is_active or user.has_usable_password():
            from common.exceptions import ConflictError

            raise ConflictError(
                "Only active accounts that are not activated yet can be invited.",
                code="NOT_INVITABLE",
            )
        issue_invitation(user=user, actor=request.user, request=request)
        return Response(self._fresh(user))

    @extend_schema(request=None, responses=AccountSerializer)
    @action(detail=True, methods=["post"], url_path="reset-two-factor")
    def reset_two_factor(self, request, pk=None):
        """Lost phone: remove two-factor; the person sets it up again at the next sign-in."""
        user = self.get_object()
        mfa.admin_reset(user=user, actor=request.user, request=request)
        return Response(self._fresh(user))

    @extend_schema(request=None, responses=AccountSerializer)
    @action(detail=True, methods=["post"], url_path="sign-out-everywhere")
    def sign_out_everywhere(self, request, pk=None):
        user = self.get_object()
        end_user_sessions(
            user,
            reason=UserSession.EndReason.SIGNED_OUT_BY_ADMIN,
            actor=request.user,
            request=request,
            keep_session_key=request.session.session_key if user.pk == request.user.pk else None,
        )
        return Response(self._fresh(user))
