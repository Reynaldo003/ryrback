"""Homologación V3 en la BD existente. Predeterminado: simulación sin escrituras.

Aplicación ÚNICAMENTE tras respaldo, revisión de huella y ventana controlada.
No se ejecuta con migrate ni con deploy. No modifica el estado anterior.
"""
import hashlib
import json
import unicodedata
from collections import Counter
from datetime import datetime, time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.utils import timezone
from Digitales.models import ExpedienteDigital, ActividadComercialDigital

EQUIVALENCIAS = {
    'sin contactar': 'nuevo_prospecto',
    'contactado': 'en_seguimiento', 'calificado': 'en_seguimiento',
    'en perfilamiento': 'en_seguimiento', 'potencialmente viable': 'en_seguimiento',
    'seguimiento': 'en_seguimiento', 'cotizacion realizada': 'cotizacion_enviada',
    'cita programada': 'cita_agendada', 'asistencia a la cita': 'cita_asistida',
    'documentos enviados': 'documentos_enviados',
    'autorizado no formalizado': 'autorizado_no_formalizado',
    'facturado': 'facturado', 'descalificado': 'lead_perdido',
}


def normalizar(valor):
    texto = unicodedata.normalize('NFKD', str(valor or ''))
    return ' '.join(''.join(c for c in texto if not unicodedata.combining(c))
                    .replace('_', ' ').casefold().split())


class Command(BaseCommand):
    help = 'Simula por defecto u homologa históricos a V3 con huella y lotes cortos.'

    def add_arguments(self, parser):
        parser.add_argument('--antes-de', required=True, help='Corte exclusivo YYYY-MM-DD')
        parser.add_argument('--aplicar', action='store_true')
        parser.add_argument('--base', default='', help='Nombre exacto de BD efectivo')
        parser.add_argument('--huella', default='', help='SHA256 de la simulación')
        parser.add_argument('--confirmar', default='', help='HOMOLOGAR_PRODUCCION_V3')
        parser.add_argument('--tamano-lote', type=int, default=100)

    def handle(self, *args, **opts):
        try:
            corte_fecha = datetime.strptime(opts['antes_de'], '%Y-%m-%d').date()
        except ValueError as exc:
            raise CommandError('Usa --antes-de YYYY-MM-DD') from exc
        corte = datetime.combine(corte_fecha, time.min)
        if settings.USE_TZ:
            corte = timezone.make_aware(corte, timezone.get_current_timezone())
        if connections['default'].vendor != 'postgresql':
            raise CommandError('Se requiere PostgreSQL.')
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT current_database()')
            nombre_bd = cursor.fetchone()[0]
        if str(nombre_bd) != str(settings.DATABASES['default'].get('NAME', '')):
            raise CommandError('Nombre de BD efectivo diferente de la configuración.')
        tamano = opts['tamano_lote']
        if not 1 <= tamano <= 200:
            raise CommandError('El tamaño de lote debe estar entre 1 y 200.')
        if opts['aplicar']:
            if (opts['confirmar'] != 'HOMOLOGAR_PRODUCCION_V3'
                    or opts['base'] != nombre_bd or not opts['huella']):
                raise CommandError('Faltan confirmación, nombre efectivo de BD o huella.')
            if getattr(settings, 'CRM_ETAPAS_V3_API_HABILITADA', False):
                raise CommandError('La API V3 debe estar desactivada durante la homologación.')

        items = list(ExpedienteDigital.objects.using('default')
                     .filter(creado__lt=corte, etapa_comercial_v3__isnull=True)
                     .order_by('pk')
                     .values('pk', 'estado', 'agencia', 'asesor_digital', 'creado'))
        filas = [(p['pk'], p['estado'], p['agencia'], p['asesor_digital'],
                  p['creado'].isoformat()) for p in items]
        huella = hashlib.sha256(json.dumps(
            {'version': 3, 'corte': opts['antes_de'], 'filas': filas},
            ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
        destinos = Counter(EQUIVALENCIAS.get(normalizar(p['estado']))
                           or 'PENDIENTE_DE_CLASIFICACION' for p in items)
        self.stdout.write(f'BD efectiva: {nombre_bd}')
        self.stdout.write(f'Corte exclusivo: {opts["antes_de"]}')
        self.stdout.write(f'Expedientes candidatos: {len(items)}')
        self.stdout.write(f'Huella SHA256: {huella}')
        for etapa, total in sorted(destinos.items()):
            self.stdout.write(f'  {etapa}: {total}')
        total_homologar = len(items) - destinos['PENDIENTE_DE_CLASIFICACION']
        self.stdout.write(f'Homologables: {total_homologar}')
        if not opts['aplicar']:
            self.stdout.write('SOLO SIMULACION: NO SE MODIFICO NINGUN REGISTRO.')
            return
        if opts['huella'] != huella:
            raise CommandError('Huella diferente. Simula nuevamente antes de escribir.')
        if ActividadComercialDigital.objects.filter(
                clave_idempotencia__startswith='homologacion-v3-').exists():
            raise CommandError('Hay homologaciones anteriores; revisar antes de reintentar.')

        aplicados = 0
        for inicio in range(0, len(items), tamano):
            lote = items[inicio:inicio + tamano]
            try:
                with transaction.atomic(using='default'):
                    nuevas = []
                    for p in lote:
                        etapa = EQUIVALENCIAS.get(normalizar(p['estado']))
                        if not etapa:
                            continue
                        ok = ExpedienteDigital.objects.using('default').filter(
                            pk=p['pk'], creado__lt=corte, etapa_comercial_v3__isnull=True,
                            estado=p['estado'], agencia=p['agencia'],
                            asesor_digital=p['asesor_digital'],
                        ).update(etapa_comercial_v3=etapa)
                        if ok != 1:
                            raise CommandError(f'Expediente {p["pk"]} cambio. Lote revertido.')
                        nuevas.append(ActividadComercialDigital(
                            expediente_id=p['pk'], tipo='correccion', origen='correccion',
                            agencia=p['agencia'] or '', asesor_digital=p['asesor_digital'] or '',
                            usuario_crm='migracion_historica_v3',
                            fecha_actividad=None, etapa_anterior='', etapa_resultante=etapa,
                            clave_idempotencia=f'homologacion-v3-{p["pk"]}',
                            detalle={
                                'evento': 'homologacion_historica_v3',
                                'tipo_registro': 'clasificacion_heredada_no_validada',
                                'estado_legacy_original': p['estado'], 'etapa_destino': etapa,
                                'evidencia_validada_v3': False,
                                'no_es_evento_comercial_confirmado': True,
                                'no_contabilizar_evento_nuevo': True,
                                'requiere_evidencia_para_operaciones_futuras': True,
                                'fecha_creacion_original': p['creado'].isoformat(),
                                'corte_exclusivo': opts['antes_de'],
                                'huella_simulacion': huella,
                            },
                        ))
                    if nuevas:
                        ActividadComercialDigital.objects.using('default').bulk_create(
                            nuevas, batch_size=tamano)
                    aplicados += len(nuevas)
            except Exception as exc:
                raise CommandError(
                    f'FALLO lote {inicio//tamano+1}; {aplicados} ya confirmados en lotes '
                    f'previos. DETENER, auditar, no reintentar a ciegas: {exc}') from exc
            self.stdout.write(f'Lote {inicio//tamano+1}: acumulados {aplicados}')
        self.stdout.write(self.style.SUCCESS(f'HOMOLOGADOS: {aplicados}; pendientes intactos.'))
