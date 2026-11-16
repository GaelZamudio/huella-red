"""Preparación repetible del esquema y permisos; no borra datos existentes."""
import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "seguridad"))
from configurar import main as configurar_roles  # noqa: E402

# Esquema base y, en orden numérico, cada migración de db/migraciones/.
ARCHIVOS = ["esquema.sql"] + [
    f"migraciones/{p.name}"
    for p in sorted((RAIZ / "migraciones").glob("[0-9][0-9][0-9]-*.sql"))
]
MIGRACION_DOMINIOS = "migraciones/001-dominios.sql"


def instalacion_previa(conn, nombre, contenido):
    """True si el archivo ya estaba aplicado antes de existir el registro de migraciones."""
    if nombre == "esquema.sql":
        tablas = re.findall(r"CREATE TABLE (\w+)", contenido)
        existentes = [t for t in tablas
                      if conn.execute("SELECT to_regclass(%s)", ("public." + t,)).fetchone()[0]]
        if existentes and len(existentes) != len(tablas):
            raise ValueError("Esquema previo incompleto; revisar la base antes de continuar.")
        return bool(existentes)
    if nombre == MIGRACION_DOMINIOS:
        if not conn.execute("SELECT to_regtype('public.d_telefono')").fetchone()[0]:
            return False
        # Reconocer una instalación anterior sin repetir ALTER/CREATE.
        nombres = re.findall(r"(?:ADD CONSTRAINT|CREATE UNIQUE INDEX)\s+(\w+)", contenido)
        for restriccion in nombres + ["ck_d_telefono_formato"]:
            existe = conn.execute(
                """SELECT EXISTS(SELECT FROM pg_constraint WHERE conname=%s)
                   OR to_regclass(%s) IS NOT NULL""",
                (restriccion, "public." + restriccion)).fetchone()[0]
            if not existe:
                raise ValueError(f"Migración previa incompleta: falta {restriccion}")
        if not conn.execute("SELECT to_regtype('public.especie_t')").fetchone()[0]:
            raise ValueError("Migración previa incompleta: falta especie_t")
        return True
    return False  # 002 en adelante: se aplican una sola vez


def preparar():
    with psycopg.connect(host=os.environ["PGHOST"], port=os.environ["POSTGRES_PORT"],
                         dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
                         password=os.environ["POSTGRES_PASSWORD"]) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(4052026)")
        conn.execute("CREATE SCHEMA IF NOT EXISTS huellared_control")
        conn.execute("REVOKE ALL ON SCHEMA huellared_control FROM PUBLIC")
        conn.execute("""CREATE TABLE IF NOT EXISTS huellared_control.migraciones (
                        archivo text PRIMARY KEY, sha256 text NOT NULL,
                        aplicado_en timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        for nombre in ARCHIVOS:
            contenido = (RAIZ / nombre).read_text(encoding="utf-8-sig")
            huella = hashlib.sha256(contenido.replace("\r\n", "\n").encode()).hexdigest()
            anterior = conn.execute(
                "SELECT sha256 FROM huellared_control.migraciones WHERE archivo=%s",
                (nombre,)).fetchone()
            if anterior:
                if anterior[0] != huella:
                    raise ValueError(f"{nombre} cambió después de aplicarse; crea una nueva migración.")
                print(f"Ya registrado: {nombre}")
                continue
            if instalacion_previa(conn, nombre, contenido):
                print(f"Registrada instalación previa: {nombre}")
            else:
                # El gestor de arranque controla una sola transacción.
                conn.execute(re.sub(r"(?m)^\s*(BEGIN|COMMIT);\s*$", "", contenido))
                print(f"Aplicado: {nombre}")
            conn.execute(
                "INSERT INTO huellared_control.migraciones(archivo, sha256) VALUES (%s, %s)",
                (nombre, huella))
    configurar_roles()
    print("Preparación terminada: esquema, migraciones y roles listos.")


if __name__ == "__main__":
    try:
        preparar()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except psycopg.Error as exc:
        raise SystemExit(f"Preparación fallida: SQLSTATE {exc.sqlstate}; "
                         f"{exc.diag.message_primary}") from None