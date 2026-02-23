# citas/serializers.py
from rest_framework import serializers
from .models import Citas

class CitasSerializer(serializers.ModelSerializer):
    class Meta:
        model = Citas
        fields = "__all__"
