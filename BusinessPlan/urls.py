from django.urls import path
from .views import (
    TableroListaCrearView, TableroDetalleView, RestaurarTableroView,
    TemaListaCrearView, TemaDetalleView, DatosTemaAnualView,
    UsuariosInvitablesView, InvitacionTableroView, InvitacionTemaView,
    InvitacionesPendientesView, ResponderInvitacionView,
    ColaboradoresTableroView, ColaboradoresTemaView,
    RevocarColaboradorTableroView, RevocarColaboradorTemaView,
)

urlpatterns = [
    path("api/tableros/", TableroListaCrearView.as_view()),
    path("api/tableros/<int:pk>/", TableroDetalleView.as_view()),
    path("api/tableros/<int:pk>/restaurar/", RestaurarTableroView.as_view()),
    path("api/tableros/<int:pk>/colaboradores/", ColaboradoresTableroView.as_view()),
    path("api/tableros/<int:pk>/colaboradores/<int:usuario_id>/", RevocarColaboradorTableroView.as_view()),
    path("api/tableros/<int:pk>/invitar/", InvitacionTableroView.as_view()),
    path("api/temas/", TemaListaCrearView.as_view()),
    path("api/temas/<int:pk>/", TemaDetalleView.as_view()),
    path("api/temas/<int:pk>/periodos/<int:anio>/", DatosTemaAnualView.as_view()),
    path("api/temas/<int:pk>/colaboradores/", ColaboradoresTemaView.as_view()),
    path("api/temas/<int:pk>/colaboradores/<int:usuario_id>/", RevocarColaboradorTemaView.as_view()),
    path("api/temas/<int:pk>/invitar/", InvitacionTemaView.as_view()),
    path("api/usuarios/", UsuariosInvitablesView.as_view()),
    path("api/invitaciones/", InvitacionesPendientesView.as_view()),
    path("api/invitaciones/<str:tipo>/<int:pk>/", ResponderInvitacionView.as_view()),
]
