from rest_framework import serializers


# ============================================================
# FACTURA
# dbo.Matriz_FacturasRef
# ============================================================

class CompraRefaccionesSerializer(serializers.Serializer):
    rowid__ = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    agencia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    nrnota = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    serie = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    nrpedunpar = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    qtprodutos = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    proveedor = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    dtemissao = serializers.DateField(
        allow_null=True,
        required=False,
    )

    dtentrada = serializers.DateField(
        allow_null=True,
        required=False,
    )

    subtotal = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    total = serializers.FloatField(
        allow_null=True,
        required=False,
    )

class CompraRefaccionPiezaSerializer(serializers.Serializer):
    rowid__ = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    agencia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    nrnota = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    serie = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    seqitem = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    prodserv = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    descrprod = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    unidade = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    qtprodutos = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    vrunitliq = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    vrunitbruto = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    vrliqtotal = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    dtentrada = serializers.DateField(
        allow_null=True,
        required=False,
    )

    nrpedcompra = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )