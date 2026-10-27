"""Feature settings API (HIMS-ORG-004)."""

from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P
from apps.access_control.selectors import check_permission, get_permission_scope
from apps.facilities.models import Facility
from common.idempotency.decorators import idempotent
from common.permissions import FACILITY

from .. import catalog, services
from .serializers import (
    EffectiveFeaturesSerializer,
    FeatureChangeSerializer,
    FeatureStateSerializer,
)

SETTING_TO_VALUE = {"default": None, "on": True, "off": False}


def _setting(row) -> dict:
    if row is None:
        return {
            "setting": "default",
            "version": 0,
            "reason": "",
            "updated_by_name": None,
            "updated_at": None,
        }
    return {
        "setting": services.setting_label(row.enabled),
        "version": row.version,
        "reason": row.reason,
        "updated_by_name": row.updated_by.display_name if row.updated_by else None,
        "updated_at": row.updated_at,
    }


def _state(item: dict, with_facility: bool) -> dict:
    feature: catalog.Feature = item["feature"]
    return {
        "key": feature.key,
        "name": feature.name,
        "description": feature.description,
        "category": feature.category,
        "scope": feature.scope,
        "available": feature.available,
        "planned_phase": feature.planned_phase,
        "countries": sorted(feature.countries) if feature.countries else None,
        "offered_in_country": item["offered_in_country"],
        "default": item["default"],
        "hospital": _setting(item["hospital_row"]),
        "facility": _setting(item["facility_row"]) if with_facility else None,
        "enabled": item["enabled"],
    }


def _facility_in_scope(request, facility_id, codename):
    facility = Facility.objects.filter(pk=facility_id).first()
    scope = get_permission_scope(request.user, codename)
    if facility is None or not scope.covers(facility_id=facility.pk, department_id=None):
        raise Http404  # out of scope looks the same as missing
    return facility


class FeatureListView(APIView):
    """Every feature with its default and settings. With ``?facility=``: per-facility features
    only, with that facility's settings."""

    permission_scope = FACILITY
    required_permissions = {"get": P.FEATURES_VIEW}

    @extend_schema(
        parameters=[OpenApiParameter("facility", str, description="Facility id")],
        responses=FeatureStateSerializer(many=True),
    )
    def get(self, request):
        facility_id = request.query_params.get("facility")
        facility = (
            _facility_in_scope(request, facility_id, P.FEATURES_VIEW) if facility_id else None
        )
        items = services.states(facility=facility, request=request)
        data = [_state(item, with_facility=facility is not None) for item in items]
        return Response(FeatureStateSerializer(data, many=True).data)


class FeatureChangeView(APIView):
    """Turn a feature on, off or back to the default, for the hospital or one facility."""

    permission_scope = FACILITY
    required_permissions = {"post": P.FEATURES_MANAGE}

    @extend_schema(
        operation_id="features_change",
        request=FeatureChangeSerializer,
        responses=FeatureStateSerializer,
    )
    @idempotent("features.change")
    def post(self, request, key):
        if key not in catalog.BY_KEY:
            raise Http404
        serializer = FeatureChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        facility = data.get("facility")
        # Hospital-wide settings need an organization-wide grant; a facility's needs one there.
        check_permission(
            request.user, P.FEATURES_MANAGE, facility_id=facility.pk if facility else None
        )
        services.set_feature(
            actor=request.user,
            key=key,
            facility=facility,
            enabled=SETTING_TO_VALUE[data["setting"]],
            reason=data["reason"],
            version=data["version"],
            request=request,
        )
        item = next(
            i
            for i in services.states(facility=facility, request=request)
            if i["feature"].key == key
        )
        return Response(
            FeatureStateSerializer(_state(item, with_facility=facility is not None)).data,
            status=status.HTTP_200_OK,
        )


class EffectiveFeaturesView(APIView):
    """What is on right now, for the app to show or hide things.

    Before sign-in only public features are returned (e.g. whether to show "Forgot password?").
    Showing or hiding is a convenience; the server enforces every feature itself.
    """

    permission_classes = [AllowAny]

    @extend_schema(responses=EffectiveFeaturesSerializer)
    def get(self, request):
        settings_ = services.current_settings(request)
        signed_in = request.user.is_authenticated
        hospital = {
            feature.key: settings_.hospital(feature)
            for feature in catalog.FEATURES
            if signed_in or feature.public
        }
        facilities = {}
        if signed_in:
            per_facility = [f for f in catalog.FEATURES if f.scope == catalog.FACILITY]
            for facility_id in Facility.objects.values_list("pk", flat=True):
                facilities[str(facility_id)] = {
                    feature.key: settings_.at(feature, facility_id) for feature in per_facility
                }
        return Response(
            EffectiveFeaturesSerializer({"hospital": hospital, "facilities": facilities}).data
        )
