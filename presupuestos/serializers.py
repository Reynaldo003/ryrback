from rest_framework import serializers


class MatrizPresupuestosSerializer(serializers.Serializer):
    agencia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    nr_orcamento = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    cod_entidade = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    nome = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    endereco = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    bairro = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cod_munic = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    cep = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    tel_fax1 = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    tel_fax2 = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    tp_pessoa = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cgc = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    rg = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cod_segurad = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    placa_veic = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    chassi = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    km = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    cor_veic = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cod_modelo = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    ano_fabr = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    ano_mod = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    vr_produtos = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_mdo_pub = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    dt_emissao = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    hr_emissao = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    dt_validade = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    dt_aprov = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    sit = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    nr_prisma = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    cor_prisma = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cod_func = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    comentario = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    nr_apolice = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    desc_pcs = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_desc_pcs = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    desc_serv = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_desc_serv = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    nr_at_ped = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    tp_entrega = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    dest_ped = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    tp_preco = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    impr_cod_pcs = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    area_orcam = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cod_contacto = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    cod_pacote = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    sinistro = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    ajustador = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    orcam_dyp = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    pres_elsa_pro = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    pres_elsa_aut = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    nr_atend = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    vr_adicionais = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    nr_remision = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    nr_convenio = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    asegurado = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    taller = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    nr_vale = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    nr_orden_cpa = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cod_empresa = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    cod_filial = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    rowid = serializers.IntegerField(
        allow_null=True,
        required=False,
    )


class MatrizPresupuestosRefSerializer(serializers.Serializer):
    agencia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    nr_orcamento = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    nm_prod = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cod_prod = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    qt_prod = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    preco_pc = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    desc_pc = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_desc_pc = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_liq_pc = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    vr_casco = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    hr_creacion = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    dn_stock = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    dn_media_vta = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    dn_ct_solicitada = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    filler05 = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    filler06 = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    filler07 = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    filler08 = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    filler09 = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    filler10 = serializers.FloatField(
        allow_null=True,
        required=False,
    )
    selec = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    id_casco = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    impr_desc = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    filler12 = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    filler13 = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    filler14 = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    filler15 = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    filler16 = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    cod_pacote = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    filler17 = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    coment_ref = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    dt_creacion = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    filler20 = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    rowid = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
