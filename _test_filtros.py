# -*- coding: utf-8 -*-
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ryrback.settings")
import django; django.setup()

from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model
from Autos.compra_ref_tipificada import CompraRefTipificadaListView

User = get_user_model()
usuario, _ = User.objects.get_or_create(username="test_tipificada")
factory = APIRequestFactory()

def probar(params, etiqueta):
    request = factory.get("/ventas-vn/api/compra-ref-tipificada/", params)
    force_authenticate(request, user=usuario)
    response = CompraRefTipificadaListView.as_view()(request)
    data = response.data
    print(f"[{etiqueta}] count={data.get('count')} detail={data.get('detail')} opciones.proveedores={data.get('opciones', {}).get('proveedores')}")
    return data

probar({}, "sin filtros")
d = probar({"proveedor": "VOLKSWAGEN DE MEXICO"}, "proveedor=VWM")
d = probar({"proveedor": "AUTOMOTRIZ R&R"}, "proveedor=R&R")
d = probar({"proveedor": "OTROS"}, "proveedor=OTROS")
d = probar({"proveedor": "OTROS", "proveedor_nombre": "ZURICH"}, "OTROS+ZURICH")
d = probar({"proveedor": "OTROS", "proveedor_nombre": "VOLKSWAGEN LEASING"}, "OTROS+LEASING")
d = probar({"proveedor_nombre": "AUTOZONE DE MEXICO"}, "nombre solo")
print("opciones.proveedores (botones):", d["opciones"]["proveedores"])
print("proveedores_nombre (primeros 8):", d["opciones"]["proveedores_nombre"][:8])
d = probar({"serie": "VWM"}, "serie=VWM")
d = probar({"serie": "EA"}, "serie=EA")
d = probar({"serie": "IN"}, "serie=IN")
d = probar({"q": "bomba"}, "q=bomba")
d = probar({"agencia": "Vw Cordoba", "serie": "VWM"}, "agencia+serie")
d = probar({"proveedor": "AUTOMOTRIZ R&R", "serie": "VWM"}, "proveedor+serie")

# Ver que las columnas incluyen Proveedor / CategoriaProveedor
d = probar({"proveedor": "VOLKSWAGEN DE MEXICO", "page_size": 2}, "columnas")
print("columnas en resultados:", list(d["results"][0].keys()))
print("serie en opciones (primeras 10):", d["opciones"]["series"][:10])
print("n total de series:", len(d["opciones"]["series"]))