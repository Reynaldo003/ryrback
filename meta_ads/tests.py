from django.test import SimpleTestCase

from .views import es_objetivo_alcance


class ObjetivoAlcanceTests(SimpleTestCase):
    def test_reconoce_identificadores_actuales_y_anteriores(self):
        for objetivo in ("REACH", "BRAND_AWARENESS", "OUTCOME_AWARENESS"):
            with self.subTest(objetivo=objetivo):
                self.assertTrue(es_objetivo_alcance(objetivo))

    def test_comparacion_es_exacta_y_no_depende_de_mayusculas(self):
        self.assertTrue(es_objetivo_alcance("reach"))
        self.assertFalse(es_objetivo_alcance("LEAD_GENERATION"))
        self.assertFalse(es_objetivo_alcance("AWARENESS_LEADS"))
        self.assertFalse(es_objetivo_alcance("MY_REACH_CAMPAIGN"))

    def test_objetivos_desconocidos_o_ausentes_no_son_alcance(self):
        self.assertFalse(es_objetivo_alcance(None))
        self.assertFalse(es_objetivo_alcance(""))
        self.assertFalse(es_objetivo_alcance("UNKNOWN"))
