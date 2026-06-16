# PedidosPiezas/views.py
from django.db.models import Q

from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import PedidosPiezas, Piezas
from .serializers import PedidosPiezasSerializer, PiezasSerializer


class PedidosPiezasViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    serializer_class = PedidosPiezasSerializer
    pagination_class = None
    queryset = (
        PedidosPiezas.objects
        .prefetch_related("piezas", "piezas__pieza")
        .all()
        .order_by("-creado")
    )

    def get_queryset(self):
        queryset = super().get_queryset()

        q = (self.request.query_params.get("q") or "").strip()
        dealer = (self.request.query_params.get("dealer") or "").strip()
        estatus = (self.request.query_params.get("estatus") or "").strip()

        if dealer and dealer != "Todos":
            queryset = queryset.filter(dealer__iexact=dealer)

        if estatus and estatus != "Todos":
            queryset = queryset.filter(estatus__iexact=estatus)

        if q:
            queryset = queryset.filter(
                Q(numero_pedido__icontains=q)
                | Q(nombre_cliente__icontains=q)
                | Q(orden_servicio__icontains=q)
                | Q(ticket_sar__icontains=q)
                | Q(canal__icontains=q)
                | Q(asesor__icontains=q)
                | Q(dealer__icontains=q)
                | Q(piezas__numero_parte__icontains=q)
                | Q(piezas__descripcion__icontains=q)
            ).distinct()

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pedido = serializer.save()

        return Response(
            {
                "message": "Pedido registrado correctamente.",
                "data": self.get_serializer(pedido).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        pedido = serializer.save()

        return Response(
            {
                "message": "Pedido actualizado correctamente.",
                "data": self.get_serializer(pedido).data,
            },
            status=status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)

        return Response(
            {"message": "Pedido eliminado correctamente."},
            status=status.HTTP_200_OK,
        )


class PiezasViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    serializer_class = PiezasSerializer
    pagination_class = None
    queryset = Piezas.objects.all().order_by("codigo")

    def get_queryset(self):
        queryset = super().get_queryset()

        q = (self.request.query_params.get("q") or "").strip()

        if q:
            queryset = queryset.filter(
                Q(codigo__icontains=q) |
                Q(nombre__icontains=q)
            )

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pieza = serializer.save()

        return Response(
            {
                "message": "Pieza registrada correctamente.",
                "data": self.get_serializer(pieza).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        pieza = serializer.save()

        return Response(
            {
                "message": "Pieza actualizada correctamente.",
                "data": self.get_serializer(pieza).data,
            },
            status=status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)

        return Response(
            {"message": "Pieza eliminada correctamente."},
            status=status.HTTP_200_OK,
        )