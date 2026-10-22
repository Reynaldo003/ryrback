# documentacion/tasks.py
"""
Purga definitiva de documentos eliminados (soft delete).

Los documentos marcados con `eliminado` se conservan RETENCION_DIAS días
para poder recuperarlos desde Logs. Pasado ese plazo se borran el registro
y el archivo físico (via signal post_delete).
"""
from datetime import timedelta

from django.utils import timezone

from logs.models import LogActividad

from .models import DocumentoExpediente

RETENCION_DIAS = 15


def purgar_documentos_expirados(dias=RETENCION_DIAS, dry_run=False):
    """Borra documentos eliminados hace más de `dias` días.

    Devuelve (eliminados, detalles).
    """
    corte = timezone.now() - timedelta(days=max(1, int(dias)))
    qs = (
        DocumentoExpediente.objects
        .filter(eliminado__isnull=False, eliminado__lt=corte)
        .select_related("expediente")
        .order_by("eliminado")
    )

    detalles = []
    eliminados = 0

    for doc in qs:
        folio = getattr(doc.expediente, "folio", "") or ""
        descripcion = f"{doc.nombre_original} ({doc.requisito_nombre}) · expediente {folio}"

        if dry_run:
            detalles.append(f"[dry-run] Se purgaría: {descripcion}")
            continue

        # El log que registró la eliminación deja de ser restaurable:
        # el archivo físico desaparece con la purga.
        try:
            logs = LogActividad.objects.filter(
                tipo="ELIMINAR",
                datos__modelo="documentacion.DocumentoExpediente",
                datos__pk=doc.pk,
            )
            for log in logs:
                if isinstance(log.datos, dict):
                    datos = dict(log.datos)
                    datos["purgado"] = True
                    LogActividad.objects.filter(pk=log.pk).update(datos=datos)
        except Exception:
            pass

        # Borra el registro; el signal post_delete borra el archivo físico.
        doc.delete()
        eliminados += 1
        detalles.append(f"Purgado: {descripcion}")

    return eliminados, detalles
