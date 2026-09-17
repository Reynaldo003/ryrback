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
    print(f"[{etiqueta}] count={data.get('count')} detail={data.get('detail')}")
    return data

p = probar({}, "sin filtros")
print("botones proveedores:", p["opciones"]["proveedores"])
print("total select OTROS:", len(p["opciones"]["proveedores_nombre"]))
print("primeros select:", p["opciones"]["proveedores_nombre"][:5])

probar({"proveedor": "VOLKSWAGEN DE MEXICO"}, "proveedor=VW MEXICO")
probar({"proveedor": "AUTOMOTRIZ R&R"}, "proveedor=AUTOMOTRIZ R&R")
probar({"proveedor": "OTROS"}, "proveedor=OTROS")
probar({"agencia": "Vw Cordoba", "proveedor": "VOLKSWAGEN DE MEXICO"}, "agencia + VW MEXICO")
probar({"estado": "SIN TIPIFICAR", "proveedor": "VOLKSWAGEN DE MEXICO"}, "estado + VW MEXICO")