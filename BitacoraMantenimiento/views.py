import json

from django.db import transaction
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Bitacora, Evidencia, Reactivo
from .serializers import BitacoraSerializer


class BitacoraCreateView(APIView):
    parser_classes = [MultiPartParser]

    @transaction.atomic
    def post(self, request):
        data = request.data

        try:
            reactivos_data = json.loads(data.get("reactivos", "[]"))
        except json.JSONDecodeError:
            return Response(
                {"detail": "El campo 'reactivos' no es JSON válido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bitacora = Bitacora.objects.create(
            folio=data.get("folio"),
            chasis_vin=data.get("chasisVin", ""),
            fecha_ingreso=data.get("fechaIngreso") or None,
            anio_modelo_color=data.get("anioModeloColor", ""),
            responsable=data.get("responsable", ""),
            fecha_captura=data.get("fechaCaptura"),
        )

        for r in reactivos_data:
            reactivo = Reactivo.objects.create(
                bitacora=bitacora,
                reactivo_id=r.get("id"),
                titulo=r.get("titulo", ""),
                estado=r.get("estado"),
                observaciones=r.get("observaciones", ""),
            )

            # Los archivos vienen con nombre de campo "evidencia_<reactivo_id>"
            archivos = request.FILES.getlist(f"evidencia_{reactivo.reactivo_id}")
            for archivo in archivos:
                Evidencia.objects.create(reactivo=reactivo, archivo=archivo)

        serializer = BitacoraSerializer(bitacora)
        return Response(serializer.data, status=status.HTTP_201_CREATED)