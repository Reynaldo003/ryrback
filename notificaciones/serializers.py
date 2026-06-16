# notificaciones/serializers.py
from rest_framework import serializers
from CrmConformidad.models import FirebaseToken

class FirebaseTokenSerializer(serializers.ModelSerializer):
    token = serializers.CharField(validators=[])

    class Meta:
        model = FirebaseToken
        fields = ['token']

    def create(self, validated_data):
        token = validated_data['token']
        usuario = self.context['request'].user

        firebase_token, _ = FirebaseToken.objects.update_or_create(
            token=token,
            defaults={'usuario': usuario}
        )
        return firebase_token