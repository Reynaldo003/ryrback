#hojaingresos/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import HojaIngresosViewSet

router = DefaultRouter()
router.register(r"hoja-ingresos", HojaIngresosViewSet, basename="hoja-ingresos")

urlpatterns = [
    path("api/", include(router.urls)),
]