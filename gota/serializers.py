from rest_framework import serializers

from .models import GotaOrdenComentario


class MatrizOSActivasSerializer(serializers.Serializer):
    """
    Da forma a las filas que devuelve la vista GotaOrdenTallerVW.
    """

    agencia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    nr_os = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    nr_atendimento = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    tp_os = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    subtipo_os = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    situacao = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    dt_abertura = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    hr_abertura = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    dias_taller = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    id_job = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    vr_pecas = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_om = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_lubrif = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_acessor = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_cascos = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_adicionais = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_adiantam = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_desc_peca = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    perc_desc_pcs = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_total_pecas = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    cod_pagador = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    pagador = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cod_cond_pgto = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cod_oper_fiscal = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    forma_pago = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    uso_cfdi = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    sit_garantia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    sit_fiss = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    motivo_cancel = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    dt_debloq = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    dt_emi_prefact = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    hora_llegada = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    dt_fechamento = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    hr_fechamento = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    rowid = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    comentarios = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    comentarios_n = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    vin = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    asesor = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cliente = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    telefono = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    ubicacion = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )


class GotaOrdenComentarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = GotaOrdenComentario
        fields = [
            "id",
            "agencia",
            "nr_os",
            "nr_atendimento",
            "texto",
            "usuario",
            "usuario_nombre",
            "creado_en",
            "actualizado_en",
            "activo",
        ]
        read_only_fields = [
            "id",
            "usuario",
            "usuario_nombre",
            "creado_en",
            "actualizado_en",
            "activo",
        ]


class GotaDashboardSerializer(serializers.Serializer):
    """
    Sólo documenta la forma del payload; el dashboard se arma
    con consultas agregadas y se devuelve sin serializar.
    """

    totales = serializers.DictField(required=False)
    graficas = serializers.DictField(required=False)
