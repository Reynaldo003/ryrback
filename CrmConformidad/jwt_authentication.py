# CrmConformidad/jwt_authentication.py
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Usuario


class CRMJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        id_usuario = validated_token.get("id_usuario")

        if not id_usuario:
            raise AuthenticationFailed("Token JWT sin id_usuario.")

        user = (
            Usuario.objects
            .select_related("rol")
            .filter(id_usuario=id_usuario)
            .first()
        )

        if not user:
            raise AuthenticationFailed("Usuario no existe.")

        return user