import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ryrback.settings")
import django
django.setup()

from django.utils import timezone
from datetime import timedelta

from documentacion.models import Expediente, DocumentoExpediente
from documentacion.tasks import purgar_documentos_expirados, RETENCION_DIAS
from logs.models import LogActividad
from logs.snapshots import capturar_snapshot, restaurar_snapshot
from django.db import transaction

resultado = {}
with transaction.atomic():
    sid = transaction.savepoint()
    try:
        exp = Expediente.objects.create(
            cliente="PRUEBA PPAER15", agencia="AG T", tipo_persona="fisica_profesionista",
            financiamiento="credit", creado_por="prueba",
        )
        doc = DocumentoExpediente.objects.create(
            expediente=exp, requisito_id="ine", requisito_nombre="INE",
            archivo="", nombre_original="ine_prueba.pdf", tamano_bytes=123,
        )
        resultado["doc_creado"] = doc.pk

        snap = capturar_snapshot(f"/documentacion/api/documentos/{doc.pk}/")
        resultado["snapshot_ok"] = bool(snap)
        resultado["snapshot_campos_tiene_archivo"] = bool((snap or {}).get("campos", {}).get("archivo"))

        doc.refresh_from_db()
        doc.eliminado = timezone.now()
        doc.save(update_fields=["eliminado"])
        resultado["soft_delete"] = doc.eliminado is not None
        resultado["registro_existe_tras_borrar"] = DocumentoExpediente.objects.filter(pk=doc.pk).exists()
        resultado["oculto_en_listado"] = not exp.documentos.filter(eliminado__isnull=True).filter(pk=doc.pk).exists()

        log = LogActividad.objects.create(
            usuario=None, tipo="ELIMINAR", modulo="documentacion",
            entidad=f"Documento #{doc.pk} · ine_prueba.pdf",
            cambio=f"Eliminó Documento #{doc.pk}", datos=snap,
        )
        ok, msgs = restaurar_snapshot(log.datos)
        doc.refresh_from_db()
        resultado["restaurar_ok"] = ok
        resultado["restaurar_msgs"] = msgs
        resultado["ya_no_eliminado"] = doc.eliminado is None
        resultado["visible_tras_restaurar"] = exp.documentos.filter(eliminado__isnull=True).filter(pk=doc.pk).exists()

        # purge: envejece el soft delete 16 días y purga
        DocumentoExpediente.objects.filter(pk=doc.pk).update(eliminado=timezone.now() - timedelta(days=16))
        log.datos = dict(log.datos); log.save()
        n, dets = purgar_documentos_expirados(dias=RETENCION_DIAS)
        resultado["purga_elimino"] = not DocumentoExpediente.objects.filter(pk=doc.pk).exists()
        log.refresh_from_db()
        resultado["log_marcado_purgado"] = bool((log.datos or {}).get("purgado"))
        ok2, msgs2 = restaurar_snapshot(log.datos)
        resultado["restaurar_purgado_rechazado"] = (ok2 is False)
        resultado["restaurar_purgado_msg"] = msgs2
    except Exception as e:
        resultado["ERROR"] = repr(e)
    finally:
        transaction.savepoint_rollback(sid)

for k, v in resultado.items():
    print(f"{k}: {v}")
print("[rollback aplicado]")
