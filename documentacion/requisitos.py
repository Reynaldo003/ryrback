# documentacion/requisitos.py

def r(id, nombre, descripcion="", obligatorio=True): return {"id": id, "nombre": nombre, "descripcion": descripcion, "obligatorio": obligatorio}


REQUISITOS_PROFESIONISTA = [
    r("identificacion", "Identificación oficial", "INE o Pasaporte con Licencia"),
    r("comprobante_domicilio", "Comprobante de domicilio"),
    r("constancia_fiscal", "Constancia de Situación Fiscal"),
    r("estados_cuenta_3_meses", "Estados de Cuenta de últimos 3 meses", "Integrar los tres meses en un solo PDF."),
    r("solicitud_origen", "Solicitud de Origen"),
    r("consulta_buro", "Consulta de Buró firmada"),
    r("resumen_operacion", "Resumen de Operación"),
]


REQUISITOS_MORAL = [
    r("solicitud_origen", "Solicitud de Origen"),
    r("apoderado_identificacion", "INE o Pasaporte del Apoderado"),
    r("apoderado_comprobante_domicilio", "Comprobante de domicilio del Apoderado", "Con fecha actualizada."),
    r("apoderado_constancia_fiscal", "Constancia de Situación Fiscal del Apoderado", "Con fecha actualizada."),
    r("empresa_constancia_fiscal", "Constancia de Situación Fiscal de la Empresa", "Con fecha actualizada."),
    r("empresa_comprobante_domicilio", "Comprobante de Domicilio de la Empresa", "Con fecha actualizada."),
    r("empresa_estados_cuenta", "Estados de Cuenta completos de últimos 2 meses", "Integrar ambos meses en un solo PDF."),
    r("empresa_declaracion_anual", "Acuse de Recibo y Declaración Anual", "Del año anterior. Archivos PDF descargados del SAT."),
    r("empresa_estados_financieros", "Estados Financieros Internos", "Del año anterior, firmados por Apoderado y Contador."),
    r("empresa_acta_constitutiva", "Acta Constitutiva"),
    r("empresa_poder_notarial", "Poder Notarial", "En caso de que aplique.", False),
]


REQUISITOS = {
    "fisica_asalariada": {
        "credit": None,
        "leasing": [
            r("identificacion", "Identificación oficial", "INE o Pasaporte con Licencia"),
            r("comprobante_domicilio", "Comprobante de domicilio"),
            r("constancia_fiscal", "Constancia de Situación Fiscal"),
            r("nomina_ultimos_2_meses", "Comprobantes de Nómina de últimos 2 meses", "Recibos y estados de cuenta. Integrar todo en un solo PDF."),
            r("pagos_especiales", "Recibos de pagos especiales", "Aguinaldo, PTU, bonos o compensaciones anuales, en caso de aplicar.", False),
            r("solicitud_origen", "Solicitud de Origen"),
            r("consulta_buro", "Consulta de Buró firmada"),
            r("resumen_operacion", "Resumen de Operación"),
        ],
    },
    "fisica_profesionista": {
        "credit": REQUISITOS_PROFESIONISTA,
        "leasing": REQUISITOS_PROFESIONISTA,
    },
    "moral": {
        "credit": REQUISITOS_MORAL,
        "leasing": REQUISITOS_MORAL,
    },
}


def obtener_requisitos(tipo_persona, financiamiento): return REQUISITOS.get(tipo_persona, {}).get(financiamiento)


def obtener_requisito(tipo_persona, financiamiento, requisito_id):
    requisitos = obtener_requisitos(tipo_persona, financiamiento) or []
    return next((item for item in requisitos if item["id"] == requisito_id), None)