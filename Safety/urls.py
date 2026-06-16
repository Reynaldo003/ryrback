#Safety/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import PublicReporteSafetyCreateView, ReporteSafetyViewSet

router = DefaultRouter()
router.register(
    r"reportes",
    ReporteSafetyViewSet,
    basename="safety-reportes",
)

urlpatterns = [
    path(
        "public/safety/reportes/",
        PublicReporteSafetyCreateView.as_view(),
        name="public-safety-reportes-create",
    ),
    path("safety/", include(router.urls)),
]