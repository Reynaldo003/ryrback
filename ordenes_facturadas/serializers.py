from rest_framework import serializers


class OrdenFacturadaResumenSerializer(serializers.Serializer):
    agencia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    nros = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    nratendimento = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    tpos = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    subtipoos = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    situacao = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    dtabertura = serializers.DateField(
        allow_null=True,
        required=False,
    )

    dtfechamento = serializers.DateField(
        allow_null=True,
        required=False,
    )

    sitgarantia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    codcondpgto = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    codoperfiscal = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    vradicionais = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    vrdescpeca = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    vrtotalpecas = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    # Total de mano de obra de la OS
    ttmo = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    requisiciones = serializers.IntegerField(
        required=False,
    )

    partidas = serializers.IntegerField(
        required=False,
    )

    valor_productos = serializers.FloatField(
        required=False,
    )

    descuentos = serializers.FloatField(
        required=False,
    )


class OrdenFacturadaDetalleSerializer(serializers.Serializer):
    agencia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    nros = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    nratendimento = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    nrreq = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    dtemissao = serializers.DateField(
        allow_null=True,
        required=False,
    )

    funcresp = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    qtdeitens = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    qtdeatend = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    codprod = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    nmproduto = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    precounit = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    percdesc = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    vrdesc = serializers.FloatField(
        allow_null=True,
        required=False,
    )

    vrprod = serializers.FloatField(
        allow_null=True,
        required=False,
    )