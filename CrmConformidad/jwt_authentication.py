# CrmConformidad/jwt_authentication.py
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Usuario


class CRMJWTAuthentication(JWTAuthentication):
    """
    Autenticación JWT para el modelo propio del CRM: CrmConformidad.Usuario.

    SimpleJWT por defecto intenta buscar usuarios en django.contrib.auth.User.
    Como tu CRM usa la tabla propia usuarios, resolvemos request.user usando
    el claim id_usuario del token.
    """

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