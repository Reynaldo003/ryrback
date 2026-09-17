import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ryrback.settings")
import django

django.setup()

from django.db import connections
from Autos.compra_ref_tipificada import (
    COLUMNAS_TABLA,
    TABLA_COMPRA_REF_TIPIFICADA,
    _fecha_entrada,
    _hora_entrada,
)

tabla = TABLA_COMPRA_REF_TIPIFICADA

try:
    c = connections["sqlserver_inv"].cursor()
    where_sql = ""
    params = []
    count_sql = f"SELECT COUNT(*) FROM dbo.{tabla} {where_sql}"
    c.execute(count_sql, params)
    total = c.fetchone()[0]
    print("TOTAL:", total)

    data_sql = f"""
        SELECT {COLUMNAS_TABLA}
        FROM dbo.{tabla}
        {where_sql}
        ORDER BY DtEntrada DESC, HrEntrada DESC, NrNota DESC, rowid__ DESC
        OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
    """
    c.execute(data_sql, params + [0, 3])
    cols = [col[0] for col in c.description]
    print("COLUMNS:", cols)
    for fila in c.fetchall():
        d = dict(zip(cols, fila))
        print(
            d["Agencia"], d["NrNota"], d["Serie"], _fecha_entrada(d["DtEntrada"]),
            _hora_entrada(d["HrEntrada"]), d["TpCompra"], d["Descripcion_texto"] if False else d["DescrProd"],
            d["EstadoTipificacion"], d["VrLiqTotal"],
        )

    # prueba del filtro LIKE q
    like = "%parabrisas%"
    c2 = connections["sqlserver_inv"].cursor()
    c2.execute(
        f"""
        SELECT TOP 3 NrNota, DescrProd, NombreEstandarizado
        FROM dbo.{tabla}
        WHERE COALESCE(DescrProd, N'') LIKE %s OR COALESCE(NombreEstandarizado, N'') LIKE %s
        """,
        [like, like],
    )
    print("BUSQUEDA 'parabrisas':", c2.fetchall())

    # agencias
    c2.execute(f"SELECT DISTINCT Agencia FROM dbo.{tabla} WHERE NULLIF(Agencia, N'') IS NOT NULL ORDER BY Agencia")
    print("AGENCIAS:", [r[0] for r in c2.fetchall()])
    c2.execute(f"SELECT DISTINCT EstadoTipificacion FROM dbo.{tabla} ORDER BY EstadoTipificacion")
    print("ESTADOS:", [r[0] for r in c2.fetchall()])
    c2.execute(f"SELECT DISTINCT TpProduto FROM dbo.{tabla} WHERE NULLIF(TpProduto, N'') IS NOT NULL ORDER BY TpProduto")
    print("TIPOS:", [r[0] for r in c2.fetchall()])
except Exception as e:
    print("ERROR:", type(e).__name__, e)
    import traceback
    traceback.print_exc()