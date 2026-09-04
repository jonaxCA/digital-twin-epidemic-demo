"""Roles, permisos y control de acceso a las vistas.

Este archivo es el unico lugar donde vive la matriz de permisos. Cuando
llegue la matriz definitiva, se edita PERMISOS y no se toca nada mas.
"""
from functools import wraps

from flask import abort, redirect, session, url_for

# RF-A04: cinco perfiles del sistema.
ROLES = {
    "ADMINISTRADOR": "Administrador",
    "EPIDEMIOLOGO": "Epidemiologo",
    "ANALISTA": "Analista",
    "CAPTURISTA": "Capturista",
    "PUBLICO": "Publico general",
}

# RF-A05: permisos diferenciados por rol. "*" es acceso total.
PERMISOS = {
    "ADMINISTRADOR": ["*"],
    "EPIDEMIOLOGO": [
        "tablero:ver", "monitoreo:ver", "simulaciones:ver", "comparacion:ver",
        "mapa:ver", "catalogos:leer", "catalogos:escribir", "auditoria:ver",
    ],
    "ANALISTA": [
        "tablero:ver", "monitoreo:ver", "simulaciones:ver", "comparacion:ver",
        "mapa:ver", "catalogos:leer",
    ],
    # RN-04: el capturista opera exclusivamente desde la app Android.
    "CAPTURISTA": [],
    "PUBLICO": ["tablero:ver"],
}


def rol_actual():
    return session.get("rol")


def puede(permiso):
    """True si el rol en sesion tiene el permiso. Tambien se usa en plantillas."""
    permitidos = PERMISOS.get(rol_actual(), [])
    return "*" in permitidos or permiso in permitidos


def requiere_permiso(permiso):
    """Protege una vista: sin sesion manda a login, sin permiso responde 403."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if not rol_actual():
                return redirect(url_for("main.login"))
            if not puede(permiso):
                abort(403)
            return vista(*args, **kwargs)
        return envoltura
    return decorador
