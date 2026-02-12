#/Digitales/urls.py
from django.urls import path
from . import views
urlpatterns = [
    path("bienvenido/", views.bienvenido),
    path("webhook/", views.webhook),
    path("enviar-template/", views.enviar_template_view),
]
