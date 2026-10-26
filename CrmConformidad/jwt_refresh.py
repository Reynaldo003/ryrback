#CrmConformidad/jwt_refresh.py
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .models import Usuario


class CRMTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = RefreshToken(attrs["refresh"])
        id_usuario = refresh.get("id_usuario")

        usuario_activo = Usuario.objects.filter(
            id_usuario=id_usuario,
            estado="Activo"
        ).exists()

        if not usuario_activo:
            raise AuthenticationFailed(
                "La cuenta está desactivada o ya no existe."
            )

        return super().validate(attrs)


class CRMTokenRefreshView(TokenRefreshView):
    serializer_class = CRMTokenRefreshSerializer
