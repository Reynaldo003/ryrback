# trafico_piso/views.py
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import ExtractIsoWeekDay

from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from CrmConformidad.models import Usuario

from .models import TraficoPiso
from .serializers import TraficoPisoSerializer

from .pagination import TraficoPisoPagination


class TraficoPisoViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    pagination_class = TraficoPisoPagination

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

        # Aplicar filtros adicionales utilizados en el frontend
        tipo_persona = (request.query_params.get("tipo_persona") or "").strip()
        tiempo_compra = (request.query_params.get("tiempo_compra") or "").strip()

        if tipo_persona and tipo_persona != "Todos":
            qs = qs.filter(tipo_persona=tipo_persona)

        if tiempo_compra and tiempo_compra != "Todos":
            qs = qs.filter(tiempo_compra=tiempo_compra)

        # Métricas generales sobre todos los registros filtrados
        generales = qs.aggregate(
            total=Count("id_trafico"),
            con_auto_cuenta=Count(
                "id_trafico", filter=Q(deja_auto_cuenta=True)
            ),
            comprueban_ingresos=Count(
                "id_trafico", filter=Q(comprueba_ingresos=True)
            ),
            promedio_presupuesto=Avg("presupuesto_estimado"),
            promedio_enganche=Avg("enganche_presupuestado"),
            total_presupuesto=Sum("presupuesto_estimado"),
        )
        def agrupar(campo):
            return {
                str(item[campo] or "Sin especificar"): item["total"]
                for item in qs.order_by().values(campo).annotate(
                    total=Count("id_trafico")
                )
            }
        # Día de semana: 1 = lunes, 7 = domingo
        dias = {
            "Lun": 0, "Mar": 0, "Mié": 0, "Jue": 0,
            "Vie": 0, "Sáb": 0, "Dom": 0,
        }

        nombres_dias = [
            "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"
        ]
        for item in qs.order_by().annotate(
            dia_semana=ExtractIsoWeekDay("creado_en")
        ).values("dia_semana").annotate(
            total=Count("id_trafico")
        ):
            indice = item["dia_semana"]
            if indice is not None:
                dias[nombres_dias[indice - 1]] = item["total"]

        total = generales["total"] or 0
        con_auto = generales["con_auto_cuenta"] or 0

        return Response({
            "total": total,
            "interesados_auto_cuenta": con_auto,
            "con_auto_cuenta": con_auto,
            "sin_auto_cuenta": total - con_auto,
            "comprueban_ingresos": generales["comprueban_ingresos"] or 0,
            "promedio_presupuesto": generales["promedio_presupuesto"] or 0,
            "promedio_enganche": generales["promedio_enganche"] or 0,
            "total_presupuesto": generales["total_presupuesto"] or 0,

            # Datos completos para gráficos
            "por_agencia": agrupar("agencia"),
            "por_asesor": agrupar("asesor_ventas"),
            "por_motivo_ingreso": agrupar("motivo_ingreso"),
            "por_tipo_persona": agrupar("tipo_persona"),
            "por_tiempo_compra": agrupar("tiempo_compra"),
            "por_forma_capitalizacion": agrupar("forma_capitalizacion"),
            "por_dia": dias,
        })

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