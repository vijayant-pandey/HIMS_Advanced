"""Security review tab on the Compliance page (spec 13, 23; HIMS-SEC-011): the Phase 1 review's
findings, the spec 13.5 security tests, what remains before go-live, and the live encryption key
status. Read-only: the review is kept in code (``apps/compliance/security_review.py``)."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P

from .. import encryption, security_review


class ReviewFindingSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=security_review.SEVERITIES)
    area = serializers.CharField()
    finding = serializers.CharField()
    fix = serializers.CharField()
    status = serializers.ChoiceField(choices=security_review.FINDING_STATUSES)


class ReviewCheckSerializer(serializers.Serializer):
    area = serializers.CharField()
    result = serializers.CharField()


class SecurityTestCaseSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    case = serializers.CharField(help_text="As written in spec 13.5.")
    status = serializers.ChoiceField(choices=security_review.CASE_STATUSES)
    status_label = serializers.CharField()
    how = serializers.CharField()
    tests = serializers.IntegerField(help_text="Automated tests that prove it.")


class GoLiveItemSerializer(serializers.Serializer):
    ticket = serializers.CharField()
    what = serializers.CharField()


class EncryptedFieldSerializer(serializers.Serializer):
    name = serializers.CharField()
    values = serializers.IntegerField()
    on_older_keys = serializers.IntegerField()


class EncryptionStatusSerializer(serializers.Serializer):
    keys = serializers.IntegerField(help_text="Keys configured (newest first).")
    fields = EncryptedFieldSerializer(many=True)
    on_older_keys = serializers.IntegerField(
        help_text="Stored secrets an older key is still needed for; 0 means old keys can go."
    )


class SecurityReviewSerializer(serializers.Serializer):
    reviewed_on = serializers.DateField()
    reviewer = serializers.CharField()
    scope = serializers.CharField()
    method = serializers.CharField()
    findings = ReviewFindingSerializer(many=True)
    checked = ReviewCheckSerializer(many=True)
    cases = SecurityTestCaseSerializer(many=True)
    before_go_live = GoLiveItemSerializer(many=True)
    encryption = EncryptionStatusSerializer()


class SecurityReviewView(APIView):
    """The Phase 1 security review and the encryption key status."""

    required_permissions = {"get": P.COMPLIANCE_VIEW}

    @extend_schema(responses=SecurityReviewSerializer)
    def get(self, request):
        data = {**security_review.summary(), "encryption": encryption.status()}
        return Response(SecurityReviewSerializer(data).data)
