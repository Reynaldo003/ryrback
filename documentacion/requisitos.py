# documentacion/requisitos.py

def r(id, nombre, descripcion="", obligatorio=True):
    return {
        "id": id,
        "nombre": nombre,
        "descripcion": descripcion,
        "obligatorio": obligatorio,
    }


REQUISITOS_SERVICIOS_FINANCIEROS = [
    # 1. Buró Físico (conserva 'consulta_buro' para expedientes previos)
    r("consulta_buro", "Autorización de Consulta de Buró Físico", "", True),
    # 2. Identificación (conserva 'identificacion' para expedientes previos)
    r("identificacion", "Identificación Oficial Vigente", "INE o Pasaporte vigente", True),
    # 3. Verificación ID
    r("verificacion_id", "Verificación de la ID", "", False),
    # 4. Consentimiento Identidad
    r("consentimiento_validacion_identidad", "Consentimiento de Validación Identidad", "", False),
    # 5. Certificados Especiales
    r("certificados_especiales", "Certificados Especiales", "", False),
    # 6. Carta Preferente
    r("carta_preferente", "Carta Preferente", "", False),
    # 7. Formato Verificación
    r("formato_verificacion_datos", "Formato de Verificación de Datos", "", True),
    # 8. Validación RFC
    r("validacion_rfc", "Validación de RFC", "", False),
    # 9. CURP
    r("curp", "CURP", "Formato actualizado", True),
    # 10. Comprobante Domicilio (conserva 'comprobante_domicilio')
    r("comprobante_domicilio", "Comprobante de Domicilio", "No mayor a 3 meses", True),
    # 11-16. Comprobantes de Ingresos
    r("comprobantes_ingresos_1", "Comprobantes de Ingresos 1", "", True),
    r("comprobantes_ingresos_2", "Comprobantes de Ingresos 2", "", True),
    r("comprobantes_ingresos_3", "Comprobantes de Ingresos 3", "", False),
    r("comprobantes_ingresos_4", "Comprobantes de Ingresos 4", "", False),
    r("comprobantes_ingresos_5", "Comprobantes de Ingresos 5", "", False),
    r("comprobantes_ingresos_6", "Comprobantes de Ingresos 6", "", False),
    # 17-18. Extranjeros
    r("formato_migratorio", "Formato Migratorio", "En caso de extranjeros", False),
    r("formato_domicilio_extranjero", "Formato de Domicilio en el Extranjero", "", False),
    # 19. Encuesta
    r("encuesta_conocimiento_cliente", "Encuesta de Conocimiento del Cliente", "", False),
    # 20. Investigación
    r("investigacion_credito", "Investigación de Crédito", "", False),
    # 21. Siniestros
    r("documentacion_siniestros", "Documentación de Siniestros", "", False),
    # 22. Motivos de Compra
    r("carta_motivos_compra", "Carta de Motivos de Compra", "", False),
    # 23-25. Adicionales
    r("documento_adicional_1", "Documento Adicional 1", "", False),
    r("documento_adicional_2", "Documento Adicional 2", "", False),
    r("documento_adicional_3", "Documento Adicional 3", "", False),
    # 26. Fiscal (conserva 'constancia_fiscal' para expedientes previos)
    r("constancia_fiscal", "Constancia de Situación Fiscal", "Actualizada al mes en curso", False),
    # 27-28. Historial
    r("saldos_vencidos", "Saldos Vencidos", "", False),
    r("reporte_especial_bc", "Reporte Especial BC", "", False),
    # 29. Resumen Operación (conserva 'resumen_operacion')
    r("resumen_operacion", "Resumen de Operación", "", True),
    # 30. ID Adicional
    r("identificaciones_adicionales", "Identificaciones Adicionales", "", False),
    # 31. Buró Digital
    r("autorizacion_buro_digital", "Autorización de Consulta de Buró Digital", "", True),
    # 32. Unidad Adicional
    r("carta_unidad_adicional", "Carta de Unidad Adicional", "", False),
    # 33. Otros
    r("otros", "Otros", "Documentos varios no contemplados", False),
]

REQUISITOS_MORAL = [
    *REQUISITOS_SERVICIOS_FINANCIEROS,
    r("empresa_acta_constitutiva", "Acta Constitutiva", "", True),
    r("empresa_poder_notarial", "Poder Notarial", "", False),
]

REQUISITOS = {
    "fisica_asalariada": {
        "credit": REQUISITOS_SERVICIOS_FINANCIEROS,
        "leasing": REQUISITOS_SERVICIOS_FINANCIEROS,
    },
    "fisica_profesionista": {
        "credit": REQUISITOS_SERVICIOS_FINANCIEROS,
        "leasing": REQUISITOS_SERVICIOS_FINANCIEROS,
    },
    "moral": {
        "credit": REQUISITOS_MORAL,
        "leasing": REQUISITOS_MORAL,
    },
}

PLANTILLAS_SOLICITUD = {
    "fisica_asalariada": {
        "leasing": {
            "value": "persona_fisica_asalariada",
            "archivo": "Solicitud-Persona-Fisica-Asalariada.pdf",
        },
        "credit": {
            "value": "credito_personas_fisicas",
            "archivo": "Solicitud-Credito-Personas-Fisicas.pdf",
        },
    },
    "fisica_profesionista": {
        "credit": {
            "value": "credito_personas_fisicas",
            "archivo": "Solicitud-Credito-Personas-Fisicas.pdf",
        },
        "leasing": {
            "value": "arrendamiento_personas_fisicas",
            "archivo": "Solicitud-Arrendamiento-Personas-Fisicas.pdf",
        },
    },
    "moral": {
        "credit": {
            "value": "credito_personas_morales",
            "archivo": "Solicitud-Credito-Personas-Morales.pdf",
        },
        "leasing": {
            "value": "arrendamiento_personas_morales",
            "archivo": "Solicitud-Arrendamiento-Personas-Morales.pdf",
        },
    },
}

def obtener_plantilla_solicitud(tipo_persona, financiamiento):
    return PLANTILLAS_SOLICITUD.get(tipo_persona, {}).get(financiamiento)

def obtener_requisitos(tipo_persona, financiamiento):
    return REQUISITOS.get(tipo_persona, {}).get(financiamiento)

def obtener_requisito(tipo_persona, financiamiento, requisito_id):
    requisitos = obtener_requisitos(tipo_persona, financiamiento) or []
    return next((item for item in requisitos if item["id"] == requisito_id), None)