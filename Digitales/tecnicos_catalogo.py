from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.permissions import IsAdminRole

from .models import Tecnico


class TecnicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tecnico
        fields = [
            "id",
            "nombre",
            "tipo_personal",
            "agencia",
            "activo",
            "creado",
            "actualizado",
        ]
        read_only_fields = [
            "id",
            "creado",
            "actualizado",
        ]

    def validate_nombre(self, value):
        nombre = str(value or "").strip()

        if not nombre:
            raise serializers.ValidationError(
                "El nombre es obligatorio."
            )

        return nombre

    def validate_tipo_personal(self, value):
        return str(value or "").strip()

    def validate_agencia(self, value):
        return str(value or "").strip()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tecnicos_list(request):
    queryset = Tecnico.objects.all()

    activo = str(
        request.query_params.get("activo", "true")
    ).strip().lower()

    if activo in {"true", "1", "si", "sí"}:
        queryset = queryset.filter(activo=True)

    elif activo in {"false", "0", "no"}:
        queryset = queryset.filter(activo=False)

    tipo_personal = str(
        request.query_params.get("tipo_personal", "")
    ).strip()

    if tipo_personal:
        queryset = queryset.filter(
            tipo_personal__iexact=tipo_personal
        )

    agencia = str(
        request.query_params.get("agencia", "")
    ).strip()

    if agencia:
        queryset = queryset.filter(
            agencia__iexact=agencia
        )

    serializer = TecnicoSerializer(
        queryset,
        many=True,
    )

    return Response(serializer.data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def tecnicos_admin_list_create(request):
    if request.method == "GET":
        queryset = Tecnico.objects.all()

        serializer = TecnicoSerializer(
            queryset,
            many=True,
        )

        return Response(serializer.data)

    serializer = TecnicoSerializer(
        data=request.data
    )

    serializer.is_valid(
        raise_exception=True
    )

    tecnico = serializer.save()

    return Response(
        TecnicoSerializer(tecnico).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH", "PUT"])
@permission_classes([IsAuthenticated, IsAdminRole])
def tecnico_admin_detail(request, tecnico_id):
    try:
        tecnico = Tecnico.objects.get(
            pk=tecnico_id
        )
    except Tecnico.DoesNotExist:
        return Response(
            {
                "detail": "Personal no encontrado."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response(
            TecnicoSerializer(tecnico).data
        )

    serializer = TecnicoSerializer(
        tecnico,
        data=request.data,
        partial=request.method == "PATCH",
    )

    serializer.is_valid(
        raise_exception=True
    )

    tecnico = serializer.save()

    return Response(
        TecnicoSerializer(tecnico).data
    )