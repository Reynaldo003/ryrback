from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from CrmConformidad.models import Usuario

from .models import Tablero, Tema, ColaboradorTablero, ColaboradorTema, DatosTemaAnual
from .permisos import (
    puede_ver_tablero, puede_editar_tablero, puede_ver_tema, puede_editar_tema,
    tableros_visibles, temas_visibles,
)
from .serializers import (
    TableroSerializer, TemaSerializer, InvitarSerializer,
    AccesoTableroSerializer, AccesoTemaSerializer, DatosTemaAnualSerializer,
)


class VistaAutenticada(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]


def tablero_visible_o_404(usuario, pk):
    tablero = get_object_or_404(Tablero.objects.select_related("propietario"), pk=pk)
    if not puede_ver_tablero(usuario, tablero):
        raise NotFound("Tablero no encontrado.")
    return tablero


def tema_visible_o_404(usuario, pk):
    tema = get_object_or_404(Tema.objects.select_related("tablero", "propietario"), pk=pk)
    if not puede_ver_tema(usuario, tema):
        raise NotFound("Tema no encontrado.")
    return tema


def exigir_propietario_tablero(usuario, tablero):
    if tablero.propietario_id != usuario.pk:
        raise PermissionDenied("Solo el propietario puede administrar este tablero.")


def exigir_administrador_tema(usuario, tema):
    if usuario.pk not in (tema.propietario_id, tema.tablero.propietario_id):
        raise PermissionDenied("Solo el propietario del tema o del tablero puede invitar.")


def serializar_tablero(tablero, request):
    return TableroSerializer(tablero, context={"request": request}).data


def serializar_tema(tema, request):
    return TemaSerializer(tema, context={"request": request}).data


class TableroListaCrearView(VistaAutenticada):
    def get(self, request):
        if request.query_params.get("papelera") == "1":
            tableros = Tablero.objects.filter(
                propietario=request.user, eliminado_en__isnull=False
            ).select_related("propietario").order_by("-eliminado_en")
        else:
            tableros = tableros_visibles(request.user).select_related("propietario")

        return Response([serializar_tablero(t, request) for t in tableros])

    @transaction.atomic
    def post(self, request):
        serializer = TableroSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        tablero = serializer.save(propietario=request.user)
        # Solo se crea el tema General al crear un tablero. NO se crean tableros predeterminados.
        Tema.objects.create(
            tablero=tablero, propietario=request.user,
            nombre="General", subtitulo="Indicadores y objetivos generales",
        )
        return Response(serializar_tablero(tablero, request), status=status.HTTP_201_CREATED)


class TableroDetalleView(VistaAutenticada):
    def get(self, request, pk):
        tablero = tablero_visible_o_404(request.user, pk)
        return Response(serializar_tablero(tablero, request))

    def patch(self, request, pk):
        tablero = tablero_visible_o_404(request.user, pk)
        exigir_propietario_tablero(request.user, tablero)
        serializer = TableroSerializer(
            tablero, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializar_tablero(tablero, request))

    def delete(self, request, pk):
        tablero = tablero_visible_o_404(request.user, pk)
        exigir_propietario_tablero(request.user, tablero)
        tablero.eliminado_en = timezone.now()
        tablero.save(update_fields=["eliminado_en", "actualizado_en"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class RestaurarTableroView(VistaAutenticada):
    def post(self, request, pk):
        tablero = get_object_or_404(Tablero, pk=pk, propietario=request.user)
        if tablero.eliminado_en is None:
            return Response({"detail": "El tablero ya está activo."})

        # Al restaurar se comprueba que no exista otro tablero activo con ese nombre.
        if Tablero.objects.filter(
            propietario=request.user, nombre__iexact=tablero.nombre, eliminado_en__isnull=True
        ).exclude(pk=tablero.pk).exists():
            return Response(
                {"detail": "Ya tienes otro tablero activo con el mismo nombre."},
                status=status.HTTP_409_CONFLICT,
            )

        tablero.eliminado_en = None
        tablero.save(update_fields=["eliminado_en", "actualizado_en"])
        return Response(serializar_tablero(tablero, request))


class TemaListaCrearView(VistaAutenticada):
    def get(self, request):
        tablero_id = request.query_params.get("tablero")
        if not tablero_id or not str(tablero_id).isdigit():
            raise ValidationError({"tablero": "Debes enviar ?tablero=ID numérico."})
        tablero = tablero_visible_o_404(request.user, int(tablero_id))
        return Response([serializar_tema(t, request) for t in temas_visibles(request.user, tablero)])

    def post(self, request):
        serializer = TemaSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        tablero = serializer.validated_data["tablero"]
        if not puede_editar_tablero(request.user, tablero):
            raise PermissionDenied("No tienes permiso para crear temas en este tablero.")
        tema = serializer.save(propietario=request.user)
        return Response(serializar_tema(tema, request), status=status.HTTP_201_CREATED)


class TemaDetalleView(VistaAutenticada):
    def get(self, request, pk):
        tema = tema_visible_o_404(request.user, pk)
        return Response(serializar_tema(tema, request))

    def patch(self, request, pk):
        tema = tema_visible_o_404(request.user, pk)
        if not puede_editar_tema(request.user, tema):
            raise PermissionDenied("No tienes permiso de edición.")
        if "tablero" in request.data or "propietario" in request.data:
            raise ValidationError("No puedes cambiar el propietario ni mover el tema.")
        serializer = TemaSerializer(
            tema, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializar_tema(tema, request))

    def delete(self, request, pk):
        tema = tema_visible_o_404(request.user, pk)
        exigir_administrador_tema(request.user, tema)
        tema.delete()  # También elimina sus periodos e invitaciones.
        return Response(status=status.HTTP_204_NO_CONTENT)


class DatosTemaAnualView(VistaAutenticada):
    @staticmethod
    def respuesta(tema, anio, datos):
        return {
            "tema": tema.id,
            "anio": anio,
            "revision": datos.revision if datos else 0,
            "filas": datos.filas if datos else [],
            "columnas": datos.columnas if datos else [],
        }

    @staticmethod
    def validar_anio(anio):
        if not 2000 <= anio <= 2100:
            raise ValidationError({"anio": "El año debe estar entre 2000 y 2100."})

    def get(self, request, pk, anio):
        self.validar_anio(anio)
        tema = tema_visible_o_404(request.user, pk)
        datos = DatosTemaAnual.objects.filter(tema=tema, anio=anio).first()
        return Response(self.respuesta(tema, anio, datos))

    @transaction.atomic
    def put(self, request, pk, anio):
        self.validar_anio(anio)
        serializer = DatosTemaAnualSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Se bloquea el tema para evitar dos INSERT simultáneos al primer guardado del año.
        tema = get_object_or_404(
            Tema.objects.select_related("tablero").select_for_update(), pk=pk
        )
        if not puede_editar_tema(request.user, tema):
            raise PermissionDenied("No tienes permiso para modificar este tema.")

        datos, _ = DatosTemaAnual.objects.get_or_create(tema=tema, anio=anio)
        datos = DatosTemaAnual.objects.select_for_update().get(pk=datos.pk)

        if serializer.validated_data["revision"] != datos.revision:
            return Response(
                {"detail": "Otro usuario modificó este periodo. Recarga antes de guardar.",
                 "revision_actual": datos.revision},
                status=status.HTTP_409_CONFLICT,
            )

        datos.filas = serializer.validated_data["filas"]
        datos.columnas = serializer.validated_data["columnas"]
        datos.revision += 1
        datos.actualizado_por = request.user
        datos.save()
        return Response(self.respuesta(tema, anio, datos))


class UsuariosInvitablesView(VistaAutenticada):
    def get(self, request):
        buscar = request.query_params.get("buscar", "").strip()
        if len(buscar) < 2:
            return Response([])
        usuarios = Usuario.objects.filter(
            Q(usuario__icontains=buscar) | Q(nombre__icontains=buscar)
            | Q(apellidos__icontains=buscar) | Q(correo__icontains=buscar)
        ).exclude(pk=request.user.pk).order_by("usuario")[:20]
        return Response([
            {"id_usuario": u.id_usuario, "usuario": u.usuario,
             "nombre": f"{u.nombre} {u.apellidos or ''}".strip()}
            for u in usuarios
        ])


def validar_invitacion(request):
    serializer = InvitarSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    destinatario = get_object_or_404(Usuario, pk=serializer.validated_data["id_usuario"])
    return destinatario, serializer.validated_data["rol"]


class InvitacionTableroView(VistaAutenticada):
    def post(self, request, pk):
        tablero = tablero_visible_o_404(request.user, pk)
        exigir_propietario_tablero(request.user, tablero)
        destinatario, rol = validar_invitacion(request)
        if destinatario.pk == tablero.propietario_id:
            raise ValidationError({"id_usuario": "El propietario ya tiene acceso completo."})

        colaboracion, _ = ColaboradorTablero.objects.update_or_create(
            tablero=tablero, usuario=destinatario,
            defaults={"rol": rol, "estado": "pendiente", "invitado_por": request.user},
        )
        return Response(AccesoTableroSerializer(colaboracion).data, status=status.HTTP_201_CREATED)


class InvitacionTemaView(VistaAutenticada):
    def post(self, request, pk):
        tema = tema_visible_o_404(request.user, pk)
        exigir_administrador_tema(request.user, tema)
        destinatario, rol = validar_invitacion(request)
        if destinatario.pk in (tema.propietario_id, tema.tablero.propietario_id):
            raise ValidationError({"id_usuario": "Ese usuario ya tiene acceso como propietario."})

        colaboracion, _ = ColaboradorTema.objects.update_or_create(
            tema=tema, usuario=destinatario,
            defaults={"rol": rol, "estado": "pendiente", "invitado_por": request.user},
        )
        return Response(AccesoTemaSerializer(colaboracion).data, status=status.HTTP_201_CREATED)


class InvitacionesPendientesView(VistaAutenticada):
    def get(self, request):
        tableros = ColaboradorTablero.objects.filter(
            usuario=request.user, estado="pendiente", tablero__eliminado_en__isnull=True
        ).select_related("tablero", "invitado_por")
        temas = ColaboradorTema.objects.filter(
            usuario=request.user, estado="pendiente", tema__tablero__eliminado_en__isnull=True
        ).select_related("tema", "tema__tablero", "invitado_por")
        datos = [
            {"id": x.id, "tipo": "tablero", "nombre": x.tablero.nombre,
             "rol": x.rol, "invitado_por": x.invitado_por.usuario}
            for x in tableros
        ]
        datos += [
            {"id": x.id, "tipo": "tema", "nombre": x.tema.nombre,
             "tablero": x.tema.tablero.nombre, "rol": x.rol,
             "invitado_por": x.invitado_por.usuario}
            for x in temas
        ]
        return Response(datos)


class ResponderInvitacionView(VistaAutenticada):
    def post(self, request, tipo, pk):
        modelos = {"tablero": ColaboradorTablero, "tema": ColaboradorTema}
        modelo = modelos.get(tipo)
        if modelo is None:
            raise NotFound("Tipo de invitación desconocido.")
        accion = request.data.get("accion")
        if accion not in ("aceptar", "rechazar"):
            raise ValidationError({"accion": "Usa aceptar o rechazar."})
        acceso = get_object_or_404(modelo, pk=pk, usuario=request.user, estado="pendiente")
        if accion == "rechazar":
            acceso.delete()
        else:
            recurso = acceso.tablero if tipo == "tablero" else acceso.tema.tablero
            if recurso.eliminado_en:
                raise NotFound("El tablero ya no está disponible.")
            acceso.estado = "aceptada"
            acceso.save(update_fields=["estado"])
        return Response({"detail": "Invitación procesada."})


class ColaboradoresTableroView(VistaAutenticada):
    def get(self, request, pk):
        tablero = tablero_visible_o_404(request.user, pk)
        exigir_propietario_tablero(request.user, tablero)
        accesos = tablero.colaboraciones.select_related("usuario").order_by("id")
        return Response(AccesoTableroSerializer(accesos, many=True).data)


class ColaboradoresTemaView(VistaAutenticada):
    def get(self, request, pk):
        tema = tema_visible_o_404(request.user, pk)
        exigir_administrador_tema(request.user, tema)
        accesos = tema.colaboraciones.select_related("usuario").order_by("id")
        return Response(AccesoTemaSerializer(accesos, many=True).data)


class RevocarColaboradorTableroView(VistaAutenticada):
    def delete(self, request, pk, usuario_id):
        tablero = tablero_visible_o_404(request.user, pk)
        exigir_propietario_tablero(request.user, tablero)
        get_object_or_404(ColaboradorTablero, tablero=tablero, usuario_id=usuario_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RevocarColaboradorTemaView(VistaAutenticada):
    def delete(self, request, pk, usuario_id):
        tema = tema_visible_o_404(request.user, pk)
        exigir_administrador_tema(request.user, tema)
        get_object_or_404(ColaboradorTema, tema=tema, usuario_id=usuario_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
