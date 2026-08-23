"""Acceso a datos. Consultas acotadas y SIEMPRE parametrizadas.

Regla dura del proyecto: **el modelo nunca genera SQL**. Produce el JSON del contrato
y nada mas; las consultas viven aqui, con parametros ligados. Es superficie de ataque
y de alucinacion que no se abre.
"""
import json
from datetime import date, timedelta


class Repositorio:
    """Recibe una conexion ya abierta (PyMySQL con DictCursor)."""

    def __init__(self, conn):
        self.conn = conn

    def _q(self, sql, params=()):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    SELECT_BASE = """
        SELECT g.id, g.proveedor_id, g.fecha, g.monto, g.categoria, g.descripcion,
               p.nombre AS proveedor, p.nombre_norm AS proveedor_norm, p.nit
        FROM gastos_esperados g
        JOIN proveedores p ON p.id = g.proveedor_id
    """

    def listar_proveedores_norm(self):
        return self._q("SELECT id, nombre, nombre_norm FROM proveedores")

    def buscar_exacto(self, proveedor_norm, fecha, monto):
        return self._q(
            self.SELECT_BASE + " WHERE p.nombre_norm = %s AND g.fecha = %s AND g.monto = %s",
            (proveedor_norm, fecha, monto),
        )

    def buscar_por_proveedor_fecha(self, proveedor_norm, fecha, tolerancia_dias=3):
        d = _a_fecha(fecha)
        if d is None:
            return []
        return self._q(
            self.SELECT_BASE + " WHERE p.nombre_norm = %s AND g.fecha BETWEEN %s AND %s"
            " ORDER BY ABS(DATEDIFF(g.fecha, %s))",
            (proveedor_norm, d - timedelta(days=tolerancia_dias),
             d + timedelta(days=tolerancia_dias), d),
        )

    def buscar_por_monto(self, monto, fecha=None, tolerancia_dias=3, tolerancia_monto=0.01):
        if fecha is None:
            return self._q(
                self.SELECT_BASE + " WHERE ABS(g.monto - %s) <= %s",
                (monto, tolerancia_monto),
            )
        d = _a_fecha(fecha)
        if d is None:
            return []
        return self._q(
            self.SELECT_BASE + " WHERE ABS(g.monto - %s) <= %s AND g.fecha BETWEEN %s AND %s"
            " ORDER BY ABS(DATEDIFF(g.fecha, %s))",
            (monto, tolerancia_monto, d - timedelta(days=tolerancia_dias),
             d + timedelta(days=tolerancia_dias), d),
        )

    def buscar_por_monto_en_mes(self, monto, fecha, tolerancia_monto=0.01):
        d = _a_fecha(fecha)
        if d is None:
            return []
        primero = d.replace(day=1)
        siguiente = (primero + timedelta(days=32)).replace(day=1)
        return self._q(
            self.SELECT_BASE + " WHERE ABS(g.monto - %s) <= %s AND g.fecha >= %s AND g.fecha < %s",
            (monto, tolerancia_monto, primero, siguiente),
        )

    def buscar_duplicados(self, monto, fecha, tolerancia_monto=0.01):
        """Registros distintos con el mismo monto y la misma fecha: cargo duplicado."""
        return self._q(
            self.SELECT_BASE + " WHERE ABS(g.monto - %s) <= %s AND g.fecha = %s",
            (monto, tolerancia_monto, fecha),
        )

    def guardar_conciliacion(self, contrato):
        r = contrato.get("reconciliation", {})
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO conciliaciones
                   (receipt_id, gasto_id, veredicto, delta, confianza, explicacion,
                    revision_humana, contrato_json)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (contrato.get("receipt_id"),
                 r.get("matched_record_id"),
                 r.get("verdict", "UNCERTAIN"),
                 r.get("delta"),
                 contrato.get("confidence_overall"),
                 (r.get("explanation") or "")[:255],
                 bool(r.get("human_review_required")),
                 json.dumps(contrato, ensure_ascii=False, default=str)),
            )
            return cur.lastrowid

    def resumen_veredictos(self):
        """La consulta que justifica MariaDB en el pitch: agrega sobre el JSON guardado."""
        return self._q(
            """SELECT JSON_UNQUOTE(JSON_EXTRACT(contrato_json, '$.reconciliation.verdict'))
                        AS veredicto,
                      COUNT(*) AS n,
                      ROUND(AVG(confianza), 3) AS confianza_media
               FROM conciliaciones
               GROUP BY veredicto
               ORDER BY n DESC"""
        )

    def listar_conciliaciones(self, limite=100):
        return self._q(
            """SELECT receipt_id, veredicto, delta, confianza, explicacion, creado_en
               FROM conciliaciones ORDER BY id DESC LIMIT %s""",
            (limite,),
        )


def _a_fecha(v):
    if isinstance(v, date):
        return v
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None
