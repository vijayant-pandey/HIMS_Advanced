"""Console access tab on the Compliance page (spec 13.1, 13.4; HIMS-SEC-015).

Shows where the admin console may be used from and which addresses it refused. The list of
allowed addresses is a server setting (HIMS_ADMIN_ALLOWED_NETWORKS), deliberately not editable
from the app or the console: what protects the console must not be changeable through it.
Reading needs ``compliance.view``; marking a refusal reviewed needs ``compliance.manage``.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P

from .. import console_access
from ..models import ConsoleAccessBlock

LIST_LIMIT = 200


class ConsoleAccessSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(help_text="The admin console is switched on here.")
    allowed_networks = serializers.ListField(child=serializers.CharField())
    your_address = serializers.CharField(allow_null=True)
    you_are_allowed = serializers.BooleanField()
    developer_pc = serializers.BooleanField()
    refusals_to_review = serializers.IntegerField()


class ConsoleAccessView(APIView):
    required_permissions = {"get": P.COMPLIANCE_VIEW}

    @extend_schema(responses=ConsoleAccessSerializer)
    def get(self, request):
        return Response(ConsoleAccessSerializer(console_access.console_status(request)).data)


class ConsoleAccessBlockSerializer(serializers.ModelSerializer):
    signed_in_user_name = serializers.CharField(
        source="signed_in_user.display_name", read_only=True, default=None, allow_null=True
    )
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.display_name", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = ConsoleAccessBlock
        fields = [
            "id",
            "day",
            "ip_address",
            "attempts",
            "last_seen_at",
            "last_path",
            "signed_in_user_name",
            "reviewed_by_name",
            "reviewed_at",
            "review_note",
            "version",
        ]
        read_only_fields = fields


class ConsoleBlockReviewSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class ConsoleAccessBlockViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ConsoleAccessBlockSerializer
    pagination_class = None
    required_permissions = {"list": P.COMPLIANCE_VIEW, "review": P.COMPLIANCE_MANAGE}

    def get_queryset(self):
        rows = ConsoleAccessBlock.objects.select_related("signed_in_user", "reviewed_by")
        return rows if self.action != "list" else rows[:LIST_LIMIT]

    @extend_schema(request=ConsoleBlockReviewSerializer, responses=ConsoleAccessBlockSerializer)
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        serializer = ConsoleBlockReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        block = console_access.review_block(
            actor=request.user,
            block_id=self.get_object().pk,
            request=request,
            **serializer.validated_data,
        )
        return Response(ConsoleAccessBlockSerializer(block).data)
