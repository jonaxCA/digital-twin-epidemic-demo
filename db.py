"""Conexion directa a PostgreSQL. Sistema monolitico: sin capa de microservicios,
un solo pool de conexiones para toda la app (tal como se pidio: "se puede
entrar de manera indiscriminada a la DB").
"""
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres_pw@localhost:5432/simulador_epidemico",
)


@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def query(sql, params=None, one=False):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            return (rows[0] if rows else None) if one else rows


def execute(sql, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
