from django.urls import path

from .views import EffectiveFeaturesView, FeatureChangeView, FeatureListView

urlpatterns = [
    path("features/", FeatureListView.as_view(), name="feature-list"),
    path("features/effective/", EffectiveFeaturesView.as_view(), name="feature-effective"),
    path("features/<str:key>/change/", FeatureChangeView.as_view(), name="feature-change"),
]
