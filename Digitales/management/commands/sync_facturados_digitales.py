# Digitales/management/commands/sync_facturados_digitales.py
"""Sincroniza ventas facturadas desde SQL Server hacia ExpedienteDigital.

Lee OrdenServicioVentaVW (DB 'sqlserver_inv') y:

  - Por teléfono: llena vin_facturado/facturado_at en expedientes sin VIN,
    cruzando telefono_cliente de la venta con cliente.telefono del CRM.
  - Por VIN: rellena facturado_at/vin_estatus_entrega/estado en expedientes
    que ya tienen VIN pero carecen de fecha de facturación.

Uso:
    python manage.py sync_facturados_digitales
    python manage.py sync_facturados_digitales --dry-run
    python manage.py sync_facturados_digitales --meses 24
    python manage.py sync_facturados_digitales --solo-vin
    python manage.py sync_facturados_digitales --solo-telefono
    python manage.py sync_facturados_digitales --todo
"""
import re
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from citas.models import normaliza_tel_mx
from retencion.models import OrdenServicioVentaVW

from Digitales.models import ExpedienteDigital
from Digitales.serializers import ProspectoSerializer

DB_VENTAS = "sqlserver_inv"

_PATRON_VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

_SERIALIZER = ProspectoSerializer()


def _vin_limpio(valor):
    return str(valor or "").strip().upper()


def _vin_valido(valor):
    return bool(_PATRON_VIN.fullmatch(_vin_limpio(valor)))


def _dt_desde_fecha(fecha):
    if not fecha:
        return None
    if isinstance(fecha, datetime):
        return fecha
    return datetime.combine(fecha, datetime.min.time())


def _mejor_venta_por_vin(actual, fila):
    def _clave(v):
        return v.get("fecha_venta") or v.get("fecha_salida") or date.min
    if actual is None:
        return fila
    if _clave(fila) > _clave(actual):
        return fila
    return actual


class Command(BaseCommand):
    help = (
        "Sincroniza ventas facturadas (OrdenServicioVentaVW) hacia "
        "ExpedienteDigital.vin_facturado/facturado_at por teléfono y por VIN."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Solo reportar, no escribir.")
        parser.add_argument("--todo", action="store_true", help="Revisar todas las ventas sin límite de fecha.")
        parser.add_argument("--desde", type=str, default="", help="Fecha mínima de venta (YYYY-MM-DD).")
        parser.add_argument("--hasta", type=str, default="", help="Fecha máxima de venta (YYYY-MM-DD).")
        parser.add_argument("--meses", type=int, default=12, help="Ventana en meses hacia atrás (desde hoy).")
        parser.add_argument("--solo-vin", action="store_true", help="Solo la pasada por VIN.")
        parser.add_argument("--solo-telefono", action="store_true", help="Solo la pasada por teléfono.")
        parser.add_argument(
            "--recomputar-fechas",
            action="store_true",
            help="Actualizar facturado_at con la fecha real de venta aunque ya tenga valor.",
        )
        parser.add_argument("--sin-estado", action="store_true", help="No modificar 'estado' del expediente.")
        parser.add_argument("--batch-size", type=int, default=1000, help="Tamaño de lote para consultas.")

    def _parsear_fecha(self, texto, nombre):
        if not texto:
            return None
        try:
            return datetime.strptime(texto.strip(), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            raise CommandError(
                "Parámetro --%s inválido: %r (formato YYYY-MM-DD)"
                % (nombre, texto)
            )

    def _ventas_en_rango(self, desde, hasta, todo, batch):
        qs = (
            OrdenServicioVentaVW.objects.using(DB_VENTAS)
            .exclude(total_nota=None)
            .filter(total_nota__gt=0)
            .values("vin", "fecha_venta", "fecha_salida", "telefono_cliente")
        )
        if not todo:
            if desde:
                qs = qs.filter(fecha_venta__gte=desde)
            if hasta:
                qs = qs.filter(fecha_venta__lte=hasta)
        return qs.iterator(chunk_size=batch)

    def _sync_por_telefono(self, desde, hasta, todo, batch, dry, sin_estado):
        por_telefono = {}
        total_ventas = 0
        ventas_utilizables = 0
        for fila in self._ventas_en_rango(desde, hasta, todo, batch):
            total_ventas += 1
            vin = _vin_limpio(fila.get("vin"))
            if not _vin_valido(vin):
                continue
            tel = normaliza_tel_mx(fila.get("telefono_cliente") or "")
            if not tel:
                continue
            ventas_utilizables += 1
            por_telefono[tel] = _mejor_venta_por_vin(por_telefono.get(tel), fila)

        self.stdout.write(
            f"Pass teléfono: {total_ventas} ventas en rango, "
            f"{ventas_utilizables} con teléfono válido ({len(por_telefono)} teléfonos únicos)."
        )

        if not por_telefono:
            self.stdout.write("  Sin ventas para cruzar por teléfono.")
            return 0, 0

        telefonos = list(por_telefono)
        usados = set(
            ExpedienteDigital.objects.exclude(vin_facturado="")
            .values_list("vin_facturado", flat=True)
        )
        usados = {_vin_limpio(v) for v in usados}

        qs = (
            ExpedienteDigital.objects.select_related("cliente")
            .filter(vin_facturado="", cliente__telefono__in=telefonos)
            .order_by("id")
        )
        candidatos = qs.count()
        self.stdout.write(f"  Expedientes sin VIN con teléfono que vendió: {candidatos}.")

        procesados = 0
        omitidos_conflicto = 0
        for exp in qs.iterator(chunk_size=batch):
            venta = por_telefono.get(exp.cliente.telefono)
            if not venta:
                continue
            vin = _vin_limpio(venta.get("vin"))
            if vin in usados:
                omitidos_conflicto += 1
                continue

            cambios = []
            if _vin_limpio(exp.vin_facturado) != vin:
                exp.vin_facturado = vin
                cambios.append("vin_facturado")
            if not exp.facturado_at:
                exp.facturado_at = _dt_desde_fecha(venta.get("fecha_venta"))
                cambios.append("facturado_at")
            entregado = bool(venta.get("fecha_salida"))
            if entregado and _vin_limpio(exp.vin_estatus_entrega) != "entregado":
                exp.vin_estatus_entrega = "entregado"
                cambios.append("vin_estatus_entrega")
            if not sin_estado:
                nuevo_estado = _SERIALIZER._resolver_estado_automatico(
                    exp,
                    {
                        "vin_facturado": vin,
                        "vin_estatus_entrega": "entregado" if entregado else "",
                    },
                )
                if nuevo_estado and _vin_limpio(exp.estado) != _vin_limpio(nuevo_estado):
                    exp.estado = nuevo_estado
                    cambios.append("estado")

            if cambios:
                if not dry:
                    cambios.append("actualizado")
                    exp.save(update_fields=list(dict.fromkeys(cambios)))
                procesados += 1
                usados.add(vin)

        self.stdout.write(f"  Expedientes actualizados por teléfono: {procesados}; conflictos de VIN: {omitidos_conflicto}.")
        return procesados, omitidos_conflicto

    def _sync_por_vin(self, batch, dry, sin_estado, recomputar):
        qs = (
            ExpedienteDigital.objects.exclude(vin_facturado="")
            .order_by("id")
        )
        exp_por_vin = {}
        total_necesitados = 0
        for exp in qs.only(
            "id", "vin_facturado", "facturado_at",
            "vin_estatus_entrega", "estado",
        ).iterator(chunk_size=batch):
            vin = _vin_limpio(exp.vin_facturado)
            if not vin:
                continue
            necesita = recomputar or not exp.facturado_at
            if not necesita:
                continue
            total_necesitados += 1
            exp_por_vin.setdefault(vin, []).append(exp)

        self.stdout.write(
            f"Pass VIN: {len(exp_por_vin)} VINs a verificar ({total_necesitados} expedientes)."
        )

        if not exp_por_vin:
            return 0

        vins = list(exp_por_vin)
        ventas_por_vin = {}
        for i in range(0, len(vins), batch):
            lote = vins[i:i + batch]
            filas = (
                OrdenServicioVentaVW.objects.using(DB_VENTAS)
                .filter(vin__in=lote)
                .values("vin", "fecha_venta", "fecha_salida")
            )
            for fila in filas:
                v = _vin_limpio(fila.get("vin"))
                if v:
                    ventas_por_vin[v] = _mejor_venta_por_vin(ventas_por_vin.get(v), fila)

        sin_venta = sum(1 for v in exp_por_vin if v not in ventas_por_vin)
        self.stdout.write(
            f"  VINs encontrados en SQL Server: {len(ventas_por_vin)}; sin venta registrada: {sin_venta}."
        )

        procesados = 0
        omitidos_descalificados = 0
        for vin, expedientes in exp_por_vin.items():
            venta = ventas_por_vin.get(vin)
            if not venta:
                continue
            for exp in expedientes:
                cambios = []
                fecha = _dt_desde_fecha(venta.get("fecha_venta"))
                if recomputar or not exp.facturado_at:
                    if fecha and exp.facturado_at != fecha:
                        exp.facturado_at = fecha
                        cambios.append("facturado_at")
                entregado = bool(venta.get("fecha_salida"))
                if entregado and _vin_limpio(exp.vin_estatus_entrega) != "entregado":
                    exp.vin_estatus_entrega = "entregado"
                    cambios.append("vin_estatus_entrega")
                if not sin_estado:
                    nuevo_estado = _SERIALIZER._resolver_estado_automatico(
                        exp,
                        {
                            "vin_facturado": vin,
                            "vin_estatus_entrega": "entregado" if entregado else "",
                        },
                    )
                    if nuevo_estado and _vin_limpio(exp.estado) != _vin_limpio(nuevo_estado):
                        exp.estado = nuevo_estado
                        cambios.append("estado")
                    elif not nuevo_estado:
                        omitidos_descalificados += 1

                if cambios:
                    if not dry:
                        cambios.append("actualizado")
                        exp.save(update_fields=list(dict.fromkeys(cambios)))
                    procesados += 1

        self.stdout.write(
            f"  Expedientes actualizados por VIN: {procesados} "
            f"(descalificados sin transición: {omitidos_descalificados})."
        )
        return procesados

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        todo = opts["todo"]
        batch = opts["batch_size"]
        sin_estado = opts["sin_estado"]
        recomputar = opts["recomputar_fechas"]

        hasta = self._parsear_fecha(opts["hasta"], "hasta") or date.today()
        desde = self._parsear_fecha(opts["desde"], "desde")
        if desde is None and not todo:
            desde = hasta - timedelta(days=30 * opts["meses"])

        self.stdout.write(
            "Rango de ventas: %s -> %s | dry-run=%s | batch=%s"
            % ("TODO" if todo else (desde or "-inf"), hasta, dry, batch)
        )

        if not (opts["solo_vin"] or opts["solo_telefono"]):
            self._sync_por_telefono(desde, hasta, todo, batch, dry, sin_estado)
            self._sync_por_vin(batch, dry, sin_estado, recomputar)
        elif opts["solo_telefono"]:
            self._sync_por_telefono(desde, hasta, todo, batch, dry, sin_estado)
        elif opts["solo_vin"]:
            self._sync_por_vin(batch, dry, sin_estado, recomputar)

        self.stdout.write("Sync de facturados finalizado.")