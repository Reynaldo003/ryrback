# citas/views.py
from rest_framework.viewsets import ModelViewSet
from .models import Citas, CitasPiso, PruebasManejo
from .serializers import CitasSerializer, CitasPisoSerializer, PruebasManejoSerializer


class CitasViewSet(ModelViewSet):
    queryset = Citas.objects.all().order_by("-id")
    serializer_class = CitasSerializer


class CitasPisoViewSet(ModelViewSet):
    queryset = CitasPiso.objects.all().order_by("-id")
    serializer_class = CitasPisoSerializer


class PruebasManejoViewSet(ModelViewSet):
    queryset = PruebasManejo.objects.all().order_by("-id")
    serializer_class = PruebasManejoSerializer