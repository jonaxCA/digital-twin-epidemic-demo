"""
EPIDEMIA -- Sistema Monolitico v0.1 (Flask + Jinja2 + PostgreSQL).

Primera version funcional del monolito, correspondiente al Primer Avance.

Recorrido funcional actual:
    dashboard publico (sin login) -> login -> dashboard autenticado -> mapa
    -> monitoreo -> captura de caso

Alcance de esta version:
    - Pantallas funcionales: dashboard publico, login, dashboard autenticado,
      mapa, monitoreo, catalogo de enfermedades, captura de casos, usuarios y
      auditoria. Simulaciones y Comparacion siguen como stub "Proximamente";
      el motor de simulacion y la frontera de Pareto ya existen en el paquete
      motor/, pendientes de conectarse a esas pantallas.
    - Todo corre en un solo proceso Flask contra PostgreSQL directamente
      (sin la capa de microservicios -- eso es alcance del segundo parcial).
    - Mapa acotado a Nuevo Leon.
"""
import csv
import io
import os
from datetime import date, datetime, timezone

from flask import (Flask, render_template, request, redirect, url_for,
                   make_response, g, flash)

import bcrypt

import queries
from audit import log_audit
from auth import (attempt_login, create_token, login_required, admin_required,
                  roles_required, tiene_rol, get_current_user, COOKIE_NAME)

app = Flask(__name__)
# flash() necesita firmar la cookie de sesion. Se reutiliza el mismo secreto
# del JWT para no introducir otra variable de entorno.
app.secret_key = os.environ.get("JWT_SECRET_KEY", "dev-secret-cambiar-en-despliegue")

STUB_ITEMS = {
    "simulaciones": "Simulaciones",
    "comparacion": "Comparación",
}

# El catalogo es chico por naturaleza; el export no pagina, baja todo lo que
# pase el filtro de la pantalla.
EXPORT_MAX_FILAS = 1000


@app.context_processor
def inject_globals():
    user = get_current_user()
    return {
        "current_user": user,
        "now": datetime.now(timezone.utc),
        "es_admin": tiene_rol(user, "ADMINISTRADOR"),
        # Quien puede fijar los parametros epidemiologicos del catalogo. Es
        # solo para mostrar u ocultar botones: el control real esta en
        # roles_required, en cada ruta.
        "puede_editar_catalogo": tiene_rol(user, "EPIDEMIOLOGO", "ADMINISTRADOR"),
    }


# ---------------------------------------------------------------------------
# 1. Dashboard publico -- sin login
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard_publico():
    if get_current_user():
        return redirect(url_for("dashboard"))
    indicadores = queries.get_resumen_indicadores()
    situacion = queries.get_resumen_situacion()
    curva = queries.get_curva_epidemica(30)
    return render_template(
        "dashboard_publico.html",
        indicadores=indicadores,
        situacion=situacion,
        curva=curva,
        report_link=url_for("login"),
    )


# ---------------------------------------------------------------------------
# 2. Login
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if get_current_user():
            return redirect(url_for("dashboard"))
        return render_template("login.html", error=None, usuario="")

    usuario = (request.form.get("usuario") or "").strip()
    password = request.form.get("password") or ""
    user, error = attempt_login(usuario, password)
    if error:
        log_audit(None, "LOGIN_FAILED", "users", entity_id=usuario)
        return render_template("login.html", error=error, usuario=usuario), 401

    log_audit(user["id"], "LOGIN", "users", entity_id=str(user["id"]))
    token = create_token(user)
    next_url = request.args.get("next") or url_for("dashboard")
    resp = make_response(redirect(next_url))
    resp.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="Lax", max_age=60 * 60 * 8
    )
    return resp


@app.route("/logout")
def logout():
    user = get_current_user()
    if user:
        log_audit(user["sub"], "LOGOUT", "users", entity_id=str(user["sub"]))
    resp = make_response(redirect(url_for("dashboard_publico")))
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ---------------------------------------------------------------------------
# 3. Dashboard autenticado
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    indicadores = queries.get_resumen_indicadores()
    situacion = queries.get_resumen_situacion()
    curva = queries.get_curva_epidemica(30)
    return render_template(
        "dashboard.html",
        indicadores=indicadores,
        situacion=situacion,
        curva=curva,
        active_nav="dashboard",
        report_link=url_for("export_resumen_csv"),
    )


# ---------------------------------------------------------------------------
# 4. Mapa epidemiologico -- Nuevo Leon
# ---------------------------------------------------------------------------
@app.route("/mapa")
@login_required
def mapa():
    dias = request.args.get("dias", default=30, type=int)
    disease_id = request.args.get("enfermedad", default=None, type=int)
    if dias not in (7, 30, 60):
        dias = 30

    municipios = queries.get_mapa_municipios(disease_id=disease_id, dias=dias)
    for m in municipios:
        m["tendencia"] = queries.get_tendencia_zona(m["id"], disease_id=disease_id, dias=14)
    enfermedades = queries.get_enfermedades_catalogo()

    return render_template(
        "mapa.html",
        municipios=municipios,
        enfermedades=enfermedades,
        dias=dias,
        disease_id=disease_id,
        active_nav="mapa",
    )


@app.route("/api/mapa")
@login_required
def api_mapa():
    dias = request.args.get("dias", default=30, type=int)
    disease_id = request.args.get("enfermedad", default=None, type=int)
    if dias not in (7, 30, 60):
        dias = 30
    municipios = queries.get_mapa_municipios(disease_id=disease_id, dias=dias)
    for m in municipios:
        m["tendencia"] = queries.get_tendencia_zona(m["id"], disease_id=disease_id, dias=14)
    # `serie` alimenta la linea de tiempo: mismo corte y misma ventana movil que
    # `municipios`, asi que su ultimo cuadro es identico al mapa estatico.
    serie = queries.get_mapa_serie_temporal(disease_id=disease_id, dias=dias)
    return {"municipios": municipios, "serie": serie}


@app.route("/reportes/nuevo", methods=["GET", "POST"])
@login_required
def reporte_nuevo():
    """Captura de un caso epidemiologico -- el "+ Nuevo Reporte" del dashboard.

    Abierta a cualquier usuario autenticado: capturar es justamente el trabajo
    de campo del EPIDEMIOLOGO, no del administrador. El reporte queda firmado
    con `reported_by` y ademas deja un CREATE en audit_log.

    Nota de alcance: con esto `cases` deja de ser de solo lectura, que era una
    restriccion explicita del proyecto. Es el unico camino de escritura hacia
    esa tabla y solo inserta -- no edita ni borra casos existentes.
    """
    catalogos = {
        "enfermedades": queries.get_enfermedades_para_captura(),
        "municipios": queries.get_municipios_catalogo(),
        "sexos": queries.SEXOS,
        "resultados": queries.RESULTADOS,
        "severidades": queries.SEVERIDADES,
        "hoy": date.today().isoformat(),
    }

    if request.method == "GET":
        return render_template("reporte_form.html", catalogos=catalogos,
                               form={}, errores=[], active_nav="dashboard")

    datos, errores = queries.valida_caso(request.form)
    if errores:
        return render_template("reporte_form.html", catalogos=catalogos,
                               form=request.form, errores=errores,
                               active_nav="dashboard"), 400

    nuevo_id, error = queries.crear_caso(datos, g.user["sub"])
    if error:
        return render_template("reporte_form.html", catalogos=catalogos,
                               form=request.form, errores=[error],
                               active_nav="dashboard"), 400

    caso = queries.get_caso(nuevo_id)
    log_audit(g.user["sub"], "CREATE", "cases", entity_id=str(nuevo_id),
              data_after=dict(caso))
    flash(f"Reporte #{nuevo_id} capturado: {caso['enfermedad']} en "
          f"{caso['municipio']}, {caso['report_date']}. Queda pendiente de validación.", "ok")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# 5. Catalogo de enfermedades
# ---------------------------------------------------------------------------
def _filtros_enfermedades(args):
    """Normaliza los filtros de la pantalla. Lo comparten la vista y el export
    para que el CSV baje exactamente lo que se esta viendo.

    Un estado fuera del dominio se descarta en vez de llegar a la consulta: el
    filtro se arma concatenando fragmentos de WHERE, asi que solo pasan claves
    conocidas.
    """
    estado = args.get("estado") or ""
    return {
        "busqueda": (args.get("q") or "").strip(),
        "estado": estado if estado in ("activa", "inactiva") else "",
    }


def _filtros_url(filtros):
    """Los mismos filtros con el nombre que llevan en la URL, sin los vacios,
    para reinyectarlos en los links de paginado y de export."""
    nombres = {"busqueda": "q", "estado": "estado"}
    return {nombres[k]: v for k, v in filtros.items() if v}


@app.route("/enfermedades")
@login_required
def enfermedades():
    filtros = _filtros_enfermedades(request.args)
    pagina = request.args.get("pagina", default=1, type=int)
    return render_template(
        "enfermedades.html",
        stats=queries.get_enfermedades_stats(),
        listado=queries.get_enfermedades(pagina=pagina, **filtros),
        filtros=filtros,
        filtros_url=_filtros_url(filtros),
        active_nav="enfermedades",
    )


@app.route("/enfermedades/nueva", methods=["GET", "POST"])
@login_required
def enfermedad_nueva():
    """Alta en el catalogo de enfermedades.

    Abierta a cualquier usuario autenticado, no solo al administrador: quien
    detecta un padecimiento que no esta en el catalogo es la gente de campo.
    Queda registrada en audit_log con el usuario que la dio de alta, que es lo
    que hace aceptable abrirla.

    Nota de alcance: este es el segundo camino de escritura de la app (el
    primero es el CRUD de usuarios) y el unico que toca una tabla del dominio
    epidemiologico. Los casos, escenarios y simulaciones siguen siendo de solo
    lectura.
    """
    if request.method == "GET":
        return render_template("enfermedad_form.html", enfermedad=None,
                               parametros=queries.estado_parametros({}),
                               errores=[], active_nav="enfermedades")

    datos = {
        "code": queries.normaliza_codigo(request.form.get("code")),
        "name": (request.form.get("name") or "").strip(),
        "description": (request.form.get("description") or "").strip(),
    }
    params, errores = queries.parametros_desde_form(request.form)
    errores = queries.valida_enfermedad(datos["code"], datos["name"]) + errores

    if errores:
        return render_template("enfermedad_form.html", enfermedad=datos,
                               parametros=queries.estado_parametros(params),
                               errores=errores, active_nav="enfermedades"), 400

    nuevo_id, error = queries.crear_enfermedad(
        datos["code"], datos["name"], datos["description"], params)
    if error:
        return render_template("enfermedad_form.html", enfermedad=datos,
                               parametros=queries.estado_parametros(params),
                               errores=[error], active_nav="enfermedades"), 400

    log_audit(g.user["sub"], "CREATE", "diseases", entity_id=str(nuevo_id),
              data_after=_snapshot_enfermedad(queries.get_enfermedad(nuevo_id)))
    flash(f"Enfermedad «{datos['name']}» registrada con el código {datos['code']}.", "ok")
    return redirect(url_for("enfermedades"))


def _snapshot_enfermedad(e):
    """Lo que se guarda en audit_log. created_at no viaja: no cambia nunca y
    json no serializa datetime sin ayuda."""
    if not e:
        return None
    return {"id": e["id"], "code": e["code"], "name": e["name"],
            "description": e["description"], "is_active": e["is_active"],
            "default_params": e["default_params"]}


@app.route("/enfermedades/<int:disease_id>/editar", methods=["GET", "POST"])
@roles_required("EPIDEMIOLOGO", "ADMINISTRADOR")
def enfermedad_editar(disease_id):
    """Edicion del catalogo, incluidos los parametros que consume el motor.

    Restringida a EPIDEMIOLOGO y ADMINISTRADOR: el alta la puede hacer
    cualquiera (quien detecta un padecimiento nuevo es la gente de campo), pero
    fijar R0 o la letalidad es una decision tecnica con consecuencias en cada
    simulacion que se corra despues.

    El codigo no se edita: es la llave natural con la que ya estan ligados los
    casos y los escenarios.
    """
    actual = queries.get_enfermedad(disease_id)
    if not actual:
        flash("Esa enfermedad ya no existe en el catálogo.", "error")
        return redirect(url_for("enfermedades"))

    if request.method == "GET":
        return render_template("enfermedad_form.html", enfermedad=actual,
                               parametros=queries.estado_parametros(actual["default_params"]),
                               errores=[], active_nav="enfermedades")

    datos = {
        "code": actual["code"],
        "name": (request.form.get("name") or "").strip(),
        "description": (request.form.get("description") or "").strip(),
    }
    params, errores = queries.parametros_desde_form(request.form, actual["default_params"])
    errores = queries.valida_enfermedad(datos["code"], datos["name"]) + errores

    if errores:
        return render_template("enfermedad_form.html",
                               enfermedad={**actual, **datos},
                               parametros=queries.estado_parametros(params),
                               errores=errores, active_nav="enfermedades"), 400

    antes = _snapshot_enfermedad(actual)
    ok, error = queries.actualiza_enfermedad(
        disease_id, datos["name"], datos["description"], params)
    if not ok:
        return render_template("enfermedad_form.html",
                               enfermedad={**actual, **datos},
                               parametros=queries.estado_parametros(params),
                               errores=[error], active_nav="enfermedades"), 400

    log_audit(g.user["sub"], "UPDATE", "diseases", entity_id=str(disease_id),
              data_before=antes,
              data_after=_snapshot_enfermedad(queries.get_enfermedad(disease_id)))
    flash(f"«{datos['name']}» actualizada.", "ok")
    return redirect(url_for("enfermedades"))


@app.route("/enfermedades/<int:disease_id>/estado", methods=["POST"])
@roles_required("EPIDEMIOLOGO", "ADMINISTRADOR")
def enfermedad_estado(disease_id):
    """Baja y alta logica del catalogo. Nunca borra: los casos capturados
    apuntan a la enfermedad con ON DELETE RESTRICT."""
    actual = queries.get_enfermedad(disease_id)
    if not actual:
        flash("Esa enfermedad ya no existe en el catálogo.", "error")
        return redirect(url_for("enfermedades"))

    activa = request.form.get("activa") == "1"
    queries.set_enfermedad_activa(disease_id, activa)
    log_audit(g.user["sub"], "UPDATE", "diseases", entity_id=str(disease_id),
              data_before=_snapshot_enfermedad(actual),
              data_after=_snapshot_enfermedad(queries.get_enfermedad(disease_id)))
    flash(f"«{actual['name']}» quedó {'activa' if activa else 'inactiva'} en el catálogo.", "ok")
    return redirect(request.referrer or url_for("enfermedades"))


@app.route("/export/enfermedades.csv")
@login_required
def export_enfermedades_csv():
    filtros = _filtros_enfermedades(request.args)
    listado = queries.get_enfermedades(pagina=1, por_pagina=EXPORT_MAX_FILAS, **filtros)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Código", "Enfermedad", "Estado", "Actividad", "Alta en catálogo",
                     "Casos NL (total)", "Casos NL (30 días)",
                     "Simulable", "Parámetros faltantes", "Parámetros supuestos"])
    for e in listado["enfermedades"]:
        p = e["parametros"]
        writer.writerow([e["code"], e["nombre"], e["estado_label"],
                         e["actividad"]["label"], e["alta_label"],
                         e["casos_total"], e["casos_30d"],
                         "Sí" if p["simulable"] else "No",
                         len(p["faltan"]), len(p["supuestos"])])
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=catalogo_enfermedades.csv"
    return resp


# ---------------------------------------------------------------------------
# Extras chicos pero reales: exportar CSV, y stubs para el resto del sidebar
# ---------------------------------------------------------------------------
@app.route("/export/resumen.csv")
@login_required
def export_resumen_csv():
    log_audit(g.user["sub"], "EXPORT", "reports", entity_id="resumen_situacion")
    situacion = queries.get_resumen_situacion(limit=20)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Enfermedad", "Estado", "Casos (7 dias)"])
    for row in situacion:
        writer.writerow([row["enfermedad"], row["estado"], row["incidencia"]])
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=resumen_situacion.csv"
    return resp


# ---------------------------------------------------------------------------
# 6. Monitoreo -- analisis epidemiologico
# ---------------------------------------------------------------------------
INDICADORES = {"incidencia": "Incidencia / 100k", "casos": "Casos confirmados"}
PERIODOS = (7, 30, 90)


def _filtros_monitoreo(args):
    """Normaliza los filtros de Monitoreo. Igual que en Enfermedades, lo que no
    pertenece al dominio se descarta antes de llegar a la consulta."""
    indicador = args.get("indicador") or ""
    dias = args.get("dias", type=int)
    return {
        "disease_id": args.get("enfermedad", type=int),
        "region_id": args.get("municipio", type=int),
        "dias": dias if dias in PERIODOS else 30,
        "indicador": indicador if indicador in INDICADORES else "incidencia",
        "busqueda": (args.get("q") or "").strip(),
    }


def _monitoreo_url(filtros):
    nombres = {"disease_id": "enfermedad", "region_id": "municipio",
               "dias": "dias", "indicador": "indicador", "busqueda": "q"}
    return {nombres[k]: v for k, v in filtros.items() if v}


@app.route("/monitoreo")
@login_required
def monitoreo():
    f = _filtros_monitoreo(request.args)
    pagina = request.args.get("pagina", default=1, type=int)
    ambito = {"disease_id": f["disease_id"], "region_id": f["region_id"], "dias": f["dias"]}

    serie = queries.get_monitoreo_serie(**ambito)
    edades = queries.get_monitoreo_edad(**ambito)
    sexos = queries.get_monitoreo_sexo(**ambito)
    totales = queries.get_monitoreo_totales(**ambito)
    zonas = queries.get_monitoreo_zonas(busqueda=f["busqueda"] or None,
                                        orden=f["indicador"], pagina=pagina, **ambito)

    return render_template(
        "monitoreo.html",
        serie=serie,
        edades=edades,
        sexos=sexos,
        totales=totales,
        zonas=zonas,
        insights=queries.get_monitoreo_insights(zonas["zonas"], edades, totales, f["dias"]),
        enfermedades=queries.get_enfermedades_catalogo(),
        municipios=queries.get_municipios_catalogo(),
        indicadores=INDICADORES,
        periodos=PERIODOS,
        filtros=f,
        filtros_url=_monitoreo_url(f),
        active_nav="monitoreo",
    )


@app.route("/export/monitoreo.csv")
@login_required
def export_monitoreo_csv():
    f = _filtros_monitoreo(request.args)
    log_audit(g.user["sub"], "EXPORT", "reports", entity_id="monitoreo_zonas")
    zonas = queries.get_monitoreo_zonas(
        disease_id=f["disease_id"], region_id=f["region_id"], dias=f["dias"],
        busqueda=f["busqueda"] or None, orden=f["indicador"],
        pagina=1, por_pagina=EXPORT_MAX_FILAS,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Zona", f"Casos ({f['dias']} días)", "Incidencia / 100k",
                     "Variación 7d (%)", "Graves", "Estado"])
    for z in zonas["zonas"]:
        writer.writerow([z["zona"], z["casos"], z["incidencia"], z["variacion"],
                         z["graves"], z["estado"]])
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=monitoreo_zonas.csv"
    return resp


# ---------------------------------------------------------------------------
# 7. Usuarios y Auditoria -- adaptadas del diseno de la companera, con datos
#    reales de Postgres (ver notas de alcance en queries.py)
# ---------------------------------------------------------------------------
@app.route("/usuarios")
@admin_required
def usuarios():
    busqueda = request.args.get("q") or None
    rol_id = request.args.get("rol", type=int)
    estado = request.args.get("estado") or None

    resumen = queries.get_usuarios_resumen()
    roles = queries.get_roles_catalogo()
    lista = queries.get_usuarios_lista(busqueda=busqueda, rol_id=rol_id, estado=estado)

    return render_template(
        "usuarios.html",
        resumen=resumen,
        roles=roles,
        usuarios=lista,
        filtro_q=busqueda or "",
        filtro_rol=rol_id,
        filtro_estado=estado,
        active_nav="usuarios",
    )


# ---------------------------------------------------------------------------
# CRUD de usuarios -- solo ADMINISTRADOR (admin_required)
# ---------------------------------------------------------------------------
# Cada operacion queda en audit_log con el estado antes/despues.

def _hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def _snapshot(u):
    """Lo que se guarda en audit_log. Nunca incluye password_hash."""
    if not u:
        return None
    return {
        "id": u["id"],
        "username": u["username"],
        "email": u["email"],
        "full_name": u["full_name"],
        "is_active": u["is_active"],
        "role_id": u.get("role_id"),
    }


@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@admin_required
def usuario_nuevo():
    roles = queries.get_roles_catalogo()
    if request.method == "GET":
        return render_template("usuario_form.html", roles=roles, usuario=None,
                               errores=[], active_nav="usuarios")

    datos = {
        "username": (request.form.get("username") or "").strip(),
        "email": (request.form.get("email") or "").strip(),
        "full_name": (request.form.get("full_name") or "").strip(),
        "is_active": request.form.get("is_active") == "on",
    }
    password = request.form.get("password") or ""
    role_id = request.form.get("role_id", type=int)

    errores = queries.valida_usuario(datos["username"], datos["email"],
                                     datos["full_name"], es_alta=True,
                                     password=password)
    if not role_id:
        errores.append("Selecciona un rol.")
    if errores:
        return render_template("usuario_form.html", roles=roles, usuario=datos,
                               errores=errores, active_nav="usuarios"), 400

    nuevo_id, error = queries.crear_usuario(
        datos["username"], datos["email"], datos["full_name"],
        _hash_password(password), role_id, datos["is_active"],
    )
    if error:
        return render_template("usuario_form.html", roles=roles, usuario=datos,
                               errores=[error], active_nav="usuarios"), 400

    log_audit(g.user["sub"], "CREATE", "users", entity_id=str(nuevo_id),
              data_after=_snapshot(queries.get_usuario(nuevo_id)))
    flash(f"Usuario '{datos['username'].lower()}' creado.", "ok")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:user_id>/editar", methods=["GET", "POST"])
@admin_required
def usuario_editar(user_id):
    actual = queries.get_usuario(user_id)
    if not actual:
        flash("Ese usuario ya no existe.", "error")
        return redirect(url_for("usuarios"))

    roles = queries.get_roles_catalogo()
    if request.method == "GET":
        return render_template("usuario_form.html", roles=roles, usuario=actual,
                               errores=[], active_nav="usuarios")

    datos = {
        "id": user_id,
        "username": actual["username"],   # el username no se edita
        "email": (request.form.get("email") or "").strip(),
        "full_name": (request.form.get("full_name") or "").strip(),
        "is_active": request.form.get("is_active") == "on",
    }
    password = request.form.get("password") or ""
    role_id = request.form.get("role_id", type=int)

    errores = queries.valida_usuario(datos["username"], datos["email"],
                                     datos["full_name"], es_alta=False,
                                     password=password)
    if not role_id:
        errores.append("Selecciona un rol.")

    # No dejar que el admin se quite a si mismo el acceso.
    if user_id == g.user["sub"] and not datos["is_active"]:
        errores.append("No puedes desactivar tu propia cuenta.")
    if user_id == g.user["sub"]:
        rol_admin = next((r for r in roles if r["code"] == "ADMINISTRADOR"), None)
        if rol_admin and role_id != rol_admin["id"]:
            errores.append("No puedes quitarte a ti mismo el rol de administrador.")

    if errores:
        vista = {**actual, **datos, "role_id": role_id}
        return render_template("usuario_form.html", roles=roles, usuario=vista,
                               errores=errores, active_nav="usuarios"), 400

    antes = _snapshot(actual)
    ok, error = queries.actualizar_usuario(
        user_id, datos["email"], datos["full_name"], datos["is_active"], role_id,
        password_hash=_hash_password(password) if password else None,
    )
    if not ok:
        vista = {**actual, **datos, "role_id": role_id}
        return render_template("usuario_form.html", roles=roles, usuario=vista,
                               errores=[error], active_nav="usuarios"), 400

    log_audit(g.user["sub"], "UPDATE", "users", entity_id=str(user_id),
              data_before=antes,
              data_after=_snapshot(queries.get_usuario(user_id)))
    flash(f"Usuario '{actual['username']}' actualizado.", "ok")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:user_id>/estado", methods=["POST"])
@admin_required
def usuario_estado(user_id):
    """Baja / alta logica (is_active). Es la via correcta cuando el usuario ya
    tiene registros y por eso no se puede borrar de verdad."""
    actual = queries.get_usuario(user_id)
    if not actual:
        flash("Ese usuario ya no existe.", "error")
        return redirect(url_for("usuarios"))

    activar = request.form.get("activar") == "1"
    if user_id == g.user["sub"] and not activar:
        flash("No puedes desactivar tu propia cuenta.", "error")
        return redirect(url_for("usuarios"))

    queries.desactivar_usuario(user_id, activo=activar)
    log_audit(g.user["sub"], "UPDATE", "users", entity_id=str(user_id),
              data_before=_snapshot(actual),
              data_after=_snapshot(queries.get_usuario(user_id)))
    flash(("Usuario reactivado." if activar else "Usuario desactivado (baja logica)."), "ok")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:user_id>/eliminar", methods=["POST"])
@admin_required
def usuario_eliminar(user_id):
    actual = queries.get_usuario(user_id)
    if not actual:
        flash("Ese usuario ya no existe.", "error")
        return redirect(url_for("usuarios"))

    if user_id == g.user["sub"]:
        flash("No puedes eliminar tu propia cuenta.", "error")
        return redirect(url_for("usuarios"))

    dependencias = queries.dependencias_usuario(user_id)
    if dependencias:
        detalle = ", ".join(f"{n} {etiqueta}" for etiqueta, n in dependencias)
        flash(f"No se puede eliminar a '{actual['username']}': tiene {detalle}. "
              f"Usa 'Desactivar' para darlo de baja sin perder esa trazabilidad.",
              "error")
        return redirect(url_for("usuarios"))

    antes = _snapshot(actual)
    ok, error = queries.eliminar_usuario(user_id)
    if not ok:
        flash(error, "error")
        return redirect(url_for("usuarios"))

    log_audit(g.user["sub"], "DELETE", "users", entity_id=str(user_id),
              data_before=antes)
    flash(f"Usuario '{actual['username']}' eliminado.", "ok")
    return redirect(url_for("usuarios"))


@app.route("/auditoria")
@admin_required
def auditoria():
    # Solo ADMINISTRADOR: la bitacora expone quien hizo que y desde que IP en
    # todo el sistema, incluidos los snapshots del CRUD de usuarios. Ocultar el
    # item del sidebar no basta -- la URL se puede escribir a mano, asi que el
    # candado va aqui y el intento queda registrado como PERMISSION_DENIED.
    busqueda = request.args.get("q") or None
    usuario_id = request.args.get("usuario", type=int)
    modulo = request.args.get("modulo") or None
    accion = request.args.get("accion") or None

    resumen = queries.get_auditoria_resumen()
    eventos = queries.get_auditoria_lista(
        busqueda=busqueda, usuario_id=usuario_id, modulo=modulo, accion=accion, limit=100
    )
    usuarios_filtro = queries.get_usuarios_para_filtro()
    modulos = queries.get_modulos_auditoria()
    acciones = queries.get_acciones_auditoria()

    return render_template(
        "auditoria.html",
        resumen=resumen,
        eventos=eventos,
        usuarios_filtro=usuarios_filtro,
        modulos=modulos,
        acciones=acciones,
        filtro_q=busqueda or "",
        filtro_usuario=usuario_id,
        filtro_modulo=modulo,
        filtro_accion=accion,
        active_nav="auditoria",
    )


@app.route("/stub/<name>")
@login_required
def stub(name):
    titulo = STUB_ITEMS.get(name, name.capitalize())
    return render_template("stub.html", titulo=titulo, active_nav=name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
