from rest_framework import serializers


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