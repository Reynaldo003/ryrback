from rest_framework import serializers


class MatrizOSActivasSerializer(serializers.Serializer):
    agencia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    nr_atendimento = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    nr_os = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    tp_os = serializers.CharField(
        allow_null=True,
        allow_blank=True,
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
    situacao = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cod_pagador = serializers.IntegerField(
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
    vr_total_pecas = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_pecas = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_acessor = serializers.FloatField(
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
    vr_cascos = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_desc_peca = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    motivo_cancel = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    perc_desc_pcs = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    cod_cond_pgto = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    cod_oper_fiscal = serializers.IntegerField(
        allow_null=True,
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
    subtipo_os = serializers.CharField(
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
    tipo_golpe = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    tem_fun_pin = serializers.BooleanField(
        allow_null=True,
        required=False,
    )
    nr_gar_hda = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    filler01 = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    func_cancel = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    filler03 = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    tp_serv_marca = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    check_gm = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    flag_pago = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    uso_cfdi = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    autori_crhysler = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    forma_pago = serializers.CharField(
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
    hr_emi_prefact = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    hora_llegada = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    id_job = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    rowid = serializers.IntegerField(
        allow_null=True,
        required=False,
    )


class GotaDashboardSerializer(serializers.Serializer):
    """
    Sólo documenta la forma del payload; el dashboard se arma
    con consultas agregadas y se devuelve sin serializar.
    """

    totales = serializers.DictField(required=False)
    graficas = serializers.DictField(required=False)
