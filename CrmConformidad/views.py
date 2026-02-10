from rest_framework import generics
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from .models import ExpedienteConformidad, ExpedienteDocumento
from .serializers import CasoSerializer, ExpedienteDocumentoSerializer
from django.shortcuts import get_object_or_404
from django.db import transaction

class CasoListCreateView(generics.ListCreateAPIView):
    queryset = ExpedienteConformidad.objects.select_related("cliente").prefetch_related("documentos").order_by("-id_exp")
    serializer_class = CasoSerializer

class CasoDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ExpedienteConformidad.objects.select_related("cliente").prefetch_related("documentos")
    serializer_class = CasoSerializer
    @transaction.atomic
    def perform_destroy(self, instance: ExpedienteConformidad):
        cliente = instance.cliente
        for doc in instance.documentos.all():
            if doc.archivo:
                doc.archivo.delete(save=False)  # elimina archivo físico
            doc.delete()  # elimina registro

        instance.delete()

        if not cliente.expedientes.exists():
            cliente.delete()

class CasoUploadDocsView(generics.GenericAPIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, id_exp):
        exp = get_object_or_404(ExpedienteConformidad, id_exp=id_exp)
        files = request.FILES.getlist("files")
        created = []
        for f in files:
            doc = ExpedienteDocumento.objects.create(
                expediente=exp,
                archivo=f,
                nombre_original=f.name,
                mime=getattr(f, "content_type", None),
                size=f.size,
            )
            created.append(doc)

        ser = ExpedienteDocumentoSerializer(created, many=True, context={"request": request})
        return Response(ser.data, status=status.HTTP_201_CREATED)
class DocDeleteView(generics.DestroyAPIView):
    queryset = ExpedienteDocumento.objects.all()



from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import UsuarioRegisterSerializer, UsuarioLoginSerializer, generar_token_usuario
from .models import Usuario

class AuthRegisterView(APIView):
    def post(self, request):
        ser = UsuarioRegisterSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        user = ser.save()

        # normalmente NO logueas automáticamente en registro, pero puedes hacerlo si quieres
        return Response(
            {
                "id_usuario": user.id_usuario,
                "usuario": user.usuario,
                "correo": user.correo,
                "rol": user.rol.nombre,
                "agencia": user.agencia,
            },
            status=status.HTTP_201_CREATED,
        )


class AuthLoginView(APIView):
    def post(self, request):
        ser = UsuarioLoginSerializer(data=request.data)
        if not ser.is_valid():
            # ser.errors trae {"non_field_errors": [...]}
            return Response({"detail": "Credenciales inválidas."}, status=status.HTTP_401_UNAUTHORIZED)

        user = ser.validated_data["user"]
        token = generar_token_usuario(user.id_usuario)

        return Response(
            {
                "token": token,
                "user": {
                    "id_usuario": user.id_usuario,
                    "nombre": user.nombre,
                    "apellidos": user.apellidos,
                    "usuario": user.usuario,
                    "correo": user.correo,
                    "rol": user.rol.nombre,
                    "agencia": user.agencia,
                },
            },
            status=status.HTTP_200_OK,
        )
