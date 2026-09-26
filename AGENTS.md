# AGENTS.md

> **Estado: Vigente** · 2026-09-25
> Instrucciones para agentes de código (Claude Code, Codex, etc.) que trabajen en este repositorio.
> Si algo aquí choca con lo que pide la persona en la sesión, pregunta antes de actuar.

## Qué es este proyecto

Simulador de respuesta a epidemias: una plataforma para ensayar decisiones de salud pública
antes de tomarlas. El usuario arma un escenario (intervenciones con fechas: cerrar escuelas,
vacunar a mayores de 60, etc.), el sistema simula la epidemia y compara escenarios por daño
(casos, hospitalizaciones, muertes) contra costo, en una frontera de Pareto.
Región de trabajo: Nuevo León, con datos del Censo 2020 del INEGI.

Es un proyecto universitario de un equipo de ocho personas. Buena parte del código se generó
con IA y varios integrantes todavía no lo conocen. Prefiere cambios pequeños, legibles y
fáciles de revisar sobre abstracciones ingeniosas. Comenta el porqué, no el qué.

## Etapa actual

- **Monolito:** una sola app Flask conectada directo a PostgreSQL.
- **Trabajo en curso:** `docs/CHECKLIST_SEGUNDO_AVANCE.md`, que salió de correcciones pedidas
  por el profesor. Su sección "Prueba de aceptación" (22 pasos) define cuándo algo está terminado.
- **Flujo por demostrar:** escenario → aprobación → simulación → resultados → comparación → auditoría.
- **Motor:** `procesamiento/motor` (`python-ref-0.1`) es un modelo SEIR estocástico por grupos
  de edad, sin agentes, pedido por el profesor como motor de prueba. El modelo basado en agentes
  (ABM) es trabajo futuro: no conviertas el SEIR en ABM ni le agregues agentes.
- **Pantallas pendientes:** escenarios, versiones, aprobación, simulaciones y comparación.
  El motor todavía no está conectado a ninguna pantalla.

## Fuera de alcance: no lo agregues

MongoDB, Redis, colas externas, microservicios, CUDA/Numba/FLAME GPU, ABM, app móvil,
app de escritorio, contratos OpenAPI/XSD, calibración, IA predictiva, visualización 3D
y un modelo económico sofisticado. Aunque aparezcan en `docs/arquitectura/` o
`docs/contexto/`, son etapas posteriores.

Las carpetas `microservicios/`, `infra/`, `frontend_movil/`, `frontend_desktop/` y
`docs/contratos/` están reservadas: no crees código ahí.

## Mapa del repositorio

| Ruta                               | Qué contiene                                                                            |
|------------------------------------|-----------------------------------------------------------------------------------------|
| `backend_web/db.py`                | Conexión a PostgreSQL: `query()`, `execute()`, `get_conn()`                             |
| `backend_web/queries.py`           | Todas las consultas SQL, más validaciones y formato (se partirá por dominio)            |
| `backend_web/auth.py`              | Contraseñas (bcrypt) y firma del JWT                                                    |
| `backend_web/audit.py`             | `log_audit()`: escribe en la bitácora `audit_log`                                       |
| `frontend_web/app/routes.py`       | Todas las rutas del sitio (un solo blueprint: `main`)                                   |
| `frontend_web/app/permisos.py`     | Sesión (JWT en cookie) y candados: `login_required`, `roles_required`, `admin_required` |
| `frontend_web/app/templates/`      | Plantillas Jinja2                                                                       |
| `procesamiento/motor/`             | Motor SEIR (`simular`) y frontera de Pareto (`comparar`)                                |
| `procesamiento/tests/`             | Pruebas del motor (unittest)                                                            |
| `datos/postgres/migraciones/`      | Esquema de la base: migraciones numeradas 001 a 017                                     |
| `datos/postgres/dump_completo.sql` | Las migraciones concatenadas, para instalar rápido                                      |
| `datos/postgres/semillas/`         | Datos de demostración: municipios, casos sintéticos y cuentas                           |
| `datos/censo/`, `datos/geo/`       | Datos oficiales del INEGI; cada archivo dice su fuente                                  |
| `datos/scripts/`                   | Generadores de datos y `verifica_migraciones.py`                                        |

## Comandos

Cada línea se ejecuta desde la raíz del repositorio, con el entorno virtual activo:

```bash
python -m frontend_web.run                                       # sitio en http://localhost:5000
(cd procesamiento && python -m unittest discover -s tests -t .)  # pruebas del motor
(cd procesamiento && python -m motor)                            # ejemplo de 4 escenarios con frontera
python datos/scripts/verifica_migraciones.py                     # el dump coincide con las migraciones
```

- Instalación completa: `docs/INSTALACION.md`. Su paso 5 dice `python app.py`; está
  desactualizado, el comando correcto es el de arriba.
- `CONTRIBUTING.md` menciona `docker compose up`, pero todavía no existe `docker-compose.yml`.
- Cuentas de prueba (contraseñas en `docs/INSTALACION.md`): `admin` (ADMINISTRADOR),
  `diana.flores` (EPIDEMIOLOGO) y `alex.cavazos` (ANALISTA). No hay cuenta de CAPTURISTA.

## Reglas de arquitectura

1. **Sin SQL en `routes.py`.** Si una pantalla necesita datos nuevos, agrega una función en
   `backend_web/` y llámala desde la ruta.
2. **El motor no conoce Flask ni la base.** `procesamiento/motor` recibe y regresa diccionarios
   de Python. El código que lee de la base y llama al motor vive fuera de `motor/`.
3. **Reproducibilidad.** Misma entrada y misma semilla deben dar el mismo resultado.
   No uses azar sin semilla.
4. **Cada ruta nueva lleva candado.** Ocultar un botón del menú no es control de acceso.
   Los permisos por rol viven en la tabla `role_permissions` (migración 010); si la ruta
   no encaja con esa matriz, pregunta.
5. **Todo cambio de datos se audita** con `log_audit()`. En CREATE, UPDATE y DELETE hay que
   pasar `data_before` o `data_after` (lo exige un CHECK). Nunca guardes contraseñas ni hashes
   en la bitácora.
6. **Gráficas con Highcharts**, interfaz responsive y textos de la interfaz en español.

## Reglas de base de datos

7. **El esquema son las migraciones.** Ante cualquier duda sobre tablas o columnas, la verdad
   está en `datos/postgres/migraciones/`, no en los documentos.
8. **Cambio de esquema = migración nueva** con el siguiente número (`018_…sql`):
   idempotente (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`), registrada en `schema_migrations`
   y agregada también al final de `dump_completo.sql`. Nunca edites una migración ya aplicada.
   Antes de crear una, confirma el número con la persona: hay números reservados.
9. **Las reglas de negocio de la base no se esquivan desde Python:** solo se simula una
   versión aprobada (`fn_version_aprobada`), nadie aprueba su propia versión (CHECK) y
   `audit_log` es solo de inserción.
10. **Usa los estados de la base**, no traducciones:
    - Versiones de escenario: `borrador`, `en_revision`, `aprobado`, `rechazado`.
    - Corridas: `encolado`, `ejecutando`, `completado`, `fallido`, `cancelado`.
11. **Nombres en la base:** tablas y columnas en inglés, en plural y con guion bajo
    (`scenario_versions`, `disease_id`).

## Reglas de honestidad de los datos

12. **No inventes cifras.** Todo parámetro de enfermedad o costo lleva su fuente o la marca de
    supuesto: `{"valor": 1.3, "fuente": "Biggerstaff et al., 2014", "supuesto": false}`.
    Si falta un dato, el sistema se niega a simular y dice cuál falta, como ya hace el motor.
13. **Aviso visible** en toda pantalla de resultados: no es una predicción y depende de los supuestos.
14. **La decisión final es del usuario.** La comparación muestra opciones y lo que cuesta cada
    una; no recomienda un escenario.

## Estilo de código

- Debe correr en Python 3.9: no uses `match` ni `X | Y` en anotaciones sin
  `from __future__ import annotations`.
- Sigue el estilo del archivo que editas: funciones y variables en español
  (`crear_caso`, `get_enfermedades`), columnas de la base en inglés.
- Dependencias nuevas, con versión fija, en el `requerimientos.txt` del componente.
- Secretos solo en `.env` (plantilla: `.env.example`). No agregues valores por defecto
  con credenciales.

## Decisiones abiertas: pregunta antes de implementar

El equipo todavía las está discutiendo. Si tu tarea toca alguna, pregunta; no elijas por tu cuenta.

- Quién captura casos, quién aprueba versiones y quién consulta la auditoría.
- Cuántas réplicas usa una comparación y cómo se resumen (mediana y banda, o una sola corrida).
- Qué significa la población de un escenario: habitantes o agentes simulados.
- Unidad de costo: personas-día, pesos o ambos por separado.
- Si una versión guarda una copia de los parámetros de la enfermedad al enviarse a revisión.
- Política para corregir datos en migraciones ya aplicadas. Por eso
  `verifica_migraciones.py` hoy falla en `010`: es una diferencia conocida, no la corrijas.
- Qué parte del trabajo con escenarios queda en la web y qué en la futura app de escritorio.

Cuando se decidan, quedarán en `docs/decisiones.md`.

## Qué manda cuando dos fuentes se contradicen

1. Lo que pida la persona en la sesión.
2. `docs/decisiones.md`.
3. Este archivo.
4. `docs/CHECKLIST_SEGUNDO_AVANCE.md` (qué construir).
5. `docs/arquitectura/arquitectura_v1.md`.
6. `docs/contexto/simulador.md`.

Para el esquema de la base, las migraciones ganan sobre cualquier documento.

Partes conocidas como desactualizadas en el checklist:

- Rutas anteriores a la reestructura: `db/` es ahora `datos/postgres/`, `data/censo/` es
  `datos/censo/` y `motor/` es `procesamiento/motor/`.
- Nombra los estados de corrida como PENDIENTE, COMPLETADA y ERROR; usa los de la base (regla 10).
- La última casilla del bloque E dice que ninguna enfermedad se puede simular. Desde la
  migración 017, COVID-19 e influenza sí se pueden.

## Documentos

Ábrelos cuando los necesites; no hace falta leerlos todos al empezar.

| Archivo                                | Para qué                                                               |
|----------------------------------------|------------------------------------------------------------------------|
| `docs/CHECKLIST_SEGUNDO_AVANCE.md`     | Qué construir ahora                                                    |
| `docs/decisiones.md`                   | Decisiones tomadas y abiertas                                          |
| `docs/INSTALACION.md`                  | Instalación completa y cuentas de prueba                               |
| `docs/contexto/simulador.md`           | Cómo funciona el simulador: modelo, intervenciones, réplicas, frontera |
| `docs/arquitectura/arquitectura_v1.md` | Arquitectura objetivo del sistema completo                             |
| `docs/modelo_datos/convenciones.md`    | Convenciones y decisiones del modelo de datos                          |
| `CONTRIBUTING.md`                      | Flujo de Git del equipo                                                |

## Git

Sigue `CONTRIBUTING.md`. Lo esencial:

- Una rama por tarea, con prefijo: `feat/`, `fix/`, `docs/`, `chore/` o `refactor/`.
- Commits chicos, en español, en imperativo y sin punto final ("Agrega pantalla de versiones").
- Nunca hagas push directo a `main` ni `git push --force`. Todo entra por PR con revisor.
- Si la tarea corresponde a una casilla del checklist, márcala en el mismo PR.

## Antes de dar una tarea por terminada

- [ ] Las pruebas del motor pasan.
- [ ] Si tocaste `datos/`, `verifica_migraciones.py` no muestra diferencias nuevas
      (hoy solo falla `010`; ver decisiones abiertas).
- [ ] Probaste las pantallas afectadas con la cuenta de prueba de cada rol involucrado.
- [ ] No hay SQL en `routes.py`, ni credenciales, ni cifras sin fuente.
- [ ] Cada cambio de datos deja registro en la auditoría.
