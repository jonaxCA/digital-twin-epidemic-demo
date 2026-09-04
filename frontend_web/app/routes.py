"""Vistas del cliente web.

Cada vista hace lo mismo: pide datos a servicios y los pasa a la plantilla.
Nada de logica de negocio aqui.
"""
from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)

from . import servicios
from .permisos import ROLES, puede, requiere_permiso

bp = Blueprint("main", __name__)


@bp.app_context_processor
def inyectar_permisos():
    """Deja puede() disponible en todas las plantillas."""
    return {"puede": puede}


# --------------------------------------------------------------------------
# Sesion (RF-A)
# --------------------------------------------------------------------------

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        rol = request.form.get("rol", "PUBLICO")

        if not usuario:
            flash("Escribe tu usuario o correo para continuar.", "error")
            return render_template("login.html", roles=ROLES)

        perfil = servicios.autenticar(usuario, rol)
        session["usuario"] = perfil["usuario"]
        session["nombre"] = perfil["nombre"]
        session["rol"] = perfil["rol"]
        session["token"] = perfil["token"]
        return redirect(url_for("main.dashboard"))

    return render_template("login.html", roles=ROLES)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


# --------------------------------------------------------------------------
# Tablero (RF-G)
# --------------------------------------------------------------------------

@bp.route("/")
def dashboard():
    """Version publica y privada son la misma vista.

    RF-G11: el detalle mostrado depende del rol. Sin sesion se entra
    como publico general.
    """
    if not session.get("rol"):
        session["rol"] = "PUBLICO"

    return render_template(
        "dashboard.html",
        indicadores=servicios.obtener_indicadores(),
        series=servicios.obtener_series(),
    )


@bp.route("/monitoreo")
@requiere_permiso("monitoreo:ver")
def monitoreo():
    return render_template(
        "monitoreo.html",
        datos=servicios.obtener_monitoreo(),
        enfermedades=servicios.obtener_enfermedades(),
        zonas=servicios.obtener_zonas(),
    )


@bp.route("/mapa")
@requiere_permiso("mapa:ver")
def mapa():
    return render_template(
        "mapa.html",
        zonas=servicios.obtener_zonas(),
        enfermedades=servicios.obtener_enfermedades(),
    )


# --------------------------------------------------------------------------
# Simulaciones (RF-E, RF-F)
# --------------------------------------------------------------------------

@bp.route("/simulaciones")
@requiere_permiso("simulaciones:ver")
def simulaciones():
    registros = servicios.obtener_simulaciones()
    return render_template(
        "simulaciones.html",
        simulaciones=registros,
        enfermedades=servicios.obtener_enfermedades(),
    )


@bp.route("/comparacion")
@requiere_permiso("comparacion:ver")
def comparacion():
    return render_template(
        "comparacion.html",
        datos=servicios.obtener_comparacion(),
        simulaciones=servicios.obtener_simulaciones(),
        zonas=servicios.obtener_zonas(),
    )


# --------------------------------------------------------------------------
# Catalogos (RF-B)
# --------------------------------------------------------------------------

@bp.route("/enfermedades")
@requiere_permiso("catalogos:leer")
def enfermedades():
    registros = servicios.obtener_enfermedades()
    return render_template(
        "enfermedades.html",
        enfermedades=registros,
        total=len(registros),
        activas=sum(1 for e in registros if e["estado"] == "Activa"),
        inactivas=sum(1 for e in registros if e["estado"] != "Activa"),
    )


# --------------------------------------------------------------------------
# Administracion (RF-L) y auditoria (RF-A06)
# --------------------------------------------------------------------------

@bp.route("/usuarios")
@requiere_permiso("usuarios:leer")
def usuarios():
    registros = servicios.obtener_usuarios()
    return render_template(
        "usuarios.html",
        usuarios=registros,
        roles=ROLES,
        total=len(registros),
        activos=sum(1 for u in registros if u["estado"] == "Activo"),
        pendientes=sum(1 for u in registros if u["estado"] == "Pendiente"),
        inactivos=sum(1 for u in registros if u["estado"] == "Inactivo"),
    )


@bp.route("/auditoria")
@requiere_permiso("auditoria:ver")
def auditoria():
    eventos = servicios.obtener_auditoria()
    return render_template(
        "auditoria.html",
        eventos=eventos,
        total=len(eventos),
        criticas=sum(1 for e in eventos if e["critica"]),
        fallidos=sum(1 for e in eventos if e["estado"] == "Fallido"),
    )


# --------------------------------------------------------------------------
# Errores
# --------------------------------------------------------------------------

@bp.app_errorhandler(403)
def sin_permiso(_):
    return render_template(
        "error.html",
        codigo="403",
        titulo="No tienes acceso a esta seccion",
        mensaje="Tu rol no incluye permiso para ver esta pagina. "
                "Pide acceso a un administrador si lo necesitas.",
    ), 403


@bp.app_errorhandler(404)
def no_encontrado(_):
    return render_template(
        "error.html",
        codigo="404",
        titulo="Esta pagina no existe",
        mensaje="Revisa la direccion o vuelve al panorama epidemiologico.",
    ), 404