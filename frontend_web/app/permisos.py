"""Sesion web: cookie con el JWT y decoradores de acceso por rol.
La parte de credenciales (usuarios, bcrypt, firma del JWT) vive en backend_web.auth.
"""
from functools import wraps

from flask import request, redirect, url_for, g

from backend_web.auth import decode_token

COOKIE_NAME = "access_token"


def get_current_user():
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return decode_token(token)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("main.login", next=request.path))
        g.user = user
        return view(*args, **kwargs)
    return wrapped


def tiene_rol(user, *codigos):
    """True si el usuario del JWT trae alguno de los roles indicados."""
    if not user:
        return False
    return any(c in (user.get("roles") or []) for c in codigos)


def roles_required(*codigos):
    """Restringe la vista a los roles indicados.

    Misma mecanica que admin_required, pero parametrizable: la usa el catalogo
    de enfermedades, donde definir parametros epidemiologicos es trabajo del
    EPIDEMIOLOGO (el ADMINISTRADOR entra por ser quien opera el sistema).

    El intento fallido queda en la bitacora: ocultar el boton en la plantilla
    no es control de acceso.
    """
    def decorador(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if not user:
                return redirect(url_for("main.login", next=request.path))
            g.user = user
            if not tiene_rol(user, *codigos):
                from backend_web.audit import log_audit
                log_audit(user["sub"], "PERMISSION_DENIED", "diseases",
                          entity_id=request.path)
                return redirect(url_for("main.dashboard", denegado=1))
            return view(*args, **kwargs)
        return wrapped
    return decorador


def admin_required(view):
    """Restringe la vista al rol ADMINISTRADOR.

    Un usuario logueado pero sin el rol (p.ej. diana.flores, EPIDEMIOLOGO) NO
    entra: se le manda al dashboard y se deja el intento en la bitacora como
    PERMISSION_DENIED. Sin esto, cualquier cuenta autenticada podria dar de
    alta o borrar usuarios.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("main.login", next=request.path))
        g.user = user
        if not tiene_rol(user, "ADMINISTRADOR"):
            # import local para no crear un ciclo audit <-> auth al importar
            from backend_web.audit import log_audit
            log_audit(user["sub"], "PERMISSION_DENIED", "users",
                      entity_id=request.path)
            return redirect(url_for("main.dashboard", denegado=1))
        return view(*args, **kwargs)
    return wrapped
