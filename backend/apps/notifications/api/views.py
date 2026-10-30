"""Notifications screen API (HIMS-NOTIF-001): the delivery log, send again, test message."""

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.access_control.catalog import P

from ..models import Notification
from ..services import retry_now, send_test


class NotificationSerializer(serializers.ModelSerializer):
    channel_label = serializers.CharField(source="get_channel_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    can_send_again = serializers.SerializerMethodField()
    recipients = serializers.ListField(child=serializers.CharField(), read_only=True)

    def get_can_send_again(self, notification) -> bool:
        return notification.status in (
            Notification.Status.FAILED,
            Notification.Status.GAVE_UP,
        ) and bool(notification.body_encrypted)

    class Meta:
        model = Notification
        fields = [
            "id",
            "created_at",
            "channel",
            "channel_label",
            "category",
            "template",
            "recipients",
            "subject",
            "body",
            "status",
            "status_label",
            "attempts",
            "last_error",
            "next_attempt_at",
            "sent_at",
            "skip_reason",
            "can_send_again",
        ]
        read_only_fields = fields


class TestMessageSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=Notification.Channel.choices)
    to = serializers.CharField(
        max_length=254, help_text="An email address, or a phone number like +919876543210."
    )

    def validate(self, data):
        if data["channel"] == Notification.Channel.EMAIL:
            serializers.EmailField().run_validation(data["to"])
        return data


class NotificationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = NotificationSerializer
    required_permissions = {
        "list": P.NOTIFICATIONS_VIEW,
        "retrieve": P.NOTIFICATIONS_VIEW,
        "send_again": P.NOTIFICATIONS_MANAGE,
        "test": P.NOTIFICATIONS_MANAGE,
    }

    def get_queryset(self):
        queryset = Notification.objects.order_by("-created_at")
        params = self.request.query_params
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("channel"):
            queryset = queryset.filter(channel=params["channel"])
        if params.get("search"):
            term = params["search"].strip()
            queryset = queryset.filter(
                Q(subject__icontains=term)
                | Q(template__icontains=term)
                | Q(recipients__icontains=term)
            )
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, enum=[c for c, _ in Notification.Status.choices]),
            OpenApiParameter("channel", str, enum=[c for c, _ in Notification.Channel.choices]),
            OpenApiParameter(
                "search", str, description="Part of subject, message name or recipient"
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=NotificationSerializer)
    @action(detail=True, methods=["post"], url_path="send-again")
    def send_again(self, request, pk=None):
        notification = retry_now(
            actor=request.user, notification_id=self.get_object().pk, request=request
        )
        return Response(NotificationSerializer(notification).data)

    @extend_schema(request=TestMessageSerializer, responses={201: NotificationSerializer})
    @action(detail=False, methods=["post"])
    def test(self, request):
        serializer = TestMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notification = send_test(actor=request.user, request=request, **serializer.validated_data)
        return Response(NotificationSerializer(notification).data, status=status.HTTP_201_CREATED)
