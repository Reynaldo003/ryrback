# citas/views.py
from rest_framework.viewsets import ModelViewSet
from .models import Citas
from .serializers import CitasSerializer

class CitasViewSet(ModelViewSet):
    queryset = Citas.objects.all().order_by("-id")
    serializer_class = CitasSerializer