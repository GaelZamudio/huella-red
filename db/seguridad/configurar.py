"""Configura 1.6 de forma transaccional. Requiere psycopg 3 y variables de entorno."""
import os
from pathlib import Path

import psycopg
from psycopg import sql

USUARIOS = [("huellared_app", "hr_app", "HUELLARED_APP_PASSWORD"),
            ("huellared_consulta", "hr_consulta", "HUELLARED_CONSULTA_PASSWORD"),
            ("huellared_admin", "hr_admin", "HUELLARED_ADMIN_PASSWORD")]


def required(name):
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Falta la variable de entorno {name}")
    return value


def main():
    passwords = {usuario: required(var) for usuario, _, var in USUARIOS}
    db = required("POSTGRES_DB")
    with psycopg.connect(host=os.environ.get("PGHOST", "localhost"),
                         port=required("POSTGRES_PORT"), dbname=db,
                         user=required("POSTGRES_USER"),
                         password=required("POSTGRES_PASSWORD")) as conn:
        if not conn.execute("SELECT to_regclass('public.zona')").fetchone()[0]:
            raise ValueError("Falta el esquema: aplica esquema.sql y las migraciones "
                             "antes de configurar roles.")
        conn.execute(Path(__file__).with_name("roles.sql").read_text(encoding="utf-8-sig"))
        for usuario, rol, _ in USUARIOS:
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (usuario,)).fetchone():
                conn.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(usuario)))
            conn.execute(sql.SQL("ALTER ROLE {} LOGIN INHERIT NOSUPERUSER NOCREATEDB "
                                 "NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}").format(
                                     sql.Identifier(usuario), sql.Literal(passwords[usuario])))
            conn.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(rol), sql.Identifier(usuario)))
        for _, rol, _ in USUARIOS:
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(db), sql.Identifier(rol)))
    print("Roles, usuarios y permisos configurados; transacción confirmada.")


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except psycopg.Error as exc:
        # No imprimir el SQL ni los detalles: podrían contener una contraseña.
        raise SystemExit(f"Configuración revertida. Error PostgreSQL "
                         f"{exc.sqlstate or 'de conexión'}; revisa la conexión, "
                         "los privilegios y la ejecución previa del esquema y 001.") from None
    except Exception:
        raise SystemExit("Configuración cancelada y revertida. Revisa conexión, variables, "
                         "privilegios del administrador y ejecución previa del esquema y 001.")