"""Comando local seguro para homologar estados legacy a V3.

Instalar como Digitales/management/commands/homologar_estados_v3.py.
No instala migraciones; dry-run predeterminado; jamás habilitar para producción.
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

from Digitales.models import ActividadComercialDigital, ExpedienteDigital

# Equivalencias sujetas a aprobación del negocio. Sólo texto exacto normalizado.
# Ningún estado histórico crea evidencia técnica de eventos anteriores.
import re
from datetime import date

EQUIVALENCIAS = {
    'sin contactar': 'nuevo_prospecto',
    'contactado': 'en_seguimiento',
    'calificado': 'en_seguimiento',
    'en perfilamiento': 'en_seguimiento',
    'potencialmente viable': 'en_seguimiento',
    'seguimiento': 'en_seguimiento',
    'cotizacion realizada': 'cotizacion_enviada',
    'cita programada': 'cita_agendada',
    'asistencia a la cita': 'cita_asistida',
    'documentos enviados': 'documentos_enviados',
    'autorizado no formalizado': 'autorizado_no_formalizado',
    'facturado': 'facturado',
    'descalificado': 'lead_perdido',
}

_PATRON_VIN = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')


def clasificar_expediente_historico(
    item,
    *,
    tiene_cita_agencia=False,
    tiene_cita_asistida_agencia=False,
    tiene_msg_humano_out=False,
):
    """
    Homologa el estado comercial histórico registrado por el asesor.

    No exige retroactivamente evidencias técnicas del CRM V3.
    No certifica eventos que no fueron registrados en V3.
    Los estados ambiguos permanecen pendientes de clasificación.
    """
    return EQUIVALENCIAS.get(normalizar(item.get("estado")))

def normalizar(valor):
    texto = unicodedata.normalize('NFKD', str(valor or ''))
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return ' '.join(texto.replace('_', ' ').casefold().split())


def comprobar_entorno():
    from ipaddress import ip_interface

    db = settings.DATABASES['default']

    bases_locales_permitidas = {
        'crm_etapas_pruebas',
        'crm_v3_homologacion_local',
    }

    # 1. Validar la configuración de Django
    if (
        str(db.get('NAME', '')) not in bases_locales_permitidas
        or str(db.get('HOST', '')) not in {'127.0.0.1', 'localhost'}
    ):
        raise CommandError(
            'BLOQUEADO: sólo se permite crm_etapas_pruebas en PostgreSQL local.'
        )

    if db.get('ENGINE') != 'django.db.backends.postgresql':
        raise CommandError('BLOQUEADO: se requiere PostgreSQL local.')

    # 2. Comprobar la conexión efectiva
    with connections['default'].cursor() as cursor:
        cursor.execute(
            'SELECT current_database(), inet_server_addr()::text'
        )
        nombre_real, ip_real = cursor.fetchone()

    # 3. Aceptar direcciones locales con o sin máscara de red
    try:
        ip_local = (
            ip_real is not None
            and ip_interface(str(ip_real)).ip.is_loopback
        )
    except ValueError:
        ip_local = False

    if nombre_real not in bases_locales_permitidas or not ip_local:
        raise CommandError(
            'BLOQUEADO: la conexión efectiva no corresponde a la BD local autorizada.'
        )


class Command(BaseCommand):
    help = 'Simula (por defecto) u homologa estados históricos del CRM a V3 SOLO en la BD local.'

    def add_arguments(self, parser):
        parser.add_argument('--antes-de', required=True, help='Fecha de corte YYYY-MM-DD (exclusiva)')
        parser.add_argument('--aplicar', action='store_true', help='Escribe cambios sólo con confirmación y huella')
        parser.add_argument('--confirmar-local', default='', help='Debe ser HOMOLOGAR_SOLO_PRUEBAS')
        parser.add_argument('--huella', default='', help='Huella SHA256 de la simulación')

    def handle(self, *args, **opts):
        comprobar_entorno()
        try:
            corte_fecha = datetime.strptime(opts['antes_de'], '%Y-%m-%d').date()
        except ValueError as ex:
            raise CommandError('Usa --antes-de YYYY-MM-DD.') from ex
        corte_dt = datetime.combine(corte_fecha, time.min)
        corte = timezone.make_aware(corte_dt, timezone.get_current_timezone()) if getattr(settings, 'USE_TZ', False) else corte_dt
        aplicar = opts['aplicar']
        if aplicar and (opts['confirmar_local'] != 'HOMOLOGAR_SOLO_PRUEBAS' or not opts['huella']):
            raise CommandError('Para aplicar indica --confirmar-local HOMOLOGAR_SOLO_PRUEBAS y --huella SHA256.')

        with transaction.atomic(using='default'):
            # Lock sólo al aplicar; asegura huella estable durante la escritura.
            qs = ExpedienteDigital.objects.using('default').filter(
                creado__lt=corte, etapa_comercial_v3__isnull=True
            ).order_by('pk')
            if aplicar:
                qs = qs.select_for_update()
            from citas.models import Cita
            from Digitales.models import MensajeWhatsApp

            items = list(qs.values(
                'pk', 'cliente_id', 'estado', 'agencia', 'asesor_digital', 'creado',
                'vin_facturado', 'motivo_descalificacion', 'folio_solicitud_credito',
                'solicitud_credito_estado', 'id_cotizacion', 'asistencia',
                'ultima_cita_agendada', 'ultima_cita_id',
                'primer_contacto_asesor', 'ultimo_contacto_asesor',
            ))
            cliente_ids = [p['cliente_id'] for p in items if p.get('cliente_id')]
            pares_cita = {
                (cid, normalizar(ag))
                for cid, ag in Cita.objects.using('default')
                .filter(cliente_id__in=cliente_ids)
                .values_list('cliente_id', 'agencia')
            } if cliente_ids else set()
            pares_asistencia = {
                (cid, normalizar(ag))
                for cid, ag in Cita.objects.using('default')
                .filter(cliente_id__in=cliente_ids, asistencia=True)
                .values_list('cliente_id', 'agencia')
            } if cliente_ids else set()
            clientes_con_humano = set(
                MensajeWhatsApp.objects.using('default')
                .filter(cliente_id__in=cliente_ids, direction='out', from_ia=False)
                .values_list('cliente_id', flat=True)
            ) if cliente_ids else set()

            for p in items:
                par = (p.get('cliente_id'), normalizar(p.get('agencia')))
                p['_etapa_resuelta'] = clasificar_expediente_historico(
                    p,
                    tiene_cita_agencia=par in pares_cita,
                    tiene_cita_asistida_agencia=par in pares_asistencia,
                    tiene_msg_humano_out=p.get('cliente_id') in clientes_con_humano,
                )
            filas = [(p['pk'], str(p['estado'] or ''), p['_etapa_resuelta']) for p in items]
            firma_data = {'corte': opts['antes_de'], 'filas': filas, 'version': 2}
            firma = hashlib.sha256(json.dumps(firma_data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
            destinos = Counter(etapa or 'PENDIENTE_DE_CLASIFICACION' for _, _, etapa in filas)
            origenes_pendientes = Counter(estado or '(vacío)' for _, estado, etapa in filas if not etapa)
            self.stdout.write(f'Fecha de corte exclusiva: {opts["antes_de"]}')
            self.stdout.write(f'Expedientes sin V3 anteriores al corte: {len(filas)}')
            self.stdout.write(f'Huella SHA256: {firma}')
            for etapa, cuenta in sorted(destinos.items()):
                self.stdout.write(f'  {etapa}: {cuenta}')
            if origenes_pendientes:
                self.stdout.write('Estados históricos pendientes de equivalencia (sin cambios):')
                for estado, cuenta in sorted(origenes_pendientes.items()):
                    self.stdout.write(f'  {estado!r}: {cuenta}')
            if not aplicar:
                self.stdout.write(self.style.WARNING('SIMULACIÓN: no se modificó ningún expediente.'))
                return
            if opts['huella'] != firma:
                raise CommandError('La huella cambió: vuelve a simular antes de aplicar.')
            total = 0
            for item in items:
                etapa = item.get('_etapa_resuelta')
                if not etapa:
                    continue
                if ExpedienteDigital.objects.using('default').filter(pk=item['pk'], etapa_comercial_v3__isnull=True).update(etapa_comercial_v3=etapa) != 1:
                    raise CommandError('Conflicto de actualización; se revierte el lote.')
                ActividadComercialDigital.objects.using('default').create(
                    expediente_id=item['pk'],
                    tipo='correccion', origen='correccion',
                    agencia=item['agencia'] or '', usuario_crm='migracion_historica_v3',
                    asesor_digital=item['asesor_digital'] or '',
                    fecha_actividad=timezone.localdate() if getattr(settings, 'USE_TZ', False) else date.today(),
                    detalle={
                        'evento': 'homologacion_historica_v3',
                        'tipo_registro': 'clasificacion_heredada_no_validada',
                        'requiere_evidencia_para_operaciones_futuras': True,
                        'estado_legacy_original': item['estado'],
                        'etapa_destino': etapa,
                        'evidencia_validada_v3': False,
                        'no_es_evento_comercial_confirmado': True,
                        'corte_exclusivo': opts['antes_de'],
                        'huella_simulacion': firma,
                        'fecha_creacion_original': item['creado'].isoformat(),
                    }, etapa_anterior='', etapa_resultante=etapa,
                    clave_idempotencia=f'homologacion-v3-{item["pk"]}',
                )
                total += 1
            self.stdout.write(self.style.SUCCESS(f'APLICADOS EN BD LOCAL: {total}; excepciones intactas.'))
