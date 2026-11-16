"""HuellaRed - demo web. El navegador pide, Flask responde, Postgres guarda.

Para agregar un formulario nuevo: copia rescate_nuevo() y su template, cambia
las tablas/columnas y registra la tabla en TABLAS para verla en /tabla/<nombre>.
"""
import hmac
import os
import secrets
from functools import wraps

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # detrás de ngrok
app.config.update(
    SECRET_KEY=os.environ["SECRET_KEY"],
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "1") == "1",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# Un rol de la web = un usuario de Postgres. La BD es la que impone los permisos.
ROLES = {
    r: {
        "db_user": os.environ[f"DB_USER_{r.upper()}"],
        "db_pass": os.environ[f"DB_PASS_{r.upper()}"],
        "login_pass": os.environ[f"LOGIN_PASS_{r.upper()}"],
    }
    for r in ("app", "consulta", "admin")
}

# Tablas visibles en /tabla/<nombre> -> columna para ordenar (más reciente primero).
TABLAS = {
    "rescate": "id_rescate", "rescate_rescatista": "id_rescate",
    "animal": "id_animal", "zona": "id_zona", "persona": "id_persona",
    "rescatista": "id_persona", "adoptante": "id_persona",
    "solicitud_adopcion": "fecha_solicitud", "adopcion": "fecha_adopcion",
}
TIPOS_INGRESO = ["rescate_en_calle", "reporte_ciudadano", "entrega_voluntaria"]


def conectar():
    r = ROLES[session["rol"]]
    return psycopg.connect(
        host=os.getenv("DB_HOST", "db"), port=os.getenv("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"], user=r["db_user"], password=r["db_pass"],
        row_factory=dict_row,
    )


def login_requerido(f):
    @wraps(f)
    def interno(*a, **k):
        if "rol" not in session:
            return redirect(url_for("login"))
        return f(*a, **k)
    return interno


@app.before_request
def verificar_csrf():
    if request.method == "POST":
        enviado = request.form.get("_csrf", "")
        esperado = session.get("_csrf", "")
        if not esperado or not hmac.compare_digest(enviado.encode(), esperado.encode()):
            abort(400)


@app.context_processor
def contexto():
    session.setdefault("_csrf", secrets.token_hex(16))
    return {"csrf": session["_csrf"], "rol": session.get("rol")}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        rol = request.form.get("rol", "")
        clave = request.form.get("password", "")
        if rol in ROLES and hmac.compare_digest(clave.encode(), ROLES[rol]["login_pass"].encode()):
            session["rol"] = rol
            return redirect(url_for("inicio"))
        flash("Rol o contraseña incorrectos.")
    return render_template("login.html", roles=list(ROLES))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_requerido
def inicio():
    return redirect(url_for("ver_tabla", nombre="rescate"))


@app.get("/tabla/<nombre>")
@login_requerido
def ver_tabla(nombre):
    if nombre not in TABLAS:  # lista blanca: nunca armar SQL con texto del usuario
        abort(404)
    consulta = sql.SQL("SELECT * FROM {} ORDER BY {} DESC LIMIT 20").format(
        sql.Identifier(nombre), sql.Identifier(TABLAS[nombre]))
    try:
        with conectar() as c:
            filas = c.execute(consulta).fetchall()
    except psycopg.Error as e:
        flash(e.diag.message_primary or str(e))
        filas = []
    return render_template("tabla.html", nombre=nombre, filas=filas, tablas=TABLAS)


@app.route("/rescate/nuevo", methods=["GET", "POST"])
@login_requerido
def rescate_nuevo():
    with conectar() as c:
        zonas = c.execute("SELECT id_zona, colonia, municipio FROM zona "
                          "ORDER BY municipio, colonia").fetchall()
        rescatistas = c.execute(
            "SELECT r.id_persona, p.nombres || ' ' || p.ap_paterno AS nombre "
            "FROM rescatista r JOIN persona p USING (id_persona) ORDER BY nombre"
        ).fetchall()
        if request.method == "POST":
            f = request.form
            try:
                # Los id no son automáticos en el esquema: se calculan aquí.
                nuevo = c.execute("SELECT COALESCE(MAX(id_rescate), 0) + 1 AS id "
                                  "FROM rescate").fetchone()["id"]
                c.execute(
                    "INSERT INTO rescate (id_rescate, descripcion_lugar, fecha_hora, "
                    "condicion_inicial, tipo_ingreso, id_zona) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (nuevo, f["descripcion_lugar"], f["fecha_hora"],
                     f["condicion_inicial"], f["tipo_ingreso"], int(f["id_zona"])))
                for p in f.getlist("rescatistas"):
                    c.execute("INSERT INTO rescate_rescatista (id_rescate, id_persona) "
                              "VALUES (%s, %s)", (nuevo, int(p)))
            except (psycopg.Error, ValueError, KeyError) as e:
                c.rollback()  # todo o nada: ni rescate ni rescatistas
                flash(getattr(getattr(e, "diag", None), "message_primary", None) or str(e))
            else:
                flash(f"Rescate #{nuevo} registrado.")
                return redirect(url_for("ver_tabla", nombre="rescate"))
    return render_template("rescate_nuevo.html", zonas=zonas,
                           rescatistas=rescatistas, tipos=TIPOS_INGRESO, v=request.form)
