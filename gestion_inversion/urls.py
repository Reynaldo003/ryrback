#gestion_inversion/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import FacturaMarketingViewSet,ConceptoFacturaViewSet

router = DefaultRouter()

router.register(r"facturas", FacturaMarketingViewSet, basename="gestion_inversion",)
router.register(r"conceptos", ConceptoFacturaViewSet, basename="gestion_inversion_conceptos",)

urlpatterns = [
    path("api/",include(router.urls),),
]