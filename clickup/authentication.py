from CrmConformidad.authentication import SignedUserAuthentication


class UsuarioJWTAuthentication(SignedUserAuthentication):
    """
    Se conserva el nombre para no romper imports existentes,
    pero internamente usa la misma autenticación firmada
    que ya funciona en CrmConformidad.
    """
    pass