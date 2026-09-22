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

    qtprodutos = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    unidade = serializers.CharField(
        allow_null=True,
        allow_blank=True,
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

    vrunitliq = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    dtentrada = serializers.DateField(
        allow_null=True,
        required=False,
    )

    dtemissao = serializers.DateField(
        allow_null=True,
        required=False,
    )

    vrunitbruto = serializers.FloatField(
        allow_null=True,
        required=False,
    )