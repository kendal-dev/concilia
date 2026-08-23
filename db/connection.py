"""Conexion a MariaDB.

UNA conexion con reintento. Sin pool: PyMySQL no trae pool nativo y CONCILIA es un CLI
de proceso unico que procesa recibos en serie. Un pool aqui seria decoracion.

El reintento no es defensivo porque si: el contenedor tarda 10-20 s en aceptar
conexiones despues de `docker compose up -d`, y sin backoff la primera corrida
falla siempre.
"""
import os
import time

import pymysql
from dotenv import load_dotenv

load_dotenv()


def get_connection(retries: int = 10, backoff_s: float = 2.0) -> "pymysql.Connection":
    ultimo = None
    for _ in range(retries):
        try:
            return pymysql.connect(
                host=os.environ.get("DB_HOST", "127.0.0.1"),
                port=int(os.environ.get("DB_PORT", "3307")),
                user=os.environ.get("DB_USER", "concilia"),
                password=os.environ.get("DB_PASSWORD", "concilia"),
                database=os.environ.get("DB_NAME", "concilia"),
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )
        except pymysql.err.OperationalError as e:
            ultimo = e
            time.sleep(backoff_s)
    raise ConnectionError(
        f"MariaDB no responde tras {retries} intentos: {ultimo}\n"
        f"Levantala con: docker compose up -d"
    )
