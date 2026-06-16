from CrmConformidad.jwt_authentication import CRMJWTAuthentication


class UsuarioJWTAuthentication(CRMJWTAuthentication):
    """
    Se conserva el nombre para no romper imports existentes,
    pero internamente usa la autenticación JWT
    que ya funciona en CrmConformidad.
    """
    pass