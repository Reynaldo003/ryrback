import os, re, traceback
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ryrback.settings")
import django
django.setup()

from logs import snapshots as S

from documentacion.models import DocumentoExpediente
cual = DocumentoExpediente.objects.order_by("-id_documento").first()
print("doc existente:", cual.pk if cual else None)
path = f"/documentacion/api/documentos/{cual.pk}/" if cual else "/documentacion/api/documentos/448/"
for patron, ref, hijos in S._RUTAS:
    m = re.match(patron, path)
    if m:
        print("MATCH:", patron, "->", ref, "grupo1=", m.group(1))
        try:
            modelo = S._modelo_desde_string(ref)
            print("  modelo:", modelo)
            obj = modelo.objects.filter(pk=int(m.group(1))).first()
            print("  obj:", obj)
            if obj:
                snap = S.snapshot_instancia(obj, hijos=hijos)
                print("  snapshot:", snap)
        except Exception:
            traceback.print_exc()
        break
else:
    print("SIN MATCH para", path)
