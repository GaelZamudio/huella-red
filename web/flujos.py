"""Flujos de negocio: rescates, animales y solicitudes de adopcion.
Se importa desde app.py. Estas rutas tienen prioridad sobre el listado generico /m/<slug>.
"""
from flask import abort, flash, redirect, render_template, request, url_for
import psycopg
from psycopg import sql

from app import TIPOS_INGRESO, app, conectar, login_requerido, msg

ESTADOS = ["rescatado", "en_atencion", "en_hogar_temporal", "disponible_adopcion", "adoptado", "fallecido"]
ESPECIES = ["perro", "gato", "otro"]


def leer(consulta, params=None):
    try:
        with conectar() as c:
            return c.execute(consulta, params or {}).fetchall()
    except psycopg.Error as e:
        flash(msg(e))
        return []


def ejecutar(accion, ok, destino):
    """Corre accion(c) en una transaccion: todo o nada. Muestra ok o el error de Postgres."""
    try:
        with conectar() as c:
            accion(c)
        flash(ok)
    except (psycopg.Error, ValueError, KeyError) as e:
        flash(msg(e))
    return redirect(destino)


def siguiente_id(c, tabla, col):  # un solo lugar para cambiar cuando haya ids autogenerados
    q = sql.SQL("SELECT COALESCE(MAX({}), 0) + 1 AS n FROM {}").format(
        sql.Identifier(col), sql.Identifier(tabla))
    return c.execute(q).fetchone()["n"]


def dia(x):
    return x.date() if hasattr(x, "date") else x


# ---------- Rescates ----------
@app.get("/m/rescate")
@login_requerido
def rescates():
    q, tipo = request.args.get("q", "").strip(), request.args.get("tipo", "")
    filas = leer("""
        SELECT r.id_rescate, r.fecha_hora, r.tipo_ingreso, r.descripcion_lugar, r.condicion_inicial,
               z.colonia || ', ' || z.municipio AS zona,
               (SELECT count(*) FROM animal a WHERE a.id_rescate = r.id_rescate) AS animales,
               (SELECT string_agg(p.nombres || ' ' || p.ap_paterno, ', ')
                  FROM rescate_rescatista rr JOIN persona p ON p.id_persona = rr.id_persona
                 WHERE rr.id_rescate = r.id_rescate) AS rescatistas
        FROM rescate r JOIN zona z USING (id_zona)
        WHERE (%(q)s = '' OR r.descripcion_lugar ILIKE %(like)s) AND (%(t)s = '' OR r.tipo_ingreso = %(t)s)
        ORDER BY r.fecha_hora DESC LIMIT 50""", {"q": q, "like": f"%{q}%", "t": tipo})
    return render_template("rescates.html", filas=filas, q=q, tipo=tipo, tipos=TIPOS_INGRESO)


# ---------- Animales ----------
@app.get("/m/animal")
@login_requerido
def animales():
    q, esp, est = (request.args.get(k, "").strip() for k in ("q", "especie", "estado"))
    filas = leer("""
        SELECT a.id_animal, a.nombre, a.especie, a.sexo, a.estado_actual, z.colonia,
               EXTRACT(YEAR FROM age(a.fecha_nacimiento_aprox))::int AS anios
        FROM animal a JOIN rescate r USING (id_rescate) JOIN zona z USING (id_zona)
        WHERE (%(q)s = '' OR a.nombre ILIKE %(like)s) AND (%(e)s = '' OR a.especie::text = %(e)s)
          AND (%(s)s = '' OR a.estado_actual = %(s)s)
        ORDER BY a.id_animal DESC LIMIT 60""", {"q": q, "like": f"%{q}%", "e": esp, "s": est})
    return render_template("animales.html", filas=filas, q=q, especie=esp, estado=est,
                           estados=ESTADOS, especies=ESPECIES)


@app.route("/m/animal/nuevo", methods=["GET", "POST"])
@login_requerido
def animal_nuevo():
    if request.method == "POST":
        f, nuevo = request.form, []

        def alta(c):
            n = siguiente_id(c, "animal", "id_animal")
            c.execute("INSERT INTO animal (id_animal, nombre, especie, sexo, fecha_nacimiento_aprox, "
                      "color, senas, id_rescate) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                      (n, f.get("nombre") or None, f["especie"], f["sexo"], f.get("nacimiento") or None,
                       f.get("color") or None, f.get("senas") or None, int(f["id_rescate"])))
            tri = {"si": True, "no": False}.get
            if f["especie"] == "perro":
                c.execute("INSERT INTO perro (id_animal, tamano, nivel_energia, apto_con_ninos) "
                          "VALUES (%s,%s,%s,%s)", (n, f["tamano"], f["energia"], f["apto_ninos"] == "si"))
            elif f["especie"] == "gato":
                c.execute("INSERT INTO gato (id_animal, resultado_fiv, resultado_felv) VALUES (%s,%s,%s)",
                          (n, tri(f.get("fiv")), tri(f.get("felv"))))
            else:
                c.execute("INSERT INTO otro (id_animal, descripcion_especie, cuidados_especiales) "
                          "VALUES (%s,%s,%s)", (n, f["descripcion_especie"], f.get("cuidados") or None))
            nuevo.append(n)
        resp = ejecutar(alta, "Animal registrado.", url_for("animal_nuevo"))
        return redirect(url_for("animal_ficha", id=nuevo[0])) if nuevo else resp
    rescates_ = leer("SELECT r.id_rescate, r.fecha_hora, z.colonia FROM rescate r "
                     "JOIN zona z USING (id_zona) ORDER BY r.id_rescate DESC")
    return render_template("animal_nuevo.html", rescates=rescates_, especies=ESPECIES)


@app.get("/m/animal/<int:id>")
@login_requerido
def animal_ficha(id):
    try:
        with conectar() as c:
            a = c.execute("""SELECT a.*, z.colonia, z.municipio, r.fecha_hora AS rescatado_en,
                       r.condicion_inicial, m.nombre AS madre
                FROM animal a JOIN rescate r USING (id_rescate) JOIN zona z USING (id_zona)
                LEFT JOIN animal m ON m.id_animal = a.id_madre WHERE a.id_animal = %s""", (id,)).fetchone()
            if not a:
                abort(404)
            sub = c.execute(sql.SQL("SELECT * FROM {} WHERE id_animal = %s").format(
                sql.Identifier(a["especie"])), (id,)).fetchone() or {}
            ev = [(a["rescatado_en"], "Rescatado", a["condicion_inicial"])]
            for e in c.execute("SELECT e.fecha_inicio, e.fecha_fin, e.motivo_salida, COALESCE(h.alias, h.calle) AS lugar "
                               "FROM estancia e JOIN hogar_temporal h USING (id_hogar) WHERE e.id_animal = %s", (id,)):
                ev.append((e["fecha_inicio"], "Llegó a hogar temporal", e["lugar"]))
                if e["fecha_fin"]:
                    ev.append((e["fecha_fin"], "Salió del hogar temporal", e["motivo_salida"]))
            for s in c.execute("SELECT s.fecha_solicitud, s.estado, p.nombres || ' ' || p.ap_paterno AS quien "
                               "FROM solicitud_adopcion s JOIN persona p USING (id_persona) WHERE s.id_animal = %s", (id,)):
                ev.append((s["fecha_solicitud"], f"Solicitud de adopción ({s['estado']})", s["quien"]))
            for d in c.execute("SELECT d.fecha_adopcion, d.fecha_devolucion, d.motivo_devolucion, "
                               "p.nombres || ' ' || p.ap_paterno AS quien FROM adopcion d "
                               "JOIN persona p USING (id_persona) WHERE d.id_animal = %s", (id,)):
                ev.append((d["fecha_adopcion"], "Adoptado", d["quien"]))
                if d["fecha_devolucion"]:
                    ev.append((d["fecha_devolucion"], "Devuelto", d["motivo_devolucion"]))
            for m in c.execute("SELECT fecha, tipo, observaciones FROM atencion_medica WHERE id_animal = %s", (id,)):
                ev.append((m["fecha"], "Atención: " + m["tipo"], m["observaciones"]))
    except psycopg.Error as e:
        flash(msg(e))
        return redirect(url_for("animales"))
    ev = sorted(((dia(f), t, d) for f, t, d in ev), key=lambda x: x[0], reverse=True)
    return render_template("animal_ficha.html", a=a, sub=sub, ev=ev, estados=ESTADOS)


@app.post("/m/animal/<int:id>/estado")
@login_requerido
def animal_estado(id):
    estado = request.form.get("estado", "")
    if estado not in ESTADOS:
        abort(400)
    return ejecutar(lambda c: c.execute("UPDATE animal SET estado_actual = %s WHERE id_animal = %s",
                                        (estado, id)), "Estado actualizado.", url_for("animal_ficha", id=id))


# ---------- Solicitudes de adopcion ----------
@app.get("/m/solicitud_adopcion")
@login_requerido
def solicitudes():
    est = request.args.get("estado", "")
    filas = leer("""
        SELECT s.id_animal, s.id_persona, s.fecha_solicitud, s.estado, s.observaciones,
               a.nombre AS animal, a.especie, p.nombres || ' ' || p.ap_paterno AS solicitante
        FROM solicitud_adopcion s JOIN animal a USING (id_animal) JOIN persona p ON p.id_persona = s.id_persona
        WHERE (%(s)s = '' OR s.estado = %(s)s)
        ORDER BY (s.estado = 'pendiente') DESC, s.fecha_solicitud DESC LIMIT 60""", {"s": est})
    animales_ = leer("SELECT id_animal, nombre FROM animal WHERE estado_actual = 'disponible_adopcion' ORDER BY nombre")
    adoptantes = leer("SELECT a.id_persona, p.nombres || ' ' || p.ap_paterno AS nombre "
                      "FROM adoptante a JOIN persona p USING (id_persona) ORDER BY nombre")
    return render_template("solicitudes.html", filas=filas, estado=est, animales=animales_, adoptantes=adoptantes)


@app.post("/m/solicitud_adopcion/nueva")
@login_requerido
def solicitud_nueva():
    f = request.form
    return ejecutar(lambda c: c.execute(
        "INSERT INTO solicitud_adopcion (id_animal, id_persona, observaciones) VALUES (%s,%s,%s)",
        (int(f["id_animal"]), int(f["id_persona"]), f.get("observaciones") or None)),
        "Solicitud registrada.", url_for("solicitudes"))


@app.post("/m/solicitud_adopcion/resolver")
@login_requerido
def solicitud_resolver():
    f = request.form
    animal_, persona, fecha, accion = int(f["id_animal"]), int(f["id_persona"]), f["fecha"], f["accion"]

    def resolver(c):
        nuevo = "aprobada" if accion == "aprobar" else "rechazada"
        if not c.execute("UPDATE solicitud_adopcion SET estado = %s WHERE id_animal = %s AND id_persona = %s "
                         "AND fecha_solicitud = %s AND estado = 'pendiente'", (nuevo, animal_, persona, fecha)).rowcount:
            raise ValueError("La solicitud ya fue resuelta.")
        if accion == "aprobar":  # aprobar = crear la adopcion, marcar adoptado y cerrar las demas
            c.execute("INSERT INTO adopcion (id_animal, id_persona, fecha_adopcion) VALUES (%s,%s,CURRENT_DATE)",
                      (animal_, persona))
            c.execute("UPDATE animal SET estado_actual = 'adoptado' WHERE id_animal = %s", (animal_,))
            c.execute("UPDATE solicitud_adopcion SET estado = 'rechazada' WHERE id_animal = %s "
                      "AND estado = 'pendiente'", (animal_,))
    return ejecutar(resolver, "Solicitud " + ("aprobada: adopción registrada." if accion == "aprobar"
                                                else "rechazada."), url_for("solicitudes"))
