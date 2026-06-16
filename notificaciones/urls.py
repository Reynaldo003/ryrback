# notificaciones/urls.py
from django.urls import path
from .views import RegistrarTokenView

urlpatterns = [
    path('registrar-token/', RegistrarTokenView.as_view(), name='registrar-token'),
]