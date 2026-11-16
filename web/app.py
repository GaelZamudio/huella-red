"""HuellaRed - web. El navegador pide, Flask responde, Postgres guarda.

Para agregar una pagina de listado: agrega una tupla a _P (abajo). Para un
formulario: copia rescate_nuevo() + su template y registralo en NUEVO.
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
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # detras de ngrok
app.config.update(
    SECRET_KEY=os.environ["SECRET_KEY"],
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "1") == "1",
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# Rol de la web = usuario de Postgres. La base impone los permisos reales.
ROLES = {r: {"db_user": os.environ[f"DB_USER_{r.upper()}"],
             "db_pass": os.environ[f"DB_PASS_{r.upper()}"],
             "login_pass": os.environ[f"LOGIN_PASS_{r.upper()}"]}
         for r in ("app", "consulta", "admin")}
ETIQUETAS = {"app": ("Operación", "Registra rescates, adopciones y atención médica."),
             "consulta": ("Consulta", "Solo lectura: listados y reportes."),
             "admin": ("Administración", "Control total, catálogos y configuración.")}

T, E, A = {"app", "consulta", "admin"}, {"app", "admin"}, {"admin"}
# slug, titulo, seccion, tabla (None = sin tabla aun), roles que la ven, pendiente
_P = [
 ("rescate", "Rescates", "Operación", "rescate", T, "Filtros por zona/fecha, ficha del rescate, asignar rescatistas."),
 ("animal", "Animales", "Operación", "animal", T, "Ficha con historial, cambio de estado, genealogía (id_madre), subtipo perro/gato/otro."),
 ("estancia", "Estancias", "Operación", "estancia", E, "Asignar animal a hogar, cerrar estancia con motivo de salida."),
 ("hogar_temporal", "Hogares temporales", "Operación", "hogar_temporal", T, "Alta/edición, capacidad vs. ocupación, especies aceptadas."),
 ("solicitud_adopcion", "Solicitudes", "Adopciones", "solicitud_adopcion", E, "Aprobar/rechazar, filtro por estado."),
 ("adopcion", "Adopciones", "Adopciones", "adopcion", T, "Registrar adopción y devolución con motivo."),
 ("seguimiento", "Seguimientos", "Adopciones", "seguimiento", E, "Programar y registrar seguimientos posadopción."),
 ("atencion_medica", "Atenciones", "Salud", "atencion_medica", T, "Alta de atención y detalle según tipo."),
 ("vacunacion", "Vacunación", "Salud", "vacunacion", E, "Aplicar dosis, calcular próxima dosis."),
 ("cirugia", "Cirugías", "Salud", "cirugia", E, "Registrar cirugía y complicaciones."),
 ("tratamiento", "Tratamientos", "Salud", "tratamiento", E, "Diagnóstico y duración."),
 ("clinica", "Clínicas", "Salud", "clinica", T, "CRUD de clínicas."),
 ("vacuna", "Catálogo de vacunas", "Salud", "vacuna", T, "CRUD de catálogo."),
 ("persona", "Personas", "Personas", "persona", T, "Alta y edición; roles de la persona."),
 ("rescatista", "Rescatistas", "Personas", "rescatista", T, "Disponibilidad y rescates realizados."),
 ("adoptante", "Adoptantes", "Personas", "adoptante", T, "Perfil de vivienda e historial."),
 ("veterinario", "Veterinarios", "Personas", "veterinario", T, "Cédula y atenciones."),
 ("zona", "Zonas", "Catálogos", "zona", E, "CRUD de zonas."),
 ("reportes", "Reportes", "Análisis", None, T, "Consultas del álgebra (práctica 6-8) como reportes con filtros y exportar CSV."),
 ("usuarios", "Usuarios y roles", "Administración", None, A, "Tabla de cuentas con contraseña hasheada; migración nueva."),
 ("auditoria", "Auditoría", "Administración", None, A, "Bitácora de cambios (quién, qué, cuándo)."),
 ("configuracion", "Configuración", "Administración", None, A, "Parámetros del sistema."),
]
PAGINAS = {s: dict(slug=s, titulo=t, seccion=sec, tabla=tb, roles=r, pendiente=p)
           for s, t, sec, tb, r, p in _P}
NUEVO = {"rescate": "rescate_nuevo"}  # slug -> endpoint del formulario
TIPOS_INGRESO = ["rescate_en_calle", "reporte_ciudadano", "entrega_voluntaria"]
CONTADORES = [("Animales en cuidado", "animal", "estado_actual NOT IN ('adoptado','fallecido')"),
              ("Rescates registrados", "rescate", ""),
              ("Solicitudes pendientes", "solicitud_adopcion", "estado = 'pendiente'"),
              ("Adopciones vigentes", "adopcion", "fecha_devolucion IS NULL"),
              ("Hogares activos", "hogar_temporal", "activo")]


def conectar():
    r = ROLES[session["rol"]]
    return psycopg.connect(
        host=os.getenv("DB_HOST", "db"), port=os.getenv("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"], user=r["db_user"], password=r["db_pass"],
        row_factory=dict_row)


def msg(e):
    return getattr(getattr(e, "diag", None), "message_primary", None) or str(e)


def login_requerido(f):
    @wraps(f)
    def interno(*a, **k):
        if "rol" not in session:
            return redirect(url_for("login"))
        return f(*a, **k)
    return interno


@app.before_request
def verificar_csrf():
    if request.method == "POST" and not hmac.compare_digest(
            request.form.get("_csrf", ""), session.get("_csrf", "")):
        abort(400)


@app.context_processor
def contexto():
    session.setdefault("_csrf", secrets.token_hex(16))
    rol, menu = session.get("rol"), {}
    if rol:
        for p in PAGINAS.values():
            if rol in p["roles"]:
                menu.setdefault(p["seccion"], []).append(p)
    return {"csrf": session["_csrf"], "rol": rol, "menu": menu,
            "rol_nombre": ETIQUETAS[rol][0] if rol else None,
            "dev": os.getenv("MODO_DESARROLLO", "0") == "1"}


@app.errorhandler(403)
@app.errorhandler(404)
def error(e):
    texto = {403: "Tu rol no tiene acceso a esta sección.", 404: "No encontramos esa página."}
    return render_template("error.html", codigo=e.code, texto=texto[e.code]), e.code


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        rol, clave = request.form.get("rol", ""), request.form.get("password", "")
        if rol in ROLES and hmac.compare_digest(clave, ROLES[rol]["login_pass"]):
            session["rol"] = rol
            return redirect(url_for("panel"))
        flash("Rol o contraseña incorrectos.")
    return render_template("login.html", roles=ETIQUETAS)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_requerido
def inicio():
    return redirect(url_for("panel"))


@app.get("/panel")
@login_requerido
def panel():
    cifras, recientes = [], []
    try:
        with conectar() as c:
            for nombre, tabla, cond in CONTADORES:
                q = sql.SQL("SELECT count(*) AS n FROM {}{}").format(
                    sql.Identifier(tabla), sql.SQL(f" WHERE {cond}" if cond else ""))
                cifras.append((nombre, c.execute(q).fetchone()["n"]))
            recientes = c.execute(
                "SELECT r.id_rescate, r.fecha_hora, r.tipo_ingreso, z.colonia, z.municipio "
                "FROM rescate r JOIN zona z USING (id_zona) "
                "ORDER BY r.fecha_hora DESC LIMIT 5").fetchall()
    except psycopg.Error as e:
        flash(msg(e))
    return render_template("panel.html", cifras=cifras, recientes=recientes)


@app.get("/m/<slug>")
@login_requerido
def modulo(slug):
    p = PAGINAS.get(slug) or abort(404)
    if session["rol"] not in p["roles"]:
        abort(403)
    filas = []
    if p["tabla"]:
        try:
            with conectar() as c:
                filas = c.execute(sql.SQL("SELECT * FROM {} ORDER BY 1 DESC LIMIT 50").format(
                    sql.Identifier(p["tabla"]))).fetchall()
        except psycopg.Error as e:
            flash(msg(e))
    return render_template("modulo.html", p=p, filas=filas, nuevo=NUEVO.get(slug))


@app.route("/rescate/nuevo", methods=["GET", "POST"])
@login_requerido
def rescate_nuevo():
    with conectar() as c:
        zonas = c.execute("SELECT id_zona, colonia, municipio FROM zona "
                          "ORDER BY municipio, colonia").fetchall()
        rescatistas = c.execute(
            "SELECT r.id_persona, p.nombres || ' ' || p.ap_paterno AS nombre "
            "FROM rescatista r JOIN persona p USING (id_persona) ORDER BY nombre").fetchall()
        if request.method == "POST":
            f = request.form
            try:
                # Los id no son automaticos en el esquema: se calculan aqui.
                nuevo = c.execute("SELECT COALESCE(MAX(id_rescate), 0) + 1 AS id "
                                  "FROM rescate").fetchone()["id"]
                c.execute("INSERT INTO rescate (id_rescate, descripcion_lugar, fecha_hora, "
                          "condicion_inicial, tipo_ingreso, id_zona) VALUES (%s,%s,%s,%s,%s,%s)",
                          (nuevo, f["descripcion_lugar"], f["fecha_hora"],
                           f["condicion_inicial"], f["tipo_ingreso"], int(f["id_zona"])))
                for p in f.getlist("rescatistas"):
                    c.execute("INSERT INTO rescate_rescatista (id_rescate, id_persona) "
                              "VALUES (%s, %s)", (nuevo, int(p)))
            except (psycopg.Error, ValueError, KeyError) as e:
                c.rollback()  # todo o nada
                flash(msg(e))
            else:
                flash(f"Rescate #{nuevo} registrado.")
                return redirect(url_for("modulo", slug="rescate"))
    return render_template("rescate_nuevo.html", zonas=zonas, rescatistas=rescatistas,
                           tipos=TIPOS_INGRESO, v=request.form)
