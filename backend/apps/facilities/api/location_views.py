"""API for buildings, floors, wards and rooms (HIMS-FAC-004). Beds: apps/beds/api."""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.access_control.catalog import P
from apps.access_control.selectors import check_permission
from common.idempotency.decorators import idempotent
from common.permissions import FACILITY, filter_by_facility_scope

from .. import location_services
from ..models import Building, Floor, Room, Ward
from . import location_serializers as s


class LocationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Facility-scoped list/retrieve/create/update shared by every location level.

    Subclasses set ``model``, the three serializers, ``parent_field`` and the query filters.
    Creating checks ``locations.manage`` at the *parent's* facility; editing checks it at the
    object's facility. Nothing is ever deleted (deactivate with ``is_active: false``).
    """

    model = None
    create_serializer = None
    update_serializer = None
    parent_field = ""
    filters: dict[str, str] = {}

    permission_scope = FACILITY
    required_permissions = {
        "list": P.LOCATIONS_VIEW,
        "retrieve": P.LOCATIONS_VIEW,
        "create": P.LOCATIONS_MANAGE,
        "partial_update": P.LOCATIONS_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    def get_queryset(self):
        queryset = filter_by_facility_scope(self, self.model.objects.all())
        for param, lookup in self.filters.items():
            value = self.request.query_params.get(param)
            if value:
                queryset = queryset.filter(**{lookup: value})
        if self.request.query_params.get("active") == "true":
            queryset = queryset.filter(is_active=True)
        return queryset

    def get_permission_context(self, obj):
        return obj.facility_id, None

    def _create(self, request):
        serializer = self.create_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parent = serializer.validated_data[self.parent_field]
        facility_id = parent.pk if self.parent_field == "facility" else parent.facility_id
        check_permission(request.user, P.LOCATIONS_MANAGE, facility_id=facility_id)
        instance = location_services.create_location(
            self.model, actor=request.user, request=request, **serializer.validated_data
        )
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    def _update(self, request):
        instance = self.get_object()
        serializer = self.update_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        instance = location_services.update_location(
            self.model,
            actor=request.user,
            pk=instance.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(self.get_serializer(instance).data)


def _location_viewset(model, read, create, update, parent_field, filters, docs_params):
    """Build a concrete viewset with accurate OpenAPI documentation for each level."""

    class ViewSet(LocationViewSet):
        pass

    ViewSet.model = model
    ViewSet.serializer_class = read
    ViewSet.create_serializer = create
    ViewSet.update_serializer = update
    ViewSet.parent_field = parent_field
    ViewSet.filters = filters

    @extend_schema(
        parameters=[OpenApiParameter(p, str) for p in docs_params]
        + [OpenApiParameter("active", str, description="'true' = active only")]
    )
    def list(self, request, *args, **kwargs):
        return LocationViewSet.list(self, request, *args, **kwargs)

    @extend_schema(request=create, responses={201: read})
    @idempotent(f"locations.{model._meta.model_name}.create")
    def create_view(self, request):
        return self._create(request)

    @extend_schema(request=update, responses=read)
    def partial_update(self, request, pk=None):
        return self._update(request)

    ViewSet.list = list
    ViewSet.create = create_view
    ViewSet.partial_update = partial_update
    ViewSet.__name__ = ViewSet.__qualname__ = f"{model.__name__}ViewSet"
    return ViewSet


BuildingViewSet = _location_viewset(
    Building,
    s.BuildingSerializer,
    s.BuildingCreateSerializer,
    s.BuildingUpdateSerializer,
    "facility",
    {"facility": "facility_id"},
    ["facility"],
)
FloorViewSet = _location_viewset(
    Floor,
    s.FloorSerializer,
    s.FloorCreateSerializer,
    s.FloorUpdateSerializer,
    "building",
    {"facility": "facility_id", "building": "building_id"},
    ["facility", "building"],
)
WardViewSet = _location_viewset(
    Ward,
    s.WardSerializer,
    s.WardCreateSerializer,
    s.WardUpdateSerializer,
    "floor",
    {
        "facility": "facility_id",
        "floor": "floor_id",
        "ward_type": "ward_type",
        "department": "department_id",
    },
    ["facility", "floor", "ward_type", "department"],
)
RoomViewSet = _location_viewset(
    Room,
    s.RoomSerializer,
    s.RoomCreateSerializer,
    s.RoomUpdateSerializer,
    "ward",
    {"facility": "facility_id", "ward": "ward_id", "room_type": "room_type"},
    ["facility", "ward", "room_type"],
)
