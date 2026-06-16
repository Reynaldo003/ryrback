import jwt
from django.conf import settings
from django.core import signing
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from CrmConformidad.models import Usuario


class UsuarioJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None

        token = auth.replace("Bearer ", "").strip()

        # Intentar JWT primero
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            id_usuario = payload.get("id_usuario")
            if not id_usuario:
                raise AuthenticationFailed("Token inválido.")
            user = Usuario.objects.filter(id_usuario=id_usuario).select_related("rol").first()
            if not user:
                raise AuthenticationFailed("Usuario no existe.")
            return (user, token)
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token expirado.")
        except jwt.InvalidTokenError:
            pass  # No es JWT, intentar con signing

        # Fallback: token firmado (estructura original)
        signer = signing.TimestampSigner()
        try:
            unsigned = signer.unsign(token, max_age=60 * 60 * 24 * 7)
            id_usuario = int(unsigned)
        except signing.SignatureExpired:
            raise AuthenticationFailed("Token expirado.")
        except Exception:
            raise AuthenticationFailed("Token inválido.")

        user = Usuario.objects.filter(id_usuario=id_usuario).select_related("rol").first()
        if not user:
            raise AuthenticationFailed("Usuario no existe.")

        return (user, token)