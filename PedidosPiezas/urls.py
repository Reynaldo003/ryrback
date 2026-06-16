#PedidosPiezas/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PedidosPiezasViewSet, PiezasViewSet

router = DefaultRouter()
router.register(r"pedidos-piezas/pedidos", PedidosPiezasViewSet, basename="pedidos-piezas")
router.register(r"pedidos-piezas/piezas", PiezasViewSet, basename="piezas-catalogo")

urlpatterns = [
    path("", include(router.urls)),
]