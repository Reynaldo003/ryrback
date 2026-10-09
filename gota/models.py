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


class GotaOrdenTallerVW(models.Model):
    """
    Vista de órdenes de taller activas (GOTA) del almacén analítico
    (SQL Server, base TDSQL_VW). Sólo se consulta desde Django.
    """

    agencia = models.CharField(max_length=255, db_column="Agencia", null=True)
    nr_os = models.BigIntegerField(db_column="OS", null=True)
    nr_atendimento = models.BigIntegerField(db_column="Atencion", null=True)
    tp_os = models.CharField(max_length=255, db_column="TipoOS", null=True)
    subtipo_os = models.CharField(max_length=255, db_column="Subtipo", null=True)
    situacao = models.CharField(max_length=255, db_column="Situacion", null=True)
    dt_abertura = models.DateField(db_column="Apertura", null=True)
    dias_taller = models.IntegerField(db_column="DiasTaller", null=True)
    vin = models.CharField(max_length=255, db_column="Vin", null=True)
    asesor = models.CharField(max_length=255, db_column="Asesor", null=True)
    cliente = models.CharField(max_length=255, db_column="Cliente", null=True)
    telefono = models.CharField(max_length=255, db_column="Telefono", null=True)
    ubicacion = models.CharField(max_length=255, db_column="Ubicacion", null=True)

    class Meta:
        managed = False
        db_table = "GotaOrdenTallerVW"
        verbose_name = "Orden de taller activa (GOTA)"
        verbose_name_plural = "Órdenes de taller activas (GOTA)"

    def __str__(self):
        return f"{self.agencia} · OS {self.nr_os}"


class GotaOrdenComentario(models.Model):
    """
    Comentarios editables que los técnicos capturan sobre una orden de
    taller. Vive en la misma base analítica (SQL Server) y se administra
    por Django a través del alias 'sqlserver_inv'.
    """

    id = models.AutoField(primary_key=True, db_column="IdComentario")
    agencia = models.CharField(max_length=255, db_column="Agencia")
    nr_os = models.BigIntegerField(db_column="NrOS")
    nr_atendimento = models.BigIntegerField(db_column="NrAtendimento", null=True, blank=True)
    texto = models.TextField(db_column="Texto")
    usuario = models.CharField(max_length=50, db_column="Usuario", null=True, blank=True)
    usuario_nombre = models.CharField(max_length=200, db_column="UsuarioNombre", null=True, blank=True)
    creado_en = models.DateTimeField(db_column="CreadoEn", auto_now_add=True)
    actualizado_en = models.DateTimeField(db_column="ActualizadoEn", auto_now=True)
    activo = models.BooleanField(db_column="Activo", default=True)

    class Meta:
        managed = False
        db_table = "GotaOrdenComentario"
        ordering = ["-creado_en", "-id"]
        verbose_name = "Comentario de orden de taller"
        verbose_name_plural = "Comentarios de órdenes de taller"

    def __str__(self):
        return f"OS {self.nr_os} · {self.texto[:40]}"
