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

from .db import query, execute

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-cambiar-en-despliegue")
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


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")
