from django.db import models


class MatrizOSActivas(models.Model):
    """
    Gestor de Órdenes de Taller (GOTA).

    Matriz de órdenes de servicio que permanecen activas en taller.
    Es una tabla del almacén analítico (TDSQL_VW) y por eso no la
    administra Django: sólo se consulta.
    """

    agencia = models.CharField(max_length=255, db_column="Agencia", null=True)
    nr_atendimento = models.BigIntegerField(db_column="NrAtendimento", null=True)
    nr_os = models.BigIntegerField(db_column="NrOS", null=True)
    tp_os = models.CharField(max_length=255, db_column="TpOS", null=True)
    dt_fechamento = models.DateField(db_column="DtFechamento", null=True)
    hr_fechamento = models.BigIntegerField(db_column="HrFechamento", null=True)
    situacao = models.CharField(max_length=255, db_column="Situacao", null=True)
    cod_pagador = models.BigIntegerField(db_column="CodPagador", null=True)
    vr_adicionais = models.FloatField(db_column="VrAdicionais", null=True)
    vr_adiantam = models.FloatField(db_column="VrAdiantam", null=True)
    vr_total_pecas = models.FloatField(db_column="VrTotalPecas", null=True)
    vr_pecas = models.FloatField(db_column="VrPecas", null=True)
    vr_acessor = models.FloatField(db_column="VrAcessor", null=True)
    vr_om = models.FloatField(db_column="VrOM", null=True)
    vr_lubrif = models.FloatField(db_column="VrLubrif", null=True)
    vr_cascos = models.FloatField(db_column="VrCascos", null=True)
    vr_desc_peca = models.FloatField(db_column="VrDescPeca", null=True)
    motivo_cancel = models.BigIntegerField(db_column="MotivoCancel", null=True)
    perc_desc_pcs = models.FloatField(db_column="PercDescPcs", null=True)
    cod_cond_pgto = models.BigIntegerField(db_column="CodCondPgto", null=True)
    cod_oper_fiscal = models.BigIntegerField(db_column="CodOperFiscal", null=True)
    sit_garantia = models.CharField(max_length=255, db_column="SitGarantia", null=True)
    sit_fiss = models.CharField(max_length=255, db_column="SitFISS", null=True)
    subtipo_os = models.CharField(max_length=255, db_column="SubtipoOS", null=True)
    dt_abertura = models.DateField(db_column="DtAbertura", null=True)
    hr_abertura = models.BigIntegerField(db_column="HrAbertura", null=True)
    tipo_golpe = models.CharField(max_length=255, db_column="TipoGolpe", null=True)
    tem_fun_pin = models.BooleanField(db_column="TemFunPin", null=True)
    nr_gar_hda = models.BigIntegerField(db_column="NrGarHda", null=True)
    filler01 = models.BigIntegerField(db_column="Filler01", null=True)
    func_cancel = models.BigIntegerField(db_column="Func_Cancel", null=True)
    filler03 = models.BigIntegerField(db_column="Filler03", null=True)
    tp_serv_marca = models.CharField(max_length=255, db_column="TpServMarca", null=True)
    check_gm = models.CharField(max_length=255, db_column="CheckGM", null=True)
    flag_pago = models.CharField(max_length=255, db_column="Flag_Pago", null=True)
    uso_cfdi = models.CharField(max_length=255, db_column="Uso_CFDI", null=True)
    autori_crhysler = models.CharField(max_length=255, db_column="AutoriCrhysler", null=True)
    forma_pago = models.CharField(max_length=255, db_column="FormaPago", null=True)
    dt_debloq = models.DateField(db_column="DtDebloq", null=True)
    dt_emi_prefact = models.DateField(db_column="Dt_Emi_Prefact", null=True)
    hr_emi_prefact = models.BigIntegerField(db_column="Hr_Emi_Prefact", null=True)
    hora_llegada = models.BigIntegerField(db_column="HoraLLegada", null=True)
    id_job = models.BigIntegerField(db_column="Id_Job", null=True)
    rowid = models.BigIntegerField(db_column="rowid__", null=True)

    class Meta:
        managed = False
        db_table = "Matriz_OSActivas"
        verbose_name = "Orden de servicio activa"
        verbose_name_plural = "Órdenes de servicio activas"

    def __str__(self):
        return f"{self.agencia} · OS {self.nr_os}"
