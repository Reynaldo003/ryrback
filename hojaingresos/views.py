# hojaingresos/views.py
from django.db.models import Q

from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import HojaIngresos
from .serializers import HojaIngresosSerializer


class HojaIngresosViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    serializer_class = HojaIngresosSerializer

    def get_queryset(self):
        qs = (
            HojaIngresos.objects
            .select_related("cliente")
            .all()
            .order_by("-fecha_ingreso", "-id")
        )

        q = (self.request.query_params.get("q") or "").strip()
        agencia = (self.request.query_params.get("agencia") or "").strip()
        asesor = (self.request.query_params.get("asesor") or "").strip()
        asistencia = (self.request.query_params.get("asistencia") or "").strip()
        desde = (self.request.query_params.get("desde") or "").strip()
        hasta = (self.request.query_params.get("hasta") or "").strip()

        if agencia and agencia not in ["Todos", "Todas"]:
            qs = qs.filter(agencia__iexact=agencia)

        if asesor and asesor not in ["Todos", "Todas"]:
            qs = qs.filter(asesor__icontains=asesor)

        if asistencia in ["true", "false"]:
            qs = qs.filter(asistencia=asistencia == "true")

        if desde:
            qs = qs.filter(fecha_ingreso__date__gte=desde)

        if hasta:
            qs = qs.filter(fecha_ingreso__date__lte=hasta)

        if q:
            qs = qs.filter(
                Q(agencia__icontains=q) |
                Q(no_orden__icontains=q) |
                Q(diss__icontains=q) |
                Q(pauta__icontains=q) |
                Q(indicador_resultados__icontains=q) |
                Q(alcance__icontains=q) |
                Q(torre__icontains=q) |
                Q(asesor__icontains=q) |
                Q(agendado_por__icontains=q) |
                Q(nombre_cliente__icontains=q) |
                Q(tipo_cita__icontains=q) |
                Q(declaracion_textual_cliente__icontains=q) |
                Q(comentarios__icontains=q) |
                Q(vin__icontains=q) |
                Q(anio_vehiculo__icontains=q) |
                Q(modelo__icontains=q) |
                Q(medio_concertacion__icontains=q) |
                Q(pauta_origen__icontains=q) |
                Q(cliente__nombre__icontains=q) |
                Q(cliente__telefono__icontains=q)
            )

        return qs