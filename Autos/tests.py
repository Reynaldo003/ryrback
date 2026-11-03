from django.test import SimpleTestCase

from .views import CONDICION_VENTA_VALIDA, construir_where


def filtros_base(**cambios):
    filtros = {
        "cond_uso": "N",
        "q": "",
        "agencia": "",
        "asesor": "",
        "familia": "",
        "condicion_pago": "",
        "serie": "",
        "nr_nota": "",
        "producto_servicio": "",
        "fecha_desde": "2026-10-01",
        "fecha_hasta": "2026-10-31",
        "venta_digital": "",
        "solo_vendidas": "",
    }
    filtros.update(cambios)
    return filtros


class FiltroReporteVentasTests(SimpleTestCase):
    def test_reporte_filtra_ventas_validas_desde_la_consulta(self):
        where_sql, parametros = construir_where(
            filtros_base(solo_vendidas="1")
        )

        self.assertIn(CONDICION_VENTA_VALIDA, where_sql)
        self.assertEqual(parametros, ["2026-10-01", "2026-10-31"])

    def test_detalle_normal_conserva_todos_los_estatus(self):
        where_sql, _ = construir_where(filtros_base())

        self.assertNotIn(CONDICION_VENTA_VALIDA, where_sql)

    def test_criterio_acepta_variantes_booleanas_del_parametro(self):
        for valor in ("1", "true", "si", "sí"):
            with self.subTest(valor=valor):
                where_sql, _ = construir_where(
                    filtros_base(solo_vendidas=valor)
                )
                self.assertIn(CONDICION_VENTA_VALIDA, where_sql)
