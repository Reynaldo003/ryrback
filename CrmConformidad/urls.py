# crmConformidad/urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import CasoListCreateView, PerfilUsuarioView, CasoDetailView, CasoUploadDocsView, DocDeleteView, AuthLoginView, AuthRegisterView, AuthMeView, AdminRolesView, AdminPermisosCatalogView, AdminUsuariosCreateView, AdminUsuarioDetailView

urlpatterns = [
    path("api/casos/", CasoListCreateView.as_view(), name="casos-list-create"),
    path("api/casos/<int:pk>/", CasoDetailView.as_view(), name="casos-detail"),
    path("api/casos/<int:id_exp>/docs/", CasoUploadDocsView.as_view(), name="casos-upload-docs"),
    path("api/docs/<int:pk>/", DocDeleteView.as_view(), name="docs-delete"),
    path("api/perfil/", PerfilUsuarioView.as_view(), name="perfil-usuario"),

    # AUTH
    path("api/auth/login/", AuthLoginView.as_view(), name="auth-login"),
    path("api/auth/register/", AuthRegisterView.as_view(), name="auth-register"),
    path("api/auth/me/", AuthMeView.as_view(), name="auth-me"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # ADMIN
    path("api/admin/roles/", AdminRolesView.as_view(), name="admin-roles"),
    path("api/admin/permisos/", AdminPermisosCatalogView.as_view(), name="admin-permisos"),
    path("api/admin/usuarios/", AdminUsuariosCreateView.as_view(), name="admin-usuarios"),
    path("api/admin/usuarios/<int:pk>/", AdminUsuarioDetailView.as_view(), name="admin-usuario-detail"),
]