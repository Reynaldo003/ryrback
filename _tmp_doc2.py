import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ryrback.settings")
import django
django.setup()

from documentacion.models import DocumentoExpediente
from logs.snapshots import snapshot_instancia, restaurar_snapshot

d = DocumentoExpediente.objects.exclude(archivo="").order_by("-id_documento").first()
print("doc real:", d.pk, d.nombre_original, "archivo.name:", d.archivo.name)
s = snapshot_instancia(d)
print("archivo en snapshot:", repr(s["campos"].get("archivo")))

# soft delete + restaurar con archivo real
from django.db import transaction
from django.utils import timezone
with transaction.atomic():
    sid = transaction.savepoint()
    try:
        d.eliminado = timezone.now()
        d.save(update_fields=["eliminado"])
        ok, msgs = restaurar_snapshot(s)
        d.refresh_from_db()
        print("soft restore ok:", ok, "| msgs:", msgs, "| eliminado:", d.eliminado)
    finally:
        transaction.savepoint_rollback(sid)
