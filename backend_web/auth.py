"""
Autenticacion real contra la tabla users. JWT (PyJWT) guardado en una cookie
httponly -- cumple el "login con JWT" que pide el rubro del primer parcial,
sin traer todavia la capa de microservicios (eso es el segundo parcial).

No es para produccion: SECRET_KEY tiene un default de desarrollo. Cambialo
via variable de entorno antes de exponer esto fuera de tu maquina.
"""
import os
import datetime
import bcrypt
import jwt
from functools import wraps
from flask import request, redirect, url_for, g

from db import query, execute

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-cambiar-en-despliegue")
COOKIE_NAME = "access_token"
TOKEN_TTL_MINUTES = 60 * 8  # 8 horas


def find_user_by_login(username_or_email):
    return query(
        """
        SELECT id, username, email, full_name, password_hash, is_active
        FROM users
        WHERE lower(username) = lower(%s) OR lower(email) = lower(%s)
        """,
        (username_or_email, username_or_email),
        one=True,
    )


def get_user_roles(user_id):
    rows = query(
        """
        SELECT r.code FROM roles r
        JOIN user_roles ur ON ur.role_id = r.id
        WHERE ur.user_id = %s
        """,
        (user_id,),
    )
    return [r["code"] for r in rows]


def check_password(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # password_hash invalido/marcador (p.ej. el admin sin hash real todavia)
        return False


def attempt_login(username_or_email, password):
    """Devuelve (user_dict, error_message). user_dict es None si fallo."""
    user = find_user_by_login(username_or_email)
    if not user:
        return None, "Usuario o contraseña incorrectos."
    if not user["is_active"]:
        return None, "Esta cuenta esta inactiva."
    if not check_password(password, user["password_hash"]):
        return None, "Usuario o contraseña incorrectos."

    execute("UPDATE users SET last_login_at = now(), failed_attempts = 0 WHERE id = %s",
            (user["id"],))
    roles = get_user_roles(user["id"])
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "roles": roles,
    }, None


def create_token(user):
    payload = {
        "sub": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "roles": user["roles"],
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=TOKEN_TTL_MINUTES),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


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
            return redirect(url_for("login", next=request.path))
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
                return redirect(url_for("login", next=request.path))
            g.user = user
            if not tiene_rol(user, *codigos):
                from audit import log_audit
                log_audit(user["sub"], "PERMISSION_DENIED", "diseases",
                          entity_id=request.path)
                return redirect(url_for("dashboard", denegado=1))
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
            return redirect(url_for("login", next=request.path))
        g.user = user
        if not tiene_rol(user, "ADMINISTRADOR"):
            # import local para no crear un ciclo audit <-> auth al importar
            from audit import log_audit
            log_audit(user["sub"], "PERMISSION_DENIED", "users",
                      entity_id=request.path)
            return redirect(url_for("dashboard", denegado=1))
        return view(*args, **kwargs)
    return wrapped
