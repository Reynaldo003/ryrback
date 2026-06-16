# jdpower/serializers.py
from rest_framework import serializers

from .models import EncuestaJDPower, EncuestaJDPowerServicio

class EncuestaJDPowerSerializer(serializers.ModelSerializer):
    class Meta:
        model = EncuestaJDPower
        fields = "__all__"
        read_only_fields = fields

#  SERVICIO 
class EncuestaJDPowerServicioSerializer(serializers.ModelSerializer):
    class Meta:
        model = EncuestaJDPowerServicio
        fields = "__all__"
        read_only_fields = fields