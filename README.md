# EPIDEMIA — Sistema Monolítico v0.1

Responsables de programación de este Sprint:

-- Rolando Rivas Dávalos

-- Jonathan Correa Ascencio


Primera versión funcional del monolito del **Simulador de respuesta a epidemias**,
correspondiente al Primer Avance.

Incluye dashboard público, login con JWT, dashboard autenticado, análisis de
monitoreo, mapa por municipio de Nuevo León, catálogo de enfermedades, captura de
casos, gestión de usuarios y bitácora de auditoría, además del motor de simulación
de referencia (`motor/`), que todavía no está conectado a las pantallas.

Corre como **una sola app Flask monolítica contra PostgreSQL**, sin capa de
microservicios (eso es alcance del segundo parcial). En este proyecto, "demo" se
refiere únicamente a los **datos de demostración** (`demo_datos_nl.sql`), no al sistema.

---

# Guía de instalación

Estas instrucciones funcionan en **Linux, macOS y Windows**. Si es tu primera vez,
sigue los 5 pasos en orden y no te saltes ninguno.

## Paso 0 — Qué necesitas instalado

| Requisito | Versión | Cómo verificar |
|---|---|---|
| **PostgreSQL** | 15 o superior | `psql --version` |
| **Python** | 3.9 o superior | `python3 --version` (en Windows: `python --version`) |
| **Conexión a internet** | — | Necesaria al abrir la app: las gráficas usan Highcharts desde su CDN |

> **PostgreSQL 15 es obligatorio**, no es capricho: la migración `006_escenarios.sql`
> usa `UNIQUE NULLS NOT DISTINCT`, que no existe en versiones anteriores.

Si no lo tienes:

- **Windows / macOS**: instalador oficial de <https://www.postgresql.org/download/>
  (en Windows, durante la instalación **anota la contraseña** que le pongas al
  usuario `postgres`; la vas a necesitar en el Paso 1).
- **Debian / Ubuntu**: `sudo apt install postgresql python3-venv`
- **Fedora**: `sudo dnf install postgresql-server python3`

### Abrir la consola de PostgreSQL (`psql`)

Todos los comandos de base de datos de esta guía se corren con `psql`.

- **Windows**: abre **SQL Shell (psql)** desde el menú inicio, o usa
  `"C:\Program Files\PostgreSQL\18\bin\psql.exe"` desde PowerShell (ajusta el
  número a la versión que hayas instalado).
- **Linux / macOS**: `psql` ya está en tu `PATH`.

Conéctate siempre así (te va a pedir la contraseña del usuario `postgres`):

```bash
psql -h localhost -U postgres
```

Si eso te da error de autenticación, revisa **Problemas comunes** al final.

---

## Paso 1 — Crear la base de datos y el usuario de la aplicación

Conéctate con `psql -h localhost -U postgres` y pega esto **tal cual**:

```sql
CREATE DATABASE simulador_epidemico;

CREATE ROLE epidemia_app LOGIN PASSWORD 'epidemia_app_pw';
```

Después **sal** (`\q`). Todavía falta darle permisos al rol, pero eso se hace
hasta el Paso 3, cuando ya existan las tablas.

> Puedes cambiar el nombre de la base y la contraseña si quieres; solo recuerda
> usar los mismos valores en el Paso 4.

---

## Paso 2 — Cargar el esquema y los datos

Desde una terminal, **parado en la carpeta del proyecto** (donde está `app.py`),
corre los tres archivos **en este orden exacto**:

```bash
psql -h localhost -U postgres -d simulador_epidemico -v ON_ERROR_STOP=1 -f db/dump_completo.sql
psql -h localhost -U postgres -d simulador_epidemico -v ON_ERROR_STOP=1 -f db/datos/nl_municipios_completos.sql
psql -h localhost -U postgres -d simulador_epidemico -v ON_ERROR_STOP=1 -f db/datos/demo_datos_nl.sql
```

En Windows PowerShell es lo mismo, pero anteponiendo la ruta a `psql.exe` si no
está en el `PATH`.

**Qué hace cada uno:**

| Archivo | Qué carga |
|---|---|
| `db/dump_completo.sql` | El esquema completo: las 14 migraciones numeradas (001–014) concatenadas |
| `db/datos/nl_municipios_completos.sql` | Completa los 51 municipios de Nuevo León |
| `db/datos/demo_datos_nl.sql` | Datos de demostración (sintéticos): 3,824 casos, escenario, simulaciones y la usuaria de login |

**El orden importa.** Los dos últimos archivos dependen del esquema y del catálogo
de regiones que carga `dump_completo.sql`.

> **¿Ya tenías la base de una versión anterior?** Vuelve a correr
> `db/dump_completo.sql`. Es idempotente: lo que ya existe no se duplica y se aplican
> las migraciones que falten. No hace falta ningún archivo de corrección aparte.

`-v ON_ERROR_STOP=1` hace que `psql` se detenga al primer error en vez de seguir
y dejarte la base a medias. Si un comando termina sin mensajes de `ERROR`, salió bien.

---

## Paso 3 — Dar permisos al usuario de la aplicación

Ahora que las tablas ya existen, dale acceso al rol que creaste en el Paso 1:

```bash
psql -h localhost -U postgres -d simulador_epidemico -c "
  GRANT USAGE ON SCHEMA public TO epidemia_app;
  GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO epidemia_app;
  GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO epidemia_app;
"
```

La app necesita `INSERT` y `UPDATE` (no solo lectura) porque el login actualiza
`users.last_login_at` y la auditoría escribe en `audit_log`.

---

## Paso 4 — Instalar Python y configurar la conexión

### 4.1 Crear el entorno virtual e instalar dependencias

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> Si PowerShell bloquea el script de activación, corre una vez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Sabrás que el entorno está activo porque el prompt empieza con `(.venv)`.

### 4.2 Crear el archivo `.env`

Copia la plantilla:

```bash
cp .env.example .env          # Windows: copy .env.example .env
```

Y edita `.env` para que quede así (ajusta usuario, contraseña, host, puerto y
nombre de base si usaste otros en el Paso 1):

```
DATABASE_URL=postgresql://epidemia_app:epidemia_app_pw@localhost:5432/simulador_epidemico
JWT_SECRET_KEY=pon-aqui-cualquier-cadena-larga-y-aleatoria
```

**No necesitas exportar nada a mano**: `db.py` lee el `.env` automáticamente con
`python-dotenv` al arrancar.

---

## Paso 5 — Arrancar la aplicación

Con el entorno virtual activo y en la carpeta del proyecto:

```bash
python app.py
```

Verás algo como `Running on http://127.0.0.1:5000`. Abre en tu navegador:

**<http://localhost:5000/>**

Para detenerla: `Ctrl + C`.

### Credenciales

| Usuario | Contraseña | Rol | Qué puede hacer |
|---|---|---|---|
| `alex.cavazos` | `Epidemia2026!` | ANALISTA | Vigilancia, mapa, monitoreo y captura de casos |
| `diana.flores` | `Epidemia2026!` | EPIDEMIOLOGO | Lo mismo por ahora |
| `admin` | `Admin2026!` | ADMINISTRADOR | Además, **Usuarios** y **Auditoría** |

> Los dos primeros son personas distintas a propósito: la migración `013`
> prohíbe que quien crea una versión de escenario sea quien la aprueba, y esa
> regla ya vive en la base de datos. Las pantallas que la usan (crear escenario,
> enviar a revisión, aprobar) son parte del siguiente avance, así que hoy ambos
> usuarios ven lo mismo en la interfaz.

> Las tres contraseñas las pone `db/datos/demo_datos_nl.sql`, así que con los
> tres comandos del Paso 2 ya puedes entrar con cualquiera. No hay archivos
> extra que correr.
>
> **Por qué importa el detalle:** `010_datos_iniciales.sql` crea al usuario
> `admin` con el marcador `REEMPLAZAR_ANTES_DE_DESPLEGAR` como `password_hash`,
> inválido a propósito. Quien instale **solo el esquema**, sin los datos de
> demostración, se queda con esa cuenta inutilizable — que es justo lo que
> quieres en un servidor real. La contraseña que funciona vive únicamente en los
> datos de demostración.

### Gestión de usuarios (solo ADMINISTRADOR)

Entrando como `admin` aparece **Usuarios** en el menú, con alta, edición, baja
lógica y eliminación. Con `diana.flores` ese menú **no se ve**, y entrar por URL
directa (o mandar un POST a mano) tampoco funciona: rebota al dashboard y deja el
intento en la bitácora como `PERMISSION_DENIED`.

Cada operación queda registrada en Auditoría con el estado antes y después
(nunca se guarda la contraseña).

**Sobre el botón Eliminar.** Funciona gracias a la migración
`011_fix_audit_log_delete.sql`, incluida en `dump_completo.sql`. `003_sistema.sql`
declaraba `audit_log.user_id ... ON DELETE SET NULL`, pero la bitácora tiene un
trigger que rechaza todo `UPDATE`, así que borrar a cualquier usuario con un solo
evento fallaba con `restrict_violation`. La `011` permite **únicamente** que la
llave foránea ponga `user_id` en NULL sin tocar ningún otro campo: la bitácora
sigue sin admitir borrados ni cambios de contenido.

Aun así no siempre procede: si el usuario tiene casos capturados,
escenarios o lotes de simulación, la base lo impide con `ON DELETE RESTRICT` y
la pantalla te dice exactamente qué tiene y te manda a **Desactivar**.

**Desactivar sigue siendo la vía recomendada.** Al eliminar de verdad, los
eventos que esa persona generó permanecen en la bitácora pero **pierden la
atribución**: quedan con `user_id` nulo y se muestran como "Anónimo". Ya no vas
a poder saber quién los hizo. Lo único que se conserva es el registro `DELETE`,
que guarda en `data_before` quién era la cuenta eliminada. La baja lógica evita
esa pérdida por completo.

---

## ¿Quedó bien instalado?

Recorre esta lista. Si algo no coincide, ve a **Problemas comunes**.

1. `http://localhost:5000/` abre el **dashboard público** sin pedir login.
2. Entras con `diana.flores` / `Epidemia2026!` y llegas al **Panorama Epidemiológico**.
3. El dashboard muestra números **distintos de cero** (~684 casos activos) y una
   gráfica de curva epidémica dibujada.
4. **Mapa epidemiológico** pinta los municipios de Nuevo León en colores.
5. **Auditoría** ya tiene al menos un renglón `LOGIN` — lo generó tu propio acceso.
6. Entrando como `admin` aparece **Usuarios** en el menú, con los botones de
   Editar / Desactivar / Eliminar.

Verificación rápida por consola (deberías ver `casos=3824`):

```bash
psql -h localhost -U postgres -d simulador_epidemico -Atc "SELECT 'casos='||count(*) FROM cases"
```

---

## Problemas comunes

| Síntoma | Causa y solución |
|---|---|
| `psql: error: connection to server ... failed` | El servidor de PostgreSQL no está corriendo. Linux: `sudo systemctl start postgresql`. Windows/macOS: inícialo desde el instalador o los Servicios del sistema. |
| `password authentication failed for user "postgres"` | Contraseña incorrecta. En Linux puedes reasignarla: `sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'nueva';"` |
| `Peer authentication failed` (solo Linux) | Estás conectando por socket. Usa siempre `-h localhost`, que fuerza conexión TCP con contraseña. |
| `FATAL: database "simulador_epidemico" does not exist` | Te faltó el Paso 1, o escribiste otro nombre en el `.env`. |
| `psycopg2.OperationalError` al arrancar `app.py` | El `DATABASE_URL` del `.env` no coincide con tu base/usuario/contraseña reales. Revisa el Paso 4.2. |
| `permission denied for table ...` | Te faltó el Paso 3 (los `GRANT`), o lo corriste **antes** del Paso 2, cuando las tablas todavía no existían. Vuelve a correrlo. |
| Todo se ve en **cero** y no puedes entrar | Falta `demo_datos_nl.sql` (Paso 2). Sin él no existe `diana.flores` ni hay casos. |
| Las **gráficas no aparecen** (el resto sí) | Highcharts se carga desde su CDN: necesitas internet. |
| `syntax error at or near "NULLS"` al cargar el esquema | Tu PostgreSQL es menor a 15. Actualiza. |
| El puerto 5000 está ocupado | Cambia el puerto en la última línea de `app.py`, o libera el 5000. En macOS suele ocuparlo *AirPlay Receiver*. |

### Volver a empezar de cero

Si quedó algo a medias y prefieres reinstalar la base:

```bash
psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS simulador_epidemico;"
```

Y repite desde el Paso 1.

`demo_datos_nl.sql` es seguro de volver a correr las veces que quieras: trunca
las tablas de casos, escenarios y simulaciones antes de insertar.

---

# Notas del proyecto

## Por qué no se reusó el export de Figma tal cual

Los zips de `figma-to-html*` exportan puro `<div>`/`<span>` posicionados de forma
absoluta, sin un solo `<form>`, `<input>` o `<button>` real, y con varias imágenes
de fondo rotas (rutas a archivos que no venían en el zip). El mapa "nacional" de
una de las capturas es una foto de stock, no una visualización real.

Por eso todas las pantallas están reconstruidas desde cero como HTML/CSS/JS limpio,
replicando el diseño de las capturas (paleta muestreada directamente de las
imágenes: sidebar `#091426`, azul `#1b6ce3`, badges rojo/ámbar/verde), pero con
markup funcional de verdad.

## Alcance: qué funciona y qué no

Casi todo el sistema tiene lógica real: dashboard público, login, dashboard
autenticado, **monitoreo** (con *Compartir vista*), mapa, catálogo de enfermedades
(con *+ Nueva enfermedad*), captura de casos (*+ Nuevo Reporte*), usuarios y
auditoría. **Simulaciones** y **Comparación** todavía son páginas "Próximamente".

El **motor de simulación** y el **cálculo de la frontera de Pareto** ya existen como
paquete de Python en `motor/`, con pruebas, pero aún no están conectados a la base
ni a las pantallas. Ver *Motor de simulación* más abajo.

Los tres **"Exportar" sí son funcionales** — el del dashboard descarga el resumen
de situación, el de Enfermedades el catálogo y el de Monitoreo el detalle por zona,
los tres **respetando los filtros que tengas puestos**.

## Qué es real y qué es de relleno

- **Real de verdad**: todos los números de todas las pantallas salen de consultas
  SQL contra PostgreSQL. Nada está hardcodeado en el HTML.
- **Auditoría real**: `audit_log` no trae historial precargado. Se llena con tu
  uso real de la app (cada login, logout y exportación). Que la pantalla empiece
  vacía es lo correcto.
- **Sintético pero cargado en Postgres**: los 3,824 casos, el escenario y las
  corridas de simulación. Los generó `gen_demo_data.py` con semilla fija
  (reproducible). No son casos reales.

Para regenerar los datos sintéticos (o ajustar tendencias por municipio):

```bash
python scripts/gen_demo_data.py > db/datos/demo_datos_nl.sql
```

## Decisiones que falta validar.

- **Tasa de incidencia**: la cambié de "%" (como en el mock de Figma) a *casos por
  100,000 habitantes*, que es la convención epidemiológica real. Un porcentaje
  sobre 5.8M de habitantes nunca da un número legible.
- **Clasificación Crítico/Alerta/Estable**: la definí yo (≥50% de aumento semanal
  = Crítico, ≥15% = Alerta, resto = Estable). No viene del documento del proyecto.
- **Zonas en riesgo**: municipios con incidencia >10 casos/100k en los últimos 7
  días. Umbral también definido por mí.
- **Mapa con polígonos oficiales de INEGI**: la geometría es la capa municipal del
  Marco Geoestadístico 2024 de INEGI (entidad 19), no un geojson comunitario. Los
  **51 municipios** tienen polígono, **Hualahuises incluido**. La clave `CVEGEO` del
  shapefile ya es el `regions.code` de 5 dígitos, así que el join es directo, sin
  emparejar por nombre. Como control: la suma de las áreas da 64,291 km² contra los
  64,220 km² que reporta INEGI para el estado (0.11% de diferencia; la fuente
  anterior se iba 1.4%). El shapefile viene proyectado en Lambert Cónica Conforme
  (EPSG:6372) y `build_municipios_inegi.py` lo reproyecta a lon/lat, que es lo que
  Highcharts necesita.
- **Pendiente: población de 41 municipios.** Hoy son aproximaciones de orden de
  magnitud, no censo verificado, y deben sustituirse por el Censo 2020 de INEGI
  antes de usarse en el simulador (`POBLACION_APROX` en `build_regiones_sql.py`).
- **Highcharts Maps para el mapa** (no Leaflet): la materia exige Highcharts, así
  que el choropleth usa `Highcharts.mapChart` + `Highcharts.geojson()`. Las 5
  categorías de la leyenda son `dataClasses` del `colorAxis`, con los mismos
  umbrales que usa `queries.py` en el backend. *Nota técnica*: si vuelves a tocar
  este chart, `Highcharts.geojson()` deja las propiedades anidadas en
  `.properties`, no al nivel superior — por eso `dibujarMapa()` las aplana a mano
  antes del `joinBy`, y pasa `mapData` directo en la serie (no solo en `chart.map`).
- **Enfermedades no trae Agente, Tipo ni Riesgo** del mock: ninguna de las tres
  existe en `004_catalogos.sql`, y se decidió **no** tocar el esquema entregado.
  Inventarlas en Python rompía la regla de que nada de la vista esté hardcodeado, y
  meterlas en `default_params` habría contaminado el contrato con el motor de
  simulación. La tabla se quedó con lo que el catálogo sí modela. Si más adelante
  quieren esas columnas, el camino limpio es una migración numerada nueva
  (`013_*.sql` en adelante), no un parche aparte.
- **Columna "Alta" en vez de "Última act."**: `diseases` no tiene `updated_at`,
  solo `created_at`.
- **Monitoreo: "HOSPIT." se volvió "Graves"**: el esquema no modela hospitalización
  en ninguna parte; lo más cercano es `cases.severity = 'grave'`, así que se muestra
  eso con su nombre real en vez de uno prestado.
- **Monitoreo: las "zonas" son municipios reales**: el mock inventaba Zona
  Norte/Centro/Sur/Este/Oeste; `regions` no tiene ese nivel.
- **Monitoreo: el toggle Línea/Columna/Área solo afecta la serie de casos diarios.**
  La incidencia acumulada se queda siempre como línea: es una curva que solo sube, y
  dibujarla en columnas junto a un segundo eje se lee como si esas barras fueran
  casos. El selector "Indicador" en cambio ordena la tabla de zonas por casos o por
  incidencia.
- **La tarjeta "INACTIVAS" marca 0**: es correcto, todas las enfermedades están
  activas. Si quieres verla moverse, da de baja lógica una en Postgres
  (`UPDATE diseases SET is_active = FALSE WHERE code = 'PATOGENO_X';`) — que la
  pantalla reaccione es justamente la prueba de que lee de la base.
- Agregué **Dengue, Zika y Malaria** al catálogo (antes solo había SARS-CoV-2,
  Influenza y Patógeno X) para que el panel se pareciera al diseño de Figma.

## Motor de simulación

`motor/` es un modelo SEIR estocástico con hospitalizados, fallecidos y vacunados,
por grupo de edad y reproducible por semilla (`python-ref-0.1`), más el cálculo de
costo y frontera de Pareto para comparar escenarios. No depende de Flask ni de la
base, y no trae valores epidemiológicos ni costos por defecto: cada parámetro debe
venir con su fuente o marcado como supuesto.

```bash
python -m motor                              # ejemplo A/B/C/D con frontera de Pareto
python -m unittest discover -s tests -t .    # pruebas
```

Los números del ejemplo son **supuestos ilustrativos**, no datos de Nuevo León.

## Estructura del proyecto

```
app.py                       rutas Flask (monolito)
auth.py                      login, bcrypt, JWT en cookie httponly
audit.py                     bitacora real: cada login/logout/export escribe en audit_log
db.py                        conexion a Postgres (lee .env)
queries.py                   todas las consultas SQL reales
templates/                   plantillas Jinja2
static/css/styles.css        estilos
static/js/nl_municipios.json geometria oficial de los 51 municipios (generado)

motor/                       motor de simulacion de referencia y frontera de Pareto
tests/                       pruebas del motor

db/dump_completo.sql         esquema completo (migraciones 001-012 concatenadas)
db/migraciones/              migraciones 011 y 012 como archivos individuales
db/datos/                    cargas: municipios (generado) y datos de demostracion (incluye las 3 cuentas)

scripts/build_municipios_inegi.py  capa municipal de INEGI -> geojson del mapa + centroides
scripts/build_regiones_sql.py      centroides + catalogo -> db/datos/nl_municipios_completos.sql
scripts/gen_demo_data.py           generador de los datos de demostracion (semilla fija)
data/geo/inegi_mg2024/       capa municipal oficial (Marco Geoestadistico 2024, ent. 19)
data/geo/                    catalogo INEGI y centroides de los 51 municipios

docs/                        plan de trabajo (CHECKLIST_SEGUNDO_AVANCE.md)
requirements.txt             dependencias de Python
.env.example                 plantilla de configuracion (el .env real no se sube)
.gitignore                   excluye .env, entornos virtuales, caches, respaldos y archivo/
archivo/                     solo local, ignorado por git: pipeline y fuentes geograficas superadas
```

## Notas de seguridad

La versión v0.1 corre en entorno local y **no está endurecida para producción**:

- `JWT_SECRET_KEY` tiene un valor por defecto de desarrollo.
- La contraseña de `epidemia_app` está en texto plano en este README.
- El servidor corre con `app.run(debug=True)`, que es el servidor de desarrollo de
  Flask y expone un depurador interactivo.
- `app.run(host="0.0.0.0")` deja la app visible para toda tu red local.

Nada de esto debería llegar tal cual a Google Compute Engine en el tercer parcial.
