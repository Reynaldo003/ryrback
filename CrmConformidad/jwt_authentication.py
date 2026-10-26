# CrmConformidad/jwt_authentication.py

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

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

        if user.estado != "Activo":
            raise AuthenticationFailed("Tu cuenta está desactivada. Contacta al administrador.")

        return user


class CRMTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = RefreshToken(attrs["refresh"])
        id_usuario = refresh.get("id_usuario")

        if not Usuario.objects.filter(id_usuario=id_usuario, estado="Activo").exists():
            raise AuthenticationFailed("La cuenta está desactivada o ya no existe.")

        return super().validate(attrs)


class CRMTokenRefreshView(TokenRefreshView):
    serializer_class = CRMTokenRefreshSerializer
