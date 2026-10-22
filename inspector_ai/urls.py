#inspector_ai/urls.py
from django.urls import path
from .views import InspectorAnalizarView

urlpatterns = [
    path("api/analizar/",InspectorAnalizarView.as_view(), name="inspector-ai-analizar",),
]
