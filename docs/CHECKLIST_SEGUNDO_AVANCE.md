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
- [x] Aplicar la misma corrección y las migraciones 011/012 en los archivos `010_*.sql`… del **repositorio del equipo**
- [x] Probar la instalación completa (`dump` → municipios → datos) en PostgreSQL real — **PostgreSQL 18.6**, 51 municipios, 3,824 casos, claves INEGI correctas sin parches
- [x] `013_escenarios_aprobacion.sql`: flujo de aprobación por versión + infectados iniciales (bloque D)
- [x] `014_simulacion_resultados.sql`: motor de referencia, resultados en PostgreSQL y costos de intervención (bloques F y G)
- [x] Registrar cada migración nueva en `schema_migrations` (001–014 quedan registradas)
- [x] **Ejecutar 013 y 014 contra PostgreSQL real**: aplicadas sin errores sobre una base existente (relleno de `requested_by` en 100 corridas incluido); 18 pruebas de las reglas nuevas pasan

### Datos oficiales
- [ ] Sustituir `POBLACION_APROX` por la población del **Censo 2020 de INEGI** para los 51 municipios (ojo: en 010, García tiene la misma población que San Nicolás, 412,199, probablemente copiada)
- [ ] Agregar la población de 60+ por municipio (se necesita para vacunación por grupo)
- [ ] Documentar la fuente de cada dataset (tabla INEGI, fecha de consulta)
- [ ] Verificar que la suma municipal coincide con el total estatal del censo

### Instalación de principio a fin
- [x] Sin pasos extraordinarios: la instalación son **3 comandos** (`dump` → municipios → datos). Se eliminó `admin_password.sql`; las tres cuentas quedan listas con los datos de demostración, y el esquema solo sigue creando `admin` con el marcador inválido
- [ ] Probarlo **desde cero** sobre una base recién creada — lo verificado hasta ahora fue una *actualización* (001–012 ya existían y el dump agregó 013/014)
- [ ] Probar la instalación completa en una máquina limpia de otro integrante
- [x] Actualizar los pasos de instalación del README (sin fixes aparte; bases viejas se actualizan re-corriendo el dump)

### Nombre del producto
- [x] README: `EPIDEMIA — Sistema Monolítico v0.1` (primera versión funcional del monolito)
- [x] Quitar "demo" como nombre del sistema en `app.py`, `queries.py`, `db.py`, `audit.py`, plantillas, `login.html` y CSS
- [x] Mantener "demo" solo para los **datos** de demostración (`demo_datos_nl.sql`, `gen_demo_data.py`)

---

## B. Catálogo de enfermedades (CRUD real)

- [x] Listar enfermedades, ahora con columna de **Parámetros** (simulable / cuántos faltan / cuántos son supuestos)
- [x] Crear enfermedad, con parámetros opcionales desde el alta
- [x] Editar enfermedad (`/enfermedades/<id>/editar`); el código no se edita porque es la llave con la que ya están ligados casos y escenarios
- [x] Activar / desactivar (baja lógica, nunca `DELETE`)
- [x] Los **seis parámetros** que el motor exige: R0, incubación, período infeccioso, estancia hospitalaria, tasa de hospitalización y letalidad
- [x] Estructura por parámetro en `default_params`: `{"valor": …, "fuente": "…", "supuesto": true|false}`, conservando las claves que el formulario no edita (`transmisibilidad_base`, `letalidad_por_edad`…)
- [x] Validación: **no se guarda un parámetro sin fuente** o sin la marca explícita de supuesto
- [x] Mostrar en la UI qué parámetros son supuestos, cuáles no tienen fuente y cuáles faltan
- [ ] **Cargar fuentes reales para COVID-19 e Influenza** — lo tiene que hacer una persona del equipo: elegir la referencia y verificarla. El formulario ya está listo para capturarlas
- [x] Solo `EPIDEMIOLOGO` y `ADMINISTRADOR` pueden editar (`roles_required`); el intento de un analista queda en la bitácora como `PERMISSION_DENIED`
- [x] Auditoría de crear / editar / activar / desactivar, con estado antes y después

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
- [x] Migración `013`: estados de versión `borrador → en_revision → aprobado | rechazado`
- [x] Migración `013`: columnas `submitted_at`, `reviewed_by`, `reviewed_at`, `review_comment`, con CHECK de coherencia (rechazar exige motivo)
- [ ] `ANALISTA` crea y envía a revisión (pantallas)
- [ ] `EPIDEMIOLOGO` aprueba o rechaza (pantallas)
- [x] **Nadie aprueba su propia versión**: `ck_scenario_versions_no_autoaprobacion` lo impide en la base
- [ ] En el backend, exigir además el rol `EPIDEMIOLOGO` al aprobar
- [x] Una versión nueva de un escenario aprobado vuelve a `borrador` (es el default de la columna)
- [x] **Solo se simula una versión aprobada**: el trigger `fn_version_aprobada` (014) rechaza corridas sobre cualquier otro estado
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
- [ ] Capturar R0, tasa de hospitalización y días de hospitalización **con fuente** en las enfermedades — la pantalla ya existe (bloque B); hoy a las 6 enfermedades del catálogo les faltan entre 3 y 6 parámetros, así que **ninguna se puede simular todavía**

---

## F. Ejecución, estados y resultados

### Corridas
- [x] Migración `014`: motor `python-ref` admitido y lotes desde 1 réplica (antes el mínimo eran 30)
- [x] Migración `014`: `requested_by` en `simulation_runs`, con relleno desde el lote para bases existentes
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
- [x] Migración `014`: tabla `simulation_results` (resumen + serie diaria en JSONB, con columnas generadas para los indicadores y la huella del escenario)
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
- [x] Columnas para el costo en `intervention_types` (`014`), con la regla de que un costo sin fuente debe marcarse como supuesto
- [ ] Capturar los importes (la migración deja la unidad de cada tipo, pero el costo en NULL a propósito) y una pantalla para editarlos
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
- [x] Datos de demostración: `alex.cavazos` (ANALISTA) y `diana.flores` (EPIDEMIOLOGO); el escenario de la demo ya viene creado por uno y aprobado por la otra
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
