from django.urls import (
    include,
    path,
)

from rest_framework.routers import (
    DefaultRouter,
)

from .views import (
    FacturaMarketingViewSet,
    ConceptoFacturaViewSet,
)


router = DefaultRouter()

router.register(
    r"facturas",
    FacturaMarketingViewSet,
    basename="analisis-facturas",
)

router.register(
    r"conceptos",
    ConceptoFacturaViewSet,
    basename="analisis-facturas-conceptos",
)


urlpatterns = [
    path(
        "api/",
        include(
            router.urls
        ),
    ),
]