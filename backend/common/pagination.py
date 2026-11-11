from django.core.paginator import Paginator
from django.utils.functional import cached_property
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class CappedPaginator(Paginator):
    """Counts up to ``cap`` matches only; ``capped`` says there were more."""

    cap = 10_000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.capped = False

    @cached_property
    def count(self) -> int:
        # Counting stops after cap + 1 matches; no ordering or extra columns are needed for that.
        found = self.object_list.order_by().values("pk")[: self.cap + 1].count()
        self.capped = found > self.cap
        return min(found, self.cap)


class CappedCountPagination(StandardPagination):
    """For the largest tables (the audit log): counting every match takes longer as the table
    grows, so counting stops at 10,000 and ``count_capped`` says there are more (HIMS-DATA-002
    measured 0.37 s for the count alone at 2 million events). The first 400 pages stay reachable;
    narrower filters find anything older."""

    django_paginator_class = CappedPaginator

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data["count_capped"] = self.page.paginator.capped
        return response

    def get_paginated_response_schema(self, schema):
        result = super().get_paginated_response_schema(schema)
        result["properties"]["count_capped"] = {
            "type": "boolean",
            "description": "True when there are more than `count` matches (counting stops at "
            "10,000).",
        }
        result["required"] = [*result.get("required", ["count", "results"]), "count_capped"]
        return result
