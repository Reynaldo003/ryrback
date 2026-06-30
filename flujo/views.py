# flujo/views.py

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import DiagramaFlujo
from .serializers import DiagramaFlujoSerializer


class DiagramaFlujoViewSet(viewsets.ModelViewSet):
    serializer_class = DiagramaFlujoSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        usuario = self.request.user

        qs = DiagramaFlujo.objects.select_related("usuario")

        if usuario and usuario.is_authenticated:
            qs = qs.filter(usuario=usuario)

        buscar = str(self.request.query_params.get("buscar", "")).strip()

        if buscar:
            qs = qs.filter(nombre__icontains=buscar)

        return qs.order_by("-actualizado_en")

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    def perform_update(self, serializer):
        # El usuario dueño no se cambia desde el payload.
        serializer.save(usuario=self.request.user)

    @action(detail=True, methods=["post"], url_path="duplicar")
    def duplicar(self, request, id=None):
        original = self.get_object()

        with transaction.atomic():
            copia = DiagramaFlujo.objects.create(
                usuario=request.user,
                nombre=f"{original.nombre} copia",
                descripcion=original.descripcion,
                pasos=original.pasos,
                nodos=original.nodos,
                conexiones=original.conexiones,
                metadatos=original.metadatos,
            )

        serializer = self.get_serializer(copia)
        return Response(serializer.data, status=status.HTTP_201_CREATED)