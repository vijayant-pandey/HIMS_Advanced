"""Message wording API (HIMS-NOTIF-003): see, change, preview and put back the standard."""

from django.utils.functional import cached_property
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.access_control.catalog import P

from ..message_catalog import BY_KEY, MessageSpec
from ..message_templates import ensure_templates, preview, reset_template, update_template
from ..models import MessageTemplate


class TemplateVariableSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    required = serializers.BooleanField()


class MessageTemplateSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    when = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    subject = serializers.SerializerMethodField(help_text="The wording in use")
    body = serializers.SerializerMethodField(help_text="The wording in use")
    standard_subject = serializers.SerializerMethodField()
    standard_body = serializers.SerializerMethodField()
    is_customised = serializers.SerializerMethodField()
    variables = serializers.SerializerMethodField()
    updated_by_name = serializers.CharField(
        source="updated_by.display_name", read_only=True, allow_null=True, default=None
    )

    def _spec(self, template) -> MessageSpec:
        return BY_KEY[template.key]

    def get_name(self, template) -> str:
        return self._spec(template).name

    def get_when(self, template) -> str:
        return self._spec(template).when

    def get_category(self, template) -> str:
        return self._spec(template).category

    def get_subject(self, template) -> str:
        return template.subject or self._spec(template).subject

    def get_body(self, template) -> str:
        return template.body or self._spec(template).body

    def get_standard_subject(self, template) -> str:
        return self._spec(template).subject

    def get_standard_body(self, template) -> str:
        return self._spec(template).body

    def get_is_customised(self, template) -> bool:
        return bool(template.subject or template.body)

    @extend_schema_field(TemplateVariableSerializer(many=True))
    def get_variables(self, template) -> list[dict]:
        spec = self._spec(template)
        return [
            {
                "name": variable.name,
                "description": variable.description,
                "required": variable.name in spec.required,
            }
            for variable in spec.variables
        ]

    class Meta:
        model = MessageTemplate
        fields = [
            "id",
            "key",
            "name",
            "when",
            "category",
            "subject",
            "body",
            "standard_subject",
            "standard_body",
            "is_customised",
            "variables",
            "version",
            "updated_at",
            "updated_by_name",
        ]
        read_only_fields = fields


class MessageWordingSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=255)
    body = serializers.CharField(max_length=5000)


class MessageTemplateUpdateSerializer(MessageWordingSerializer):
    version = serializers.IntegerField(min_value=1)


class MessageTemplateResetSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class MessagePreviewSerializer(serializers.Serializer):
    subject = serializers.CharField()
    body = serializers.CharField()


class MessageTemplateViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = MessageTemplateSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head"]
    required_permissions = {
        "list": P.NOTIFICATIONS_VIEW,
        "retrieve": P.NOTIFICATIONS_VIEW,
        "preview": P.NOTIFICATIONS_VIEW,
        "partial_update": P.MESSAGE_TEMPLATES_MANAGE,
        "reset": P.MESSAGE_TEMPLATES_MANAGE,
    }
    # Wording goes to everyone, including sign-in links: a stolen session must not change it.
    sensitive_actions = ("partial_update", "reset")

    @cached_property
    def _known(self):
        return list(BY_KEY)

    def get_queryset(self):
        # A row of a message no longer in the catalog stays in the table, but is not shown.
        return MessageTemplate.objects.filter(key__in=self._known).select_related("updated_by")

    def list(self, request, *args, **kwargs):
        ensure_templates()
        return super().list(request, *args, **kwargs)

    @extend_schema(request=MessageTemplateUpdateSerializer, responses=MessageTemplateSerializer)
    def partial_update(self, request, pk=None):
        template = self.get_object()
        serializer = MessageTemplateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = update_template(
            actor=request.user,
            template_id=template.pk,
            request=request,
            **serializer.validated_data,
        )
        return Response(MessageTemplateSerializer(template).data)

    @extend_schema(request=MessageTemplateResetSerializer, responses=MessageTemplateSerializer)
    @action(detail=True, methods=["post"])
    def reset(self, request, pk=None):
        template = self.get_object()
        serializer = MessageTemplateResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = reset_template(
            actor=request.user,
            template_id=template.pk,
            request=request,
            **serializer.validated_data,
        )
        return Response(MessageTemplateSerializer(template).data)

    @extend_schema(request=MessageWordingSerializer, responses=MessagePreviewSerializer)
    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        """How this wording would read, with made-up values. Nothing is saved or sent."""
        serializer = MessageWordingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subject, body = preview(
            BY_KEY[self.get_object().key],
            serializer.validated_data["subject"],
            serializer.validated_data["body"],
        )
        return Response(MessagePreviewSerializer({"subject": subject, "body": body}).data)
