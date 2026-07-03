from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.response import Response

from .models import VacanteReclutamiento, Puesto, EvaluacionPuesto
from .serializers import (
    VacanteReclutamientoSerializer,
    PuestoSerializer,
    EvaluacionPuestoSerializer,
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
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            context={"archivos": request.FILES},
        )
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=True,
            context={"archivos": request.FILES},
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

# ========== VISTAS PARA PUESTOS Y EVALUACIONES ==========
# Agregado para el módulo de Evaluación de Puestos
# No modifica nada existente


class PuestoViewSet(viewsets.ModelViewSet):
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
    serializer_class = EvaluacionPuestoSerializer
    lookup_field = "id_evaluacion"
    
    def get_queryset(self):
        queryset = EvaluacionPuesto.objects.all().order_by("-fecha")
        
        puesto_id = self.request.query_params.get("puesto_id")
        if puesto_id:
            queryset = queryset.filter(puesto_id=puesto_id)
        
        return queryset