# EPIDEMIA — Sistema Monolítico v0.1

Responsables de programación de este Sprint:

-- Rolando Rivas Dávalos

-- Jonathan Correa Ascencio

Primera versión funcional del **Simulador de respuesta a epidemias** (Primer Avance):
dashboard público, login con JWT, mapa por municipio de Nuevo León, monitoreo,
catálogo de enfermedades, captura de casos, gestión de usuarios y bitácora de
auditoría. Corre como una sola app Flask contra PostgreSQL. El motor de simulación
de referencia vive en `procesamiento/motor/` y todavía no está conectado a las pantallas.

## Estructura

| Carpeta | Contenido |
|---|---|
| `backend_web/` | Capa de datos: conexión, consultas SQL, auditoría y credenciales |
| `frontend_web/` | Sitio web Flask (rutas, plantillas, estáticos) |
| `procesamiento/` | Motor de simulación y sus pruebas |
| `datos/` | Esquema y semillas de PostgreSQL, datos geográficos y scripts |
| `docs/` | Guía de instalación completa y plan de trabajo |

## Instalación mínima

Requiere PostgreSQL 15+ y Python 3.9+. Desde la raíz del repositorio:

```bash
createdb -h localhost -U postgres simulador_epidemico
psql -h localhost -U postgres -d simulador_epidemico -v ON_ERROR_STOP=1 -f datos/postgres/dump_completo.sql
psql -h localhost -U postgres -d simulador_epidemico -v ON_ERROR_STOP=1 -f datos/postgres/semillas/nl_municipios_completos.sql
psql -h localhost -U postgres -d simulador_epidemico -v ON_ERROR_STOP=1 -f datos/postgres/migraciones/018_correccion_poblacion_51_municipios.sql
psql -h localhost -U postgres -d simulador_epidemico -v ON_ERROR_STOP=1 -f datos/postgres/semillas/demo_datos_nl.sql

python3 -m venv .venv && source .venv/bin/activate
pip install -r frontend_web/requerimientos.txt
cp .env.example .env        # y edita DATABASE_URL y JWT_SECRET_KEY
python -m frontend_web.run
```

Abre <http://localhost:5000/>. Falta crear el rol `epidemia_app` y darle permisos
(pasos 1 y 3 de la guía completa). Usuario de prueba: `diana.flores` / `Epidemia2026!`.

**Guía completa, credenciales y solución de problemas: [docs/INSTALACION.md](docs/INSTALACION.md).**

## Pruebas del motor

```bash
cd procesamiento && python -m unittest discover -s tests -t .
```
