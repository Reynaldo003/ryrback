from rest_framework import serializers


class VWVNSerializer(serializers.Serializer):

    # 1. Serie
    serie = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 2. NrNota
    nr_nota = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    # 3. TpProduto
    tp_producto = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 4. ProdOuServ
    producto_servicio = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 5. PrcUnitario
    precio_unitario = serializers.DecimalField(
        max_digits=18,
        decimal_places=3,
        allow_null=True,
        required=False,
    )

    # 6. VrBrutoItem
    valor_bruto_item = serializers.DecimalField(
        max_digits=18,
        decimal_places=3,
        allow_null=True,
        required=False,
    )

    # 7. InfluiEstat
    influye_estadistica = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 8. VrDescItem
    valor_descuento_item = serializers.DecimalField(
        max_digits=18,
        decimal_places=3,
        allow_null=True,
        required=False,
    )

    # 9. CodCondPgto
    codigo_condicion_pago = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 10. ValorFactura
    valor_factura = serializers.DecimalField(
        max_digits=18,
        decimal_places=3,
        allow_null=True,
        required=False,
    )

    # 11. ValorFacturaSnIva
    valor_factura_sin_iva = serializers.DecimalField(
        max_digits=18,
        decimal_places=3,
        allow_null=True,
        required=False,
    )

    # 12. ValorCompra
    valor_compra = serializers.DecimalField(
        max_digits=18,
        decimal_places=3,
        allow_null=True,
        required=False,
    )

    # 13. ISAN
    isan = serializers.DecimalField(
        max_digits=18,
        decimal_places=3,
        allow_null=True,
        required=False,
    )

    # 14. IVA
    iva = serializers.DecimalField(
        max_digits=18,
        decimal_places=3,
        allow_null=True,
        required=False,
    )

    # 15. CodEntidade
    codigo_entidad = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    # 16. DtEmissao
    fecha_emision = serializers.DateField(
        allow_null=True,
        required=False,
    )

    # 17. Situacao
    situacion = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 18. TpNF
    tipo_nf = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 19. NrMov
    nr_mov = serializers.IntegerField(
        allow_null=True,
        required=False,
    )

    # 20. DrUltVenda
    fecha_ultima_venta = serializers.DateField(
        allow_null=True,
        required=False,
    )

    # 21. RazaoSocial
    razon_social = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 22. TpPessoa
    tipo_persona = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 23. VrTotalProds
    valor_total_productos = serializers.DecimalField(
        max_digits=18,
        decimal_places=3,
        allow_null=True,
        required=False,
    )

    # 24. CodMarca
    codigo_marca = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 25. NmMarca
    nombre_marca = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 26. NmFamilia
    nombre_familia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 27. CondUso
    condicion_uso = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 28. NmCondPgto
    nombre_condicion_pago = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 29. Asesor
    asesor = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # 30. AGENCIA
    agencia = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    