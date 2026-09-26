# Migraciones de PostgreSQL

Modelo físico del Simulador de respuesta a epidemias. Archivos SQL numerados,
sin Alembic: se ejecutan en orden y cada uno registra su aplicación en la tabla
`schema_migrations`.

## Archivos

| Archivo | Contenido |
|---|---|
| `001_base.sql` | Extensiones, funciones compartidas y tabla de control de migraciones |
| `002_seguridad.sql` | `users`, `roles`, `permissions`, `user_roles`, `role_permissions`, `password_resets`, `devices` |
| `003_sistema.sql` | `audit_log`, `notifications`, `system_settings` |
| `004_catalogos.sql` | `diseases`, `regions`, `intervention_types` |
| `005_vigilancia.sql` | `vaccine_lots`, `cases`, `case_attachments` |
| `006_escenarios.sql` | `scenarios`, `scenario_versions`, `scenario_interventions` |
| `007_simulacion.sql` | `simulation_batches`, `simulation_runs` |
| `008_comentarios.sql` | `COMMENT ON` de las 21 tablas y sus 183 columnas |
| `009_roles_bd.sql` | Roles de PostgreSQL por microservicio y sus privilegios |
| `010_datos_iniciales.sql` | Roles de negocio, permisos, matriz de permisos y catálogos |
| `019_correccion_manual_poblacion.sql` | `region_population_adjustments`: ajuste vigente de población hecho a mano por un `ADMINISTRADOR` (Bloque C, catálogo de Regiones) |
| `020_letalidad_por_edad.sql` | Letalidad (IFR) por grupo de edad de COVID-19 e influenza, derivada de literatura publicada. La genera `datos/scripts/build_letalidad_edad.py`: no se edita a mano |
| `021_poblacion_por_grupo_edad.sql` | `region_age_groups`: población de los 51 municipios y del estado abierta en los cinco grupos de edad del motor, más la categoría `edad_no_especificada` (Censo 2020, ITER). La genera `datos/scripts/build_grupos_edad.py`: no se edita a mano |
| `022_poblacion_60plus_derivada.sql` | `regions.population_60plus` pasa a derivarse de `region_age_groups` con un trigger; deja de capturarse a mano |
| `023_escenarios_poblacion_por_edad.sql` | `scenario_versions` guarda la población por grupo de edad y la política de edad desconocida; el tope de población sube de 5 a 20 millones para que quepa el estado completo |
| `024_version_congela_parametros.sql` | `scenario_versions.disease_params`: la versión congela los parámetros de la enfermedad al salir de borrador, para que corregir el catálogo no cambie el significado de lo ya aprobado |

El orden importa: `005` referencia catálogos de `004`, y `007` referencia
escenarios de `006`. No cambien la numeración.

## Cómo ejecutarlas

Con la base ya creada:

```bash
for f in $(ls migraciones/0*.sql | sort); do
  psql -v ON_ERROR_STOP=1 -f "$f" || break
done
```

Con Docker Compose, montar la carpeta en el directorio de inicialización de la
imagen oficial. Postgres ejecuta los archivos en orden alfabético la primera vez
que arranca con un volumen vacío:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: simulador
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - ./Datos/postgres/migraciones:/docker-entrypoint-initdb.d:ro
      - pgdata:/var/lib/postgresql/data
```

Ojo: `/docker-entrypoint-initdb.d` solo corre con el volumen vacío. Para aplicar
una migración nueva sobre una base existente, ejecútenla con `psql` a mano.

## Reglas de trabajo

**Nunca editen un archivo ya aplicado.** Si algo cambia, se agrega un archivo
nuevo con el número siguiente. Editar el 004 después de que tres personas lo
corrieron deja tres bases distintas que parecen iguales.

**Todos los archivos son idempotentes.** Se pueden volver a correr sin error, lo
que permite reconstruir una base local sin borrar nada. Está probado.

**Una transacción por archivo.** Si algo falla a la mitad, no queda un esquema
a medias.

## Verificación

Estas migraciones se ejecutaron contra PostgreSQL 16.15 y producen:

- 22 tablas (21 del modelo más `schema_migrations`)
- 33 llaves foráneas
- 67 restricciones `CHECK`
- 72 índices
- 4 triggers
- 205 comentarios de documentación

Se validaron dos veces seguidas para confirmar idempotencia, y se probaron 15
casos negativos que las restricciones deben rechazar: correos con mayúsculas,
casos reportados antes del inicio de síntomas, dosis aplicadas mayores que las
del lote, dos versiones vigentes del mismo escenario, corridas completadas sin
fecha de término, intentos de modificar la bitácora, y demás. Los 15 fallan como
se espera.

## Pendientes

- **Contraseña del administrador inicial.** `010` inserta el usuario `admin` con
  un hash marcador que no permite autenticarse. Hay que generarlo y sustituirlo
  antes de la demostración.
- **Contraseñas de los roles de servicio.** `009` las crea con un marcador. En
  Compute Engine se generan aparte y se inyectan desde Secret Manager.
- **AGEB.** `010` carga estado y los diez municipios del área metropolitana. Las
  AGEB son miles y se cargan con un script aparte desde el marco geoestadístico
  del INEGI.
- **Parámetros de enfermedad.** Los de `010` son valores de literatura sin
  calibrar. La calibración contra la ola histórica los sustituye.
- **Particionamiento.** Si `audit_log` o `simulation_runs` crecen mucho durante
  las pruebas de carga, evaluar partición por rango de fecha.
