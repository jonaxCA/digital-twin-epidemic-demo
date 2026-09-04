"""Frontera entre el cliente web y el backend.

Ninguna vista ni plantilla llama a requests directamente: todo pasa por aqui.
Hoy estas funciones leen de app/data/*.json. Cuando los microservicios existan
se pone USAR_FIXTURES = False y ni las rutas ni las plantillas se tocan.

El cliente web NO habla con PostgreSQL. Habla HTTP contra el gateway (RNF-G01);
son los microservicios quienes consultan la base (RNF-D09).
"""
import json
import os

import requests
from flask import current_app, session


# --------------------------------------------------------------------------
# Acceso de bajo nivel
# --------------------------------------------------------------------------

def _leer_fixture(nombre):
    ruta = os.path.join(current_app.config["DATA_DIR"], nombre)
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _encabezados():
    """Headers comunes. El JWT viaja en cada llamada al gateway (RF-A01)."""
    cabeceras = {"Accept": "application/json"}
    token = session.get("token")
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    return cabeceras


def _get(endpoint, params=None):
    respuesta = requests.get(
        f"{current_app.config['API_URL']}{endpoint}",
        headers=_encabezados(),
        params=params,
        timeout=current_app.config["API_TIMEOUT"],
    )
    respuesta.raise_for_status()
    return respuesta.json()


def _obtener(endpoint, fixture):
    """Elige fixture o API segun la configuracion."""
    if current_app.config["USAR_FIXTURES"]:
        return _leer_fixture(fixture)
    return _get(endpoint)


# --------------------------------------------------------------------------
# Autenticacion (RF-A)
# --------------------------------------------------------------------------

def autenticar(usuario, rol):
    """Login provisional sin backend.

    Cuando exista el microservicio de autenticacion, esta funcion hace
    POST /auth/login, recibe el JWT y devuelve el perfil real del usuario.
    """
    return {
        "usuario": usuario,
        "nombre": usuario.split("@")[0].replace(".", " ").title(),
        "rol": rol,
        "token": None,
    }


# --------------------------------------------------------------------------
# Catalogos (RF-B)
# --------------------------------------------------------------------------

def obtener_enfermedades():
    return _obtener("/enfermedades", "enfermedades.json")


def obtener_zonas():
    return _obtener("/zonas", "zonas.json")


# --------------------------------------------------------------------------
# Tablero y monitoreo (RF-G, RF-F)
# --------------------------------------------------------------------------

def obtener_indicadores():
    return _obtener("/indicadores", "indicadores.json")


def obtener_series():
    """Serie diaria. Misma forma que simulation_daily_series en MongoDB."""
    return _obtener("/series", "series.json")


def obtener_monitoreo():
    return _obtener("/monitoreo", "monitoreo.json")


# --------------------------------------------------------------------------
# Simulaciones y comparacion (RF-E, RF-F)
# --------------------------------------------------------------------------

def obtener_simulaciones():
    return _obtener("/simulaciones", "simulaciones.json")


def obtener_comparacion():
    return _obtener("/comparacion", "comparacion.json")


# --------------------------------------------------------------------------
# Administracion (RF-L) y auditoria (RF-A06)
# --------------------------------------------------------------------------

def obtener_usuarios():
    return _obtener("/usuarios", "usuarios.json")


def obtener_auditoria():
    return _obtener("/auditoria", "auditoria.json")
