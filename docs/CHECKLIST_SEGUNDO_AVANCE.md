# EPIDEMIA — Checklist del segundo avance

Objetivo: demostrar el flujo completo
**Escenario → Aprobación → Simulación → Resultados → Comparación → Auditoría**
con datos persistentes en PostgreSQL y corridas reproducibles.

Stack de esta etapa: **PostgreSQL + Flask monolítico + motor Python.** Nada de
MongoDB, Redis ni CUDA todavía.

> Cada bloque (A–H) está pensado para un responsable. Cada casilla debería
> corresponder a un issue, una rama y un Pull Request en el repositorio del equipo.

---

## 0. Organización del equipo (antes de escribir código)

- [ ] El proyecto vive en **su propio repositorio** (no dentro de la carpeta de usuario)
- [ ] Asignar un responsable a cada bloque A–H
- [ ] Crear un issue por cada casilla de este documento
- [ ] Regla: una rama por issue (`feat/escenarios-versionado`, `fix/claves-inegi`, …)
- [ ] Regla: todo entra por Pull Request revisado por otro integrante, nada directo a `main`
- [ ] Regla: commits pequeños e incrementales, con el autor correcto configurado en git
- [ ] Acordar la convención de nombres de migraciones: `011_…sql`, `012_…sql`, …
- [ ] El `.tar.gz` de entrega incluye la carpeta `.git`

---

## A. Consolidación: esquema, datos e instalación

### Migraciones formales
- [x] Convertir `fix_audit_log_delete.sql` en `011_fix_audit_log_delete.sql` y borrar el parche suelto
- [x] Corregir las claves de Santa Catarina (`19048`) y San Nicolás (`19046`) **en la fuente original** (010 dentro de `dump_completo.sql`)
- [x] `012_corrige_claves_inegi_nl.sql`: actualiza bases creadas con la versión anterior; en una instalación nueva no hace nada
- [x] Quitar el `UPDATE` correctivo de `build_regiones_sql.py` / `nl_municipios_completos.sql`
- [x] Quitar del README la explicación del error de claves (ya no existe)
- [ ] Aplicar la misma corrección y las migraciones 011/012 en los archivos `010_*.sql`… del **repositorio del equipo**
- [ ] Probar la instalación completa (`dump` → municipios → datos) en PostgreSQL 15+ real
- [ ] Migración de aprobación de escenarios (ver bloque D)
- [ ] Migración de simulación en PostgreSQL (ver bloque F)
- [ ] Registrar cada migración nueva en `schema_migrations`

### Datos oficiales
- [ ] Sustituir `POBLACION_APROX` por la población del **Censo 2020 de INEGI** para los 51 municipios (ojo: en 010, García tiene la misma población que San Nicolás, 412,199, probablemente copiada)
- [ ] Agregar la población de 60+ por municipio (se necesita para vacunación por grupo)
- [ ] Documentar la fuente de cada dataset (tabla INEGI, fecha de consulta)
- [ ] Verificar que la suma municipal coincide con el total estatal del censo

### Instalación de principio a fin
- [ ] Una base vacía se instala solo con migraciones + datos, **sin fixes extraordinarios**
- [ ] Probar la instalación completa en una máquina limpia de otro integrante
- [x] Actualizar los pasos de instalación del README (sin fixes aparte; bases viejas se actualizan re-corriendo el dump)

### Nombre del producto
- [x] README: `EPIDEMIA — Sistema Monolítico v0.1` (primera versión funcional del monolito)
- [x] Quitar "demo" como nombre del sistema en `app.py`, `queries.py`, `db.py`, `audit.py`, plantillas, `login.html` y CSS
- [x] Mantener "demo" solo para los **datos** de demostración (`demo_datos_nl.sql`, `gen_demo_data.py`)

---

## B. Catálogo de enfermedades (CRUD real)

- [ ] Listar enfermedades (ya existe)
- [ ] Crear enfermedad (ya existe, **ajustar** a parámetros con fuente)
- [ ] Editar enfermedad
- [ ] Activar / desactivar (baja lógica, no borrado)
- [ ] Parámetros mínimos: R0 / transmisibilidad, incubación, duración infecciosa, letalidad, tasa de hospitalización
- [ ] Estructura por parámetro en `default_params`: `{"valor": …, "fuente": "…", "supuesto": true|false}`
- [ ] Validación: **no se guarda un parámetro sin fuente** o sin la marca explícita de supuesto
- [ ] Mostrar en la UI qué parámetros son supuestos (etiqueta visible)
- [ ] Cargar fuentes reales para COVID-19 e Influenza estacional
- [ ] Solo `EPIDEMIOLOGO` y `ADMINISTRADOR` pueden editar parámetros
- [ ] Auditoría de crear / editar / desactivar

---

## C. Catálogo de regiones

- [ ] Vista de consulta jerárquica: Nuevo León → municipios
- [ ] Columnas: clave INEGI, nombre, población, población 60+, fuente
- [ ] Búsqueda y orden por población
- [ ] Sin aproximaciones: los datos vienen del bloque A
- [ ] (Opcional) Edición de población solo para `ADMINISTRADOR`, con auditoría

---

## D. Escenarios, versiones y aprobación

### Crear escenario (pantalla central)
- [ ] Formulario: nombre, descripción, enfermedad, región
- [ ] Población tomada de la región (editable dentro de los límites del CHECK)
- [ ] Infectados iniciales
- [ ] Duración en días (horizonte)
- [ ] Guardar crea el escenario + **versión 1**

### Intervenciones
- [ ] Agregar intervención a una versión: tipo, día inicio, día fin, cobertura, cumplimiento
- [ ] Soportar como mínimo: `CIERRE_ESCUELAS`, `REDUCCION_AFORO`, `VACUNACION` (con grupo 60+)
- [ ] Quitar / reordenar intervenciones mientras la versión es borrador
- [ ] Vista de calendario o línea de tiempo de intervenciones

### Validación
- [ ] Validar escenario antes de enviar: días dentro del horizonte, cobertura 0–1, parámetros completos, sin intervenciones duplicadas
- [ ] Mostrar errores de validación claros en la UI

### Versionamiento (obligatorio)
- [ ] Modificar **nunca sobrescribe**: crea la versión siguiente
- [ ] Cada versión guarda autor, fecha, comentario y parámetros
- [ ] Solo una versión vigente por escenario (`is_current`)
- [ ] Historial de versiones visible (Escenario 14 → v1, v2, v3)
- [ ] Ver el detalle de una versión anterior
- [ ] Duplicar escenario (crea uno nuevo desde una versión)

### Flujo de aprobación
- [ ] Migración: estados de versión `borrador → en_revision → aprobado | rechazado`
- [ ] Migración: columnas `reviewed_by`, `reviewed_at`, `review_comment`
- [ ] `ANALISTA` crea y envía a revisión
- [ ] `EPIDEMIOLOGO` aprueba o rechaza (motivo obligatorio al rechazar)
- [ ] **Regla: nadie aprueba su propia versión** (validado en backend y, si es posible, en BD)
- [ ] Una versión nueva de un escenario aprobado vuelve a `borrador`
- [ ] Solo se puede simular una versión **aprobada**
- [ ] Bandeja "Pendientes de revisión" para el epidemiólogo
- [ ] Auditoría de envío, aprobación y rechazo

---

## E. Motor de simulación de referencia (Python)

- [x] Módulo aislado `motor/` sin dependencias de Flask (candidato futuro a worker)
- [x] Modelo SEIR con compartimentos: Susceptibles, Expuestos, Infectados, Recuperados, Hospitalizados, Fallecidos (+ Vacunados protegidos)
- [x] Estocástico con semilla (misma entrada + misma semilla = mismo resultado)
- [x] `ENGINE_VERSION = "python-ref-0.1"`
- [x] Traducción de intervenciones a efectos en el modelo (los 6 tipos de `intervention_types`)
- [x] Vacunación por grupo de edad (`edad_minima`, prioridad `edad_desc`), limitada por cobertura y dosis diarias
- [x] Documentar las simplificaciones del modelo como supuestos (van en la salida de cada corrida)
- [x] Pruebas unitarias: reproducibilidad, conservación de población, validación, sin intervención vs con intervención (`python -m unittest discover -s tests -t .`)
- [x] Indicadores resumen (adelanto de F): acumulados, activos, pico, día del pico, hospitalizaciones, fallecimientos, tasa de ataque
- [ ] Sustituir la población por grupo de edad del ejemplo por datos del Censo 2020 (depende de A)
- [ ] Capturar R0, tasa de hospitalización y días de hospitalización **con fuente** en las enfermedades (depende de B)

---

## F. Ejecución, estados y resultados

### Corridas
- [ ] Migración: permitir el motor `python-ref-0.1` (hoy el CHECK solo acepta `numba`/`cuda`)
- [ ] Migración: agregar `requested_by` a `simulation_runs`
- [ ] Cada corrida guarda: run_id, scenario_id, versión, engine_version, seed, inicio, fin, usuario, parámetros, estado
- [ ] Identificador visible tipo `SIM-00042` / `ESC-003`
- [ ] Botón "Ejecutar simulación" solo en versiones aprobadas

### Estados
- [ ] `PENDIENTE → EJECUTANDO → COMPLETADA`
- [ ] `PENDIENTE → EJECUTANDO → ERROR` (con mensaje de error guardado)
- [ ] La ejecución corre en segundo plano (hilo) para que la transición sea visible
- [ ] La página consulta el estado y se actualiza sola
- [ ] Probar a propósito el camino de ERROR

### Resultados (en PostgreSQL)
- [ ] Migración: tabla de resultados (resumen + serie diaria en JSONB)
- [ ] Indicadores: casos acumulados, casos activos, pico de casos, día del pico, hospitalizaciones, fallecimientos, tasa de ataque
- [ ] Curvas temporales S, E, I, R, H, D con Highcharts
- [ ] Re-ejecutar con la misma semilla reproduce el mismo resultado (demostrable)
- [ ] Auditoría de ejecución y resultado

---

## G. Comparación y frontera de Pareto

### Comparación
- [ ] Reemplazar el stub de Comparación (quitar `comparacion` de `STUB_ITEMS`)
- [ ] Seleccionar varias corridas completadas con casillas
- [ ] Superponer curvas de casos, hospitalizaciones y fallecimientos
- [ ] Tabla comparativa: fallecimientos, pico, día del pico, tasa de ataque

### Trade-off
- [x] Costo unitario por tipo de intervención, con fuente o **marcado como supuesto** (sin valores por defecto)
- [x] Costo del escenario: unitario × población × intensidad × días activos; vacunación por dosis aplicadas (`motor/pareto.py`)
- [ ] Capturar y guardar los costos unitarios (hoy solo existen en el ejemplo de `python -m motor`)
- [ ] Gráfico impacto sanitario vs costo de intervención
- [x] Calcular y marcar escenarios **no dominados** (frontera de Pareto), con impacto evitado y costo por unidad evitada contra el escenario base
- [ ] La decisión final queda explícitamente en manos del usuario

---

## H. Integración, UX y auditoría

- [ ] Reemplazar el stub de Simulaciones (quitar `simulaciones` de `STUB_ITEMS`)
- [ ] Agregar Escenarios, Simulaciones y Comparación al menú lateral
- [ ] **Aviso permanente** en pantallas de simulación, resultados y comparación: *"Los resultados representan escenarios simulados basados en parámetros y supuestos. No constituyen una predicción epidemiológica ni una recomendación sanitaria."*
- [ ] Permisos por rol revisados en cada ruta nueva (no solo ocultar el menú)
- [ ] Auditoría consultable de todo el flujo: escenario, versiones, aprobación, corridas
- [ ] Datos de demostración: usuarios `ANALISTA` y `EPIDEMIOLOGO` distintos para probar la regla de no autoaprobación
- [ ] Mensajes de éxito / error consistentes en todos los formularios

---

## Prueba de aceptación (guion de la revisión)

Correr completo sobre una base recién instalada. Si los 22 pasos pasan, el avance está cumplido.

- [ ] 1. Entrar al portal público
- [ ] 2. Iniciar sesión como analista
- [ ] 3. Crear un escenario
- [ ] 4. Seleccionar enfermedad
- [ ] 5. Seleccionar región
- [ ] 6. Configurar población
- [ ] 7. Agregar intervenciones
- [ ] 8. Guardar versión 1
- [ ] 9. Modificar y crear versión 2
- [ ] 10. Enviar a aprobación
- [ ] 11. Entrar como epidemiólogo
- [ ] 12. Aprobar escenario
- [ ] 13. Volver como analista
- [ ] 14. Ejecutar simulación
- [ ] 15. Ver PENDIENTE → EJECUTANDO → COMPLETADA
- [ ] 16. Consultar curvas
- [ ] 17. Duplicar escenario
- [ ] 18. Cambiar intervención
- [ ] 19. Ejecutar segunda simulación
- [ ] 20. Comparar resultados
- [ ] 21. Mostrar trade-off
- [ ] 22. Consultar auditoría

Verificaciones extra:
- [ ] El analista **no** puede aprobar su propio escenario (intentarlo y ver que falla)
- [ ] Editar un escenario aprobado crea una versión nueva, no sobrescribe
- [ ] Repetir una corrida con la misma semilla da resultados idénticos
- [ ] Todo sigue ahí después de reiniciar el servidor (persistencia real)

---

## Fuera de alcance en esta etapa

- MongoDB (series, agregados, calibración)
- Redis (cola, progreso, Pub/Sub, caché, revocación JWT)
- Motor CUDA / Numba y lotes de 30+ réplicas
- Microservicios
- Modelo económico sofisticado
