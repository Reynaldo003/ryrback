from django.db import models

# Create your models here.

from django.db import models


class VWVN(models.Model):
    serie = models.CharField(
        max_length=255,
        db_column="Serie",
        null=True,
        blank=True,
    )

    nr_nota = models.IntegerField(
        db_column="NrNota",
        null=True,
        blank=True,
    )

    tp_producto = models.CharField(
        max_length=255,
        db_column="TpProduto",
        null=True,
        blank=True,
    )

    producto_servicio = models.CharField(
        max_length=255,
        db_column="ProdOuServ",
        null=True,
        blank=True,
    )

    precio_unitario = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        db_column="PrcUnitario",
        null=True,
        blank=True,
    )

    valor_bruto_item = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        db_column="VrBrutoItem",
        null=True,
        blank=True,
    )

    influye_estadistica = models.CharField(
        max_length=255,
        db_column="InfluiEstat",
        null=True,
        blank=True,
    )

    valor_descuento_item = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        db_column="VrDescItem",
        null=True,
        blank=True,
    )

    codigo_condicion_pago = models.CharField(
        max_length=255,
        db_column="CodCondPgto",
        null=True,
        blank=True,
    )

    valor_factura = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        db_column="ValorFactura",
        null=True,
        blank=True,
    )

    valor_factura_sin_iva = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        db_column="ValorFacturaSnIva",
        null=True,
        blank=True,
    )

    valor_compra = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        db_column="ValorCompra",
        null=True,
        blank=True,
    )

    isan = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        db_column="ISAN",
        null=True,
        blank=True,
    )

    iva = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        db_column="IVA",
        null=True,
        blank=True,
    )

    codigo_entidad = models.IntegerField(
        db_column="CodEntidade",
        null=True,
        blank=True,
    )

    fecha_emision = models.DateField(
        db_column="DtEmissao",
        null=True,
        blank=True,
    )

    situacion = models.CharField(
        max_length=255,
        db_column="Situacao",
        null=True,
        blank=True,
    )

    tipo_nf = models.CharField(
        max_length=255,
        db_column="TpNF",
        null=True,
        blank=True,
    )

    nr_mov = models.IntegerField(
        db_column="NrMov",
        null=True,
        blank=True,
    )

    fecha_ultima_venta = models.DateField(
        db_column="DrUltVenda",
        null=True,
        blank=True,
    )

    razon_social = models.CharField(
        max_length=255,
        db_column="RazaoSocial",
        null=True,
        blank=True,
    )

    tipo_persona = models.CharField(
        max_length=255,
        db_column="TpPessoa",
        null=True,
        blank=True,
    )

    valor_total_productos = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        db_column="VrTotalProds",
        null=True,
        blank=True,
    )

    codigo_marca = models.CharField(
        max_length=255,
        db_column="CodMarca",
        null=True,
        blank=True,
    )

    nombre_marca = models.CharField(
        max_length=255,
        db_column="NmMarca",
        null=True,
        blank=True,
    )

    nombre_familia = models.CharField(
        max_length=255,
        db_column="NmFamilia",
        null=True,
        blank=True,
    )

    condicion_uso = models.CharField(
        max_length=255,
        db_column="CondUso",
        null=True,
        blank=True,
    )

    nombre_condicion_pago = models.CharField(
        max_length=255,
        db_column="NmCondPgto",
        null=True,
        blank=True,
    )

    asesor = models.CharField(
        max_length=255,
        db_column="Asesor",
        null=True,
        blank=True,
    )

    agencia = models.CharField(
        max_length=255,
        db_column="AGENCIA",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "VW_VN"

    def __str__(self):
        return f"{self.serie or 'Sin serie'} - {self.razon_social or 'Sin cliente'}"