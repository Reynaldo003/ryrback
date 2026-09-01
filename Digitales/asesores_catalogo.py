from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.permissions import IsAdminRole

from .models import Asesor


class AsesorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asesor
        fields = [
            "id",
            "nombre",
            "telefono",
            "tipo_asesor",
            "area",
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
                "El nombre del asesor es obligatorio."
            )

        return nombre

    def validate_telefono(self, value):
        return str(value or "").strip()

    def validate_tipo_asesor(self, value):
        return str(value or "").strip()

    def validate_area(self, value):
        return str(value or "").strip()

    def validate_agencia(self, value):
        return str(value or "").strip()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def asesores_list(request):
    queryset = Asesor.objects.all()

    activo = str(
        request.query_params.get("activo", "true")
    ).strip().lower()

    if activo in {"true", "1", "si", "sí"}:
        queryset = queryset.filter(activo=True)

    elif activo in {"false", "0", "no"}:
        queryset = queryset.filter(activo=False)

    tipo_asesor = str(
        request.query_params.get("tipo_asesor", "")
    ).strip()

    if tipo_asesor:
        queryset = queryset.filter(
            tipo_asesor__iexact=tipo_asesor
        )

    area = str(
        request.query_params.get("area", "")
    ).strip()

    if area:
        queryset = queryset.filter(
            area__iexact=area
        )

    agencia = str(
        request.query_params.get("agencia", "")
    ).strip()

    if agencia:
        queryset = queryset.filter(
            agencia__iexact=agencia
        )

    serializer = AsesorSerializer(
        queryset,
        many=True,
    )

    return Response(serializer.data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def asesores_admin_list_create(request):
    if request.method == "GET":
        queryset = Asesor.objects.all()

        serializer = AsesorSerializer(
            queryset,
            many=True,
        )

        return Response(serializer.data)

    serializer = AsesorSerializer(
        data=request.data
    )

    serializer.is_valid(
        raise_exception=True
    )

    asesor = serializer.save()

    return Response(
        AsesorSerializer(asesor).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH", "PUT"])
@permission_classes([IsAuthenticated, IsAdminRole])
def asesor_admin_detail(request, asesor_id):
    try:
        asesor = Asesor.objects.get(
            pk=asesor_id
        )
    except Asesor.DoesNotExist:
        return Response(
            {
                "detail": "Asesor no encontrado."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response(
            AsesorSerializer(asesor).data
        )

    serializer = AsesorSerializer(
        asesor,
        data=request.data,
        partial=request.method == "PATCH",
    )

    serializer.is_valid(
        raise_exception=True
    )

    asesor = serializer.save()

    return Response(
        AsesorSerializer(asesor).data
    )