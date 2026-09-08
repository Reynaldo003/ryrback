from django.db import models


class InventarioRefaccionesObsolescencia(models.Model):
    agencia = models.CharField(max_length=100, db_column="Agencia", null=True, blank=True)
    nr_ped_cpa = models.BigIntegerField(db_column="NrPedCpa", null=True, blank=True)
    tp_ped_cpa = models.IntegerField(db_column="TpPedCpa", null=True, blank=True)
    nm_ped = models.CharField(max_length=50, db_column="NmPed", null=True, blank=True)
    qtde_ped = models.DecimalField(max_digits=18, decimal_places=4, db_column="QtdePed", null=True, blank=True)
    vr_pedido = models.DecimalField(max_digits=18, decimal_places=2, db_column="VrPedido", null=True, blank=True)
    situacao_header = models.CharField(max_length=10, db_column="Situacao_Header", null=True, blank=True)
    situacao_item = models.CharField(max_length=10, db_column="Situacao_Item", null=True, blank=True)
    fecha_emision = models.DateField(db_column="Fecha_Emision", null=True, blank=True)
    fecha_creacion = models.DateField(db_column="Fecha_Creacion", null=True, blank=True)
    fecha_modificacion = models.DateField(db_column="Fecha_Modificacion", null=True, blank=True)
    cod_linha_prod = models.CharField(max_length=50, db_column="CodLinhaProd", null=True, blank=True)
    localizacao = models.CharField(max_length=100, db_column="Localizacao", null=True, blank=True)
    cod_prod = models.CharField(max_length=100, db_column="CodProd", null=True, blank=True)
    nm_produto = models.CharField(max_length=500, db_column="NmProduto", null=True, blank=True)
    unidade = models.CharField(max_length=20, db_column="Unidade", null=True, blank=True)
    qtde_estoque = models.DecimalField(max_digits=18, decimal_places=4, db_column="QtdeEstoque", null=True, blank=True)
    vr_estoque = models.DecimalField(max_digits=18, decimal_places=2, db_column="VrEstoque", null=True, blank=True)
    vr_unitario_medio = models.DecimalField(max_digits=18, decimal_places=4, db_column="VrUnitarioMedio", null=True, blank=True)
    qt_reservada = models.DecimalField(max_digits=18, decimal_places=4, db_column="QtReservada", null=True, blank=True)
    qt_pedida = models.DecimalField(max_digits=18, decimal_places=4, db_column="QtPedida", null=True, blank=True)
    grupo_principal = models.CharField(max_length=200, db_column="GrupoPrincipal", null=True, blank=True)
    subgrupo = models.CharField(max_length=200, db_column="Subgrupo", null=True, blank=True)
    nombre_estandarizado = models.CharField(max_length=300, db_column="NombreEstandarizado", null=True, blank=True)
    categoria = models.CharField(max_length=150, db_column="Categoria", null=True, blank=True)
    observacion = models.CharField(max_length=1000, db_column="Observacion", null=True, blank=True)
    fecha_ultima_venta = models.DateField(db_column="Fecha_Ultima_Venta", null=True, blank=True)
    fecha_ult_comp_prod = models.DateField(db_column="Fecha_Ult_Comp_Prod", null=True, blank=True)
    fecha_ult_ped_prod = models.DateField(db_column="Fecha_Ult_Ped_Prod", null=True, blank=True)
    fecha_ult_actu_prod = models.DateField(db_column="Fecha_Ult_Actu_Prod", null=True, blank=True)
    fecha_regis_refac = models.DateField(db_column="Fecha_Regis_Refac", null=True, blank=True)
    fecha_inventario_refac = models.DateField(db_column="Fecha_Inventario_Refac", null=True, blank=True)
    fecha_primera_compra_refac = models.DateField(db_column="Fecha_Primera_Compra_Refac", null=True, blank=True)
    fecha_actualizacion_refac = models.DateField(db_column="Fecha_Actualizacion_Refac", null=True, blank=True)
    vr_uni_ult_cpa = models.DecimalField(max_digits=18, decimal_places=4, db_column="VrUniUltCpa", null=True, blank=True)
    prc_unit_it = models.DecimalField(max_digits=18, decimal_places=4, db_column="PrcUnitIt", null=True, blank=True)
    vr_prod = models.DecimalField(max_digits=18, decimal_places=2, db_column="VrProd", null=True, blank=True)
    fecha_referencia = models.DateField(db_column="Fecha_Referencia", null=True, blank=True)
    dias_desde_ultimo_movimiento = models.IntegerField(db_column="Dias_Desde_Ultimo_Movimiento", null=True, blank=True)
    capa_obsolescencia = models.CharField(max_length=1, db_column="Capa_Obsolescencia", null=True, blank=True)
    categoria_movimiento = models.CharField(max_length=30, db_column="Categoria_Movimiento", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "Inventario_Refacciones_Obsolescencia"

    def __str__(self):
        return f"{self.cod_prod or 'Sin código'} - {self.nm_produto or 'Sin producto'}"