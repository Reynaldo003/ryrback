# CrmConformidad/catalogo_interfaces.py
"""
Catálogo de interfaces del menú lateral y su relación con permisos.

Cada clave de interfaz debe coincidir con la clave usada en el frontend
(src/config/interfaces.js) y, cuando un usuario tiene configuradas sus
interfaces manualmente (campo `Usuario.interfaces`), los permisos efectivos
son la unión de los permisos mínimos de cada interfaz seleccionada.

La interfaz "inicio" es siempre visible y no aporta permisos.
"""

PERMISOS_POR_INTERFAZ = {
    "gestion_negocio": ["CRM_COORDINADOR_DIGITAL"],
    "partes": ["CRM_COORDINADOR_DIGITAL"],
    "servicio": ["CRM_COORDINADOR_DIGITAL"],
    "usados": ["CRM_VALUADOR"],
    "inicio": [],
    "calidad": ["CRM_CALIDAD"],
    "comercial": ["CRM_COORDINADOR_DIGITAL"],
    "postventa": ["CRM_POSTVENTA"],
    "retencion": ["CRM_VENTAS"],
    "retencion_no_ventas": ["CRM_VENTAS"],
    "encuesta_whats": ["CRM_RECLAMACIONES"],
    "facturas": ["CRM_CALIDAD"],
    "financieros": ["CRM_FINANCIEROS"],
    "config_ia": ["CRM_DIGITALES"],
    "admin_asesores": ["USUARIOS_ADMIN"],
    "timeforaction": ["CRM_CALIDAD"],
    "flujo_procesos": ["CRM_CALIDAD"],
    "webs": ["CRM_CALIDAD"],
    "gestor_actividades": ["CRM_CALIDAD"],
    "administrativos": ["CRM_RRHH"],
    "qr": ["USUARIOS_ADMIN"],
    "configuracion": ["USUARIOS_ADMIN"],
}


def permisos_por_interfaces(interfaces):
    """Unión de los permisos mínimos de una lista de interfaces."""
    if not isinstance(interfaces, list):
        return []

    permisos = []
    for clave in interfaces:
        for permiso in PERMISOS_POR_INTERFAZ.get(clave, []):
            if permiso not in permisos:
                permisos.append(permiso)

    return permisos