# rrhh/views.py
import json

from django.db.models import Q

from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import VacanteReclutamiento, Puesto, EvaluacionPuesto
from .serializers import (
    VacanteReclutamientoSerializer,
    PuestoSerializer,
    EvaluacionPuestoSerializer,
)


class VacanteReclutamientoViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    serializer_class = VacanteReclutamientoSerializer
    lookup_field = "id_vacante"
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        queryset = (
            VacanteReclutamiento.objects
            .prefetch_related("candidatos")
            .all()
            .order_by("-id_vacante")
        )

        estatus = (self.request.query_params.get("estatus") or "").strip()
        puesto = (self.request.query_params.get("puesto") or "").strip()
        dealer = (self.request.query_params.get("dealer") or "").strip()
        fuente = (self.request.query_params.get("fuente") or "").strip()
        buscar = (self.request.query_params.get("buscar") or "").strip()

        if estatus:
            queryset = queryset.filter(estatus=estatus)

        if puesto:
            queryset = queryset.filter(puesto__icontains=puesto)

        if dealer:
            queryset = queryset.filter(dealer__icontains=dealer)

        if fuente:
            queryset = queryset.filter(
                Q(fuente_reclutamiento__icontains=fuente)
                | Q(candidatos__fuente__icontains=fuente)
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

    def get_serializer_context(self):
        context = super().get_serializer_context()

        archivos = {}

        try:
            for key in self.request.FILES.keys():
                archivo = self.request.FILES.get(key)
                if archivo:
                    archivos[key] = archivo
        except Exception:
            archivos = {}

        context["archivos"] = archivos

        return context

    def _normalizar_data(self, request):
        """
        Soporta JSON normal y multipart/form-data.

        Para multipart, el frontend debe mandar:
        - candidatos: JSON.stringify([...])
        - cv_archivo_0: archivo del candidato 0
        - cv_archivo_1: archivo del candidato 1
        """

        if isinstance(request.data, dict):
            data = dict(request.data.items()) if hasattr(request.data, "items") else dict(request.data)
        else:
            data = {}

        candidatos = data.get("candidatos", None)

        if candidatos in ["", None, "null", "undefined"]:
            data.pop("candidatos", None)
            return data

        if isinstance(candidatos, str):
            try:
                data["candidatos"] = json.loads(candidatos)
            except json.JSONDecodeError:
                raise ValidationError({
                    "candidatos": "El campo candidatos debe ser un JSON válido."
                })

        return data

    def create(self, request, *args, **kwargs):
        data = self._normalizar_data(request)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        vacante = serializer.save()

        salida = self.get_serializer(vacante)

        return Response(
            {
                "message": "Vacante registrada correctamente.",
                "data": salida.data,
            },
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        data = self._normalizar_data(request)

        serializer = self.get_serializer(
            instance,
            data=data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)

        vacante = serializer.save()

        salida = self.get_serializer(vacante)

        return Response(
            {
                "message": "Vacante actualizada correctamente.",
                "data": salida.data,
            },
            status=status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)


class PuestoViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    serializer_class = PuestoSerializer
    lookup_field = "id_puesto"
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        queryset = Puesto.objects.all().order_by("nombre")

        categoria = (self.request.query_params.get("categoria") or "").strip()
        buscar = (self.request.query_params.get("buscar") or "").strip()
        activo = self.request.query_params.get("activo")

        if self.action == "list":
            if activo is None:
                queryset = queryset.filter(activo=True)
            else:
                activo_normalizado = str(activo).strip().lower()

                if activo_normalizado in ["1", "true", "si", "sí"]:
                    queryset = queryset.filter(activo=True)

                if activo_normalizado in ["0", "false", "no"]:
                    queryset = queryset.filter(activo=False)

        if categoria:
            queryset = queryset.filter(categoria__icontains=categoria)

        if buscar:
            queryset = queryset.filter(nombre__icontains=buscar)

        return queryset


class EvaluacionPuestoViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    serializer_class = EvaluacionPuestoSerializer
    lookup_field = "id_evaluacion"
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        queryset = (
            EvaluacionPuesto.objects
            .select_related("puesto")
            .all()
            .order_by("-fecha", "-id_evaluacion")
        )

        puesto_id = (self.request.query_params.get("puesto_id") or "").strip()
        concesionario = (self.request.query_params.get("concesionario") or "").strip()
        buscar = (self.request.query_params.get("buscar") or "").strip()

        if puesto_id:
            queryset = queryset.filter(puesto_id=puesto_id)

        if concesionario:
            queryset = queryset.filter(concesionario__icontains=concesionario)

        if buscar:
            queryset = queryset.filter(
                Q(colaborador_nombre__icontains=buscar)
                | Q(evaluador_nombre__icontains=buscar)
                | Q(evaluador_puesto__icontains=buscar)
                | Q(puesto__nombre__icontains=buscar)
                | Q(concesionario__icontains=buscar)
                | Q(periodo__icontains=buscar)
            )

        return queryset