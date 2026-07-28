import json

from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.response import Response  
from rest_framework.decorators import action   

from .models import (
    VacanteReclutamiento,
    Puesto,
    EvaluacionPuesto,
    Colaborador,
    CategoriaAmbienteLaboral,  
    DominioAmbienteLaboral,    
    EvaluacionAmbienteLaboral,
)

from .serializers import (
    VacanteReclutamientoSerializer,
    PuestoSerializer,
    EvaluacionPuestoSerializer,
    ColaboradorSerializer,
    CategoriaAmbienteLaboralSerializer, 
    EvaluacionAmbienteLaboralSerializer, 
)


class VacanteReclutamientoViewSet(viewsets.ModelViewSet):
    serializer_class = VacanteReclutamientoSerializer
    lookup_field = "id_vacante"

    def get_queryset(self):
        queryset = (
            VacanteReclutamiento.objects
            .prefetch_related("candidatos")
            .all()
            .order_by("-id_vacante")
        )

        estatus = self.request.query_params.get("estatus")
        puesto = self.request.query_params.get("puesto")
        dealer = self.request.query_params.get("dealer")
        fuente = self.request.query_params.get("fuente")
        buscar = self.request.query_params.get("buscar")

        if estatus:
            queryset = queryset.filter(estatus=estatus)

        if puesto:
            queryset = queryset.filter(puesto=puesto)

        if dealer:
            queryset = queryset.filter(dealer__icontains=dealer)

        if fuente:
            queryset = queryset.filter(
                Q(fuente_reclutamiento=fuente)
                | Q(candidatos__fuente=fuente)
            )

        if buscar:
            filtros = (
                Q(puesto__icontains=buscar)
                | Q(dealer__icontains=buscar)
                | Q(fuente_reclutamiento__icontains=buscar)
                | Q(solicitado_por__icontains=buscar)
                | Q(candidatos__nombre__icontains=buscar)
                | Q(candidatos__telefono__icontains=buscar)
                | Q(candidatos__correo__icontains=buscar)
                | Q(candidatos__ubicacion__icontains=buscar)
                | Q(candidatos__puesto_postulado__icontains=buscar)
                | Q(candidatos__fuente__icontains=buscar)
                | Q(candidatos__estatus__icontains=buscar)
            )

            if buscar.isdigit():
                filtros = filtros | Q(id_vacante=int(buscar))

            queryset = queryset.filter(filtros)

        return queryset.distinct()
    
    def _construir_payload(self, request):
        data = {
            "estatus": request.data.get("estatus"),
            "puesto": request.data.get("puesto"),
            "dealer": request.data.get("dealer"),
            "fuente_reclutamiento": request.data.get("fuente_reclutamiento"),
            "solicitado_por": request.data.get("solicitado_por"),
        }

        candidatos_raw = request.data.get("candidatos")
        try:
            data["candidatos"] = json.loads(candidatos_raw) if candidatos_raw else []
        except (TypeError, ValueError):
            data["candidatos"] = []

        return data
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=self._construir_payload(request),
            context={"archivos": request.FILES},
        )
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()

        try:
            serializer = self.get_serializer(
                instance,
                data=self._construir_payload(request),
                partial=True,
                context={"archivos": request.FILES},
            )
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)

            return Response(serializer.data)

        except Exception:
            import traceback
            traceback.print_exc()
            raise

# ========== VISTAS PARA PUESTOS Y EVALUACIONES ==========
# Agregado para el módulo de Evaluación de Puestos
# No modifica nada existente


class PuestoViewSet(viewsets.ModelViewSet):
    queryset = Puesto.objects.all()
    serializer_class = PuestoSerializer
    lookup_field = "id_puesto"

    def get_queryset(self):
        queryset = Puesto.objects.filter(activo=True).order_by("nombre")

        categoria = self.request.query_params.get("categoria")
        if categoria:
            queryset = queryset.filter(categoria=categoria)

        buscar = self.request.query_params.get("buscar")
        if buscar:
            queryset = queryset.filter(nombre__icontains=buscar)

        return queryset


class EvaluacionPuestoViewSet(viewsets.ModelViewSet):
    queryset = EvaluacionPuesto.objects.all()
    serializer_class = EvaluacionPuestoSerializer
    lookup_field = "id_evaluacion"
    
    def get_queryset(self):
        queryset = EvaluacionPuesto.objects.all().order_by("-fecha")
        
        puesto_id = self.request.query_params.get("puesto_id")
        if puesto_id:
            queryset = queryset.filter(puesto_id=puesto_id)
        
        return queryset
    
class ColaboradorViewSet(viewsets.ModelViewSet):
    queryset = Colaborador.objects.all()
    serializer_class = ColaboradorSerializer
    lookup_field = "id_colaborador"

    def get_queryset(self):
        queryset = Colaborador.objects.all().order_by("nombre")

        agencia = self.request.query_params.get("agencia")
        buscar = self.request.query_params.get("buscar")

        if agencia:
            queryset = queryset.filter(agencia=agencia)

        if buscar:
            queryset = queryset.filter(
                Q(nombre__icontains=buscar)
                | Q(puesto__icontains=buscar)
                | Q(curp__icontains=buscar)
                | Q(nss__icontains=buscar)
            )

        return queryset

    @action(detail=True, methods=["post"])
    def dar_baja(self, request, id_colaborador=None):
        colaborador = self.get_object()

        fecha_baja = request.data.get("fecha_baja")
        motivo_baja = request.data.get("motivo_baja")

        if not fecha_baja or not motivo_baja:
            return Response(
                {"error": "Fecha y motivo de baja son requeridos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        colaborador.activo = False
        colaborador.fecha_baja = fecha_baja
        colaborador.motivo_baja = motivo_baja
        colaborador.save()

        return Response(ColaboradorSerializer(colaborador).data)

    @action(detail=True, methods=["post"])
    def reactivar(self, request, id_colaborador=None):
        """Por si tu jefe también quiere poder 'deshacer' una baja."""
        colaborador = self.get_object()

        colaborador.activo = True
        colaborador.fecha_baja = None
        colaborador.motivo_baja = None
        colaborador.save()

        return Response(ColaboradorSerializer(colaborador).data)

# ========== VISTAS PARA AMBIENTE LABORAL (NOM-035) ==========

class CategoriaAmbienteLaboralViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Catálogo fijo de categorías + dominios.
    Solo lectura: se administra por fixture/migración, no desde el frontend.
    """
    queryset = CategoriaAmbienteLaboral.objects.prefetch_related("dominios").all()
    serializer_class = CategoriaAmbienteLaboralSerializer
    lookup_field = "id_categoria"


class EvaluacionAmbienteLaboralViewSet(viewsets.ModelViewSet):
    queryset = EvaluacionAmbienteLaboral.objects.select_related(
        "dominio", "dominio__categoria"
    ).all()
    serializer_class = EvaluacionAmbienteLaboralSerializer
    lookup_field = "id_evaluacion"

    def get_queryset(self):
        queryset = super().get_queryset()

        dealer = self.request.query_params.get("dealer")
        anio = self.request.query_params.get("anio")

        if dealer:
            queryset = queryset.filter(dealer=dealer)
        if anio:
            queryset = queryset.filter(anio=anio)

        return queryset

    @action(detail=False, methods=["get"])
    def resumen(self, request):
        """
        Devuelve TODAS las categorías/dominios del catálogo, con la
        evaluación correspondiente a ese dealer/año si ya existe
        (o null si aún no se ha capturado).
        GET /ambiente-laboral/evaluaciones/resumen/?dealer=VW%20Cordoba&anio=2026
        """
        dealer = request.query_params.get("dealer")
        anio = request.query_params.get("anio")

        if not dealer or not anio:
            return Response(
                {"error": "dealer y anio son requeridos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        evaluaciones = {
            ev.dominio_id: ev
            for ev in EvaluacionAmbienteLaboral.objects.filter(
                dealer=dealer, anio=anio
            )
        }

        data = []
        categorias = CategoriaAmbienteLaboral.objects.prefetch_related("dominios")

        for cat in categorias:
            dominios_data = []
            for dom in cat.dominios.all():
                ev = evaluaciones.get(dom.id_dominio)
                dominios_data.append({
                    "id_dominio": dom.id_dominio,
                    "nombre": dom.nombre,
                    "id_evaluacion": ev.id_evaluacion if ev else None,
                    "puntuacion": ev.puntuacion if ev else None,
                    "plan_accion": ev.plan_accion if ev else "",
                    "seguimiento": ev.seguimiento if ev else "",
                    "evidencia": ev.evidencia.url if (ev and ev.evidencia) else None,
                })

            data.append({
                "id_categoria": cat.id_categoria,
                "nombre": cat.nombre,
                "dominios": dominios_data,
            })

        return Response(data)

    @action(detail=False, methods=["post"])
    def upsert(self, request):
        """
        Crea o actualiza la evaluación de un dominio para un dealer/año.
        POST /ambiente-laboral/evaluaciones/upsert/
        Body: { dominio, dealer, anio, puntuacion, plan_accion, seguimiento }
        """
        dominio_id = request.data.get("dominio")
        dealer = request.data.get("dealer")
        anio = request.data.get("anio")

        if not dominio_id or not dealer or not anio:
            return Response(
                {"error": "dominio, dealer y anio son requeridos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instancia, _ = EvaluacionAmbienteLaboral.objects.get_or_create(
            dominio_id=dominio_id,
            dealer=dealer,
            anio=anio,
        )

        serializer = self.get_serializer(
            instancia,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)