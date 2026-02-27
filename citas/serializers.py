# citas/serializers.py
from rest_framework import serializers
from .models import Citas, CitasPiso, PruebasManejo


class CitasSerializer(serializers.ModelSerializer):
    class Meta:
        model = Citas
        fields = "__all__"


class CitasPisoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CitasPiso
        fields = "__all__"


class PruebasManejoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PruebasManejo
        fields = "__all__"