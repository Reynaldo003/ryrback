# citas/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CitasViewSet

router = DefaultRouter()
router.register(r"citas", CitasViewSet, basename="citas")

urlpatterns = [
    path("api/", include(router.urls)),
]