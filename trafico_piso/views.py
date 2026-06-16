# trafico_piso/views.py
from django.db.models import Avg, Count, Q

from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from CrmConformidad.models import Usuario

from .models import TraficoPiso
from .serializers import TraficoPisoSerializer


class TraficoPisoViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]

    queryset = TraficoPiso.objects.all()
    serializer_class = TraficoPisoSerializer
    lookup_field = "id_trafico"

    acciones_publicas = {
        "create",
    }

    def get_authenticators(self):
        if getattr(self, "action", None) in self.acciones_publicas:
            return []

        return [CRMJWTAuthentication()]

    def get_permissions(self):
        if getattr(self, "action", None) in self.acciones_publicas:
            return [AllowAny()]

        return [IsAuthenticated()]

    def get_queryset(self):
        qs = TraficoPiso.objects.all().order_by("-id_trafico")

        search = (self.request.query_params.get("search") or "").strip()
        agencia = (self.request.query_params.get("agencia") or "").strip()
        desde = (self.request.query_params.get("desde") or "").strip()
        hasta = (self.request.query_params.get("hasta") or "").strip()

        if search:
            qs = qs.filter(
                Q(nombre_prospecto__icontains=search)
                | Q(telefono__icontains=search)
                | Q(email__icontains=search)
                | Q(asesor_ventas__icontains=search)
                | Q(agencia__icontains=search)
                | Q(motivo_ingreso__icontains=search)
                | Q(tipo_persona__icontains=search)
                | Q(tipo_venta__icontains=search)
                | Q(tiempo_compra__icontains=search)
                | Q(auto_suenos__icontains=search)
                | Q(forma_capitalizacion__icontains=search)
                | Q(motivo_compra__icontains=search)
                | Q(perfil_profesional__icontains=search)
                | Q(estado_civil__icontains=search)
                | Q(comentarios__icontains=search)
            )

        if agencia and agencia not in ["Todos", "Todas"]:
            qs = qs.filter(agencia__iexact=agencia)

        if desde:
            qs = qs.filter(creado_en__date__gte=desde)

        if hasta:
            qs = qs.filter(creado_en__date__lte=hasta)

        return qs

    def perform_create(self, serializer):
        user = None

        try:
            if self.request.user and self.request.user.is_authenticated:
                user = self.request.user
        except Exception:
            user = None

        extra = {}

        if user:
            try:
                field = TraficoPiso._meta.get_field("creado_por")
                remote_model = getattr(field.remote_field, "model", None)

                if remote_model and isinstance(user, remote_model):
                    extra["creado_por"] = user
            except Exception:
                pass

        serializer.save(**extra)

    @action(detail=False, methods=["get"], url_path="resumen")
    def resumen(self, request):
        qs = self.get_queryset()

        data = qs.aggregate(
            total=Count("id_trafico"),
            promedio_presupuesto=Avg("presupuesto_estimado"),
            promedio_enganche=Avg("enganche_presupuestado"),
        )

        interesados_auto_cuenta = qs.filter(deja_auto_cuenta=True).count()
        comprueban_ingresos = qs.filter(comprueba_ingresos=True).count()

        return Response(
            {
                "total": data["total"] or 0,
                "interesados_auto_cuenta": interesados_auto_cuenta,
                "comprueban_ingresos": comprueban_ingresos,
                "promedio_presupuesto": data["promedio_presupuesto"] or 0,
                "promedio_enganche": data["promedio_enganche"] or 0,
            }
        )

    @action(detail=False, methods=["get"], url_path="asesores-ventas")
    def asesores_ventas(self, request):
        q = (request.query_params.get("q") or "").strip()

        usuarios = Usuario.objects.select_related("rol").all()

        if q:
            usuarios = usuarios.filter(
                Q(nombre__icontains=q)
                | Q(apellidos__icontains=q)
                | Q(usuario__icontains=q)
                | Q(correo__icontains=q)
            )

        usuarios = usuarios.order_by("nombre", "apellidos", "usuario")[:30]

        data = []

        for usuario in usuarios:
            nombre = f"{usuario.nombre or ''} {usuario.apellidos or ''}".strip()

            if not nombre:
                nombre = usuario.usuario

            data.append(
                {
                    "id": usuario.id_usuario,
                    "id_usuario": usuario.id_usuario,
                    "nombre": nombre,
                    "email": usuario.correo or "",
                    "usuario": usuario.usuario,
                    "username": usuario.usuario,
                    "rol": usuario.rol.nombre if usuario.rol else "",
                    "agencia": usuario.agencia or "",
                }
            )

        return Response(data)