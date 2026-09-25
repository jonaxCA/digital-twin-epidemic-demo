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

- [x] El proyecto vive en **su propio repositorio** (no dentro de la carpeta de usuario)
- [x] Asignar un responsable a cada bloque A–H
- [x] Crear un issue por cada casilla de este documento
- [x] Regla: una rama por issue (`feat/escenarios-versionado`, `fix/claves-inegi`, …)
- [x] Regla: todo entra por Pull Request revisado por otro integrante, nada directo a `main`
- [x] Regla: commits pequeños e incrementales, con el autor correcto configurado en git
- [x] Acordar la convención de nombres de migraciones: `011_…sql`, `012_…sql`, …
- [ ] El `.tar.gz` de entrega incluye la carpeta `.git`

---

## A. Consolidación: esquema, datos e instalación

### Migraciones formales
- [x] Convertir `fix_audit_log_delete.sql` en `011_fix_audit_log_delete.sql` y borrar el parche suelto
- [x] Corregir las claves de Santa Catarina (`19048`) y San Nicolás (`19046`) **en la fuente original** (010 dentro de `dump_completo.sql`)
- [x] `012_corrige_claves_inegi_nl.sql`: actualiza bases creadas con la versión anterior; en una instalación nueva no hace nada
- [x] Quitar el `UPDATE` correctivo de `build_regiones_sql.py` / `nl_municipios_completos.sql`
- [x] Quitar del README la explicación del error de claves (ya no existe)
- [x] Aplicar la corrección y las migraciones en el **repositorio del equipo**: no había archivos `010_*.sql` sueltos que sincronizar — el esquema vive en `db/dump_completo.sql` (que ya trae la corrección dentro del bloque 010) y las migraciones nuevas están como archivos individuales en `db/migraciones/`
- [x] Probar la instalación completa (`dump` → municipios → datos) en PostgreSQL real — **PostgreSQL 18.6**, 51 municipios, 3,824 casos, claves INEGI correctas sin parches
- [x] `013_escenarios_aprobacion.sql`: flujo de aprobación por versión + infectados iniciales (bloque D)
- [x] `014_simulacion_resultados.sql`: motor de referencia, resultados en PostgreSQL y costos de intervención (bloques F y G)
- [x] Registrar cada migración nueva en `schema_migrations` (001–014 quedan registradas)
- [x] **Ejecutar 013 y 014 contra PostgreSQL real**: aplicadas sin errores sobre una base existente (relleno de `requested_by` en 100 corridas incluido); 18 pruebas de las reglas nuevas pasan

### Datos oficiales
- [x] **Población del Censo 2020 para los 51 municipios** (`data/censo/nl_poblacion_municipios_1990_2020.tsv`). Las aproximaciones estaban mal hasta en **82%** (Pesquería 26,000 vs 147,624). También se corrigieron 4 de los 10 municipios de `010`, incluido García, que traía la población de San Nicolás copiada
- [x] Migración `015_poblacion_censo_2020.sql` para las bases ya creadas; aplicada y verificada: los 51 municipios coinciden con el censo y su suma da el total estatal
- [x] Estructura por edad del estado (`data/censo/nl_estructura_edad_2020.tsv`): los 21 grupos quinquenales. **60 años y más = 654,050, el 11.31%**. El ejemplo del motor ya la usa en vez de proporciones inventadas
- [x] **Población 60+ por municipio** (`data/censo/nl_poblacion_60mas_2020.tsv`), del ITER 2020 de INEGI. Migración `016` agrega la columna `regions.population_60plus`. Validado dos veces: los 51 POBTOT coinciden con el otro tabulado y la suma da 654,050, idéntica al total estatal. La proporción va de **2.7% (El Carmen) a 28.8% (Los Herreras)**, así que el promedio estatal habría estado mal por un factor de diez
- [x] Documentar la fuente de cada dataset: el encabezado de cada archivo en `data/censo/` trae el tabulado exacto, la fecha de consulta y de dónde salió cada cifra (incluidos los tres municipios que el export cortó)
- [x] Verificar que la suma municipal coincide con el total estatal del censo: cuadra en los **siete** años censales, y el generador lo revisa en cada corrida en vez de confiar en que alguien lo comprobó una vez

### Instalación de principio a fin
- [x] Sin pasos extraordinarios: la instalación son **3 comandos** (`dump` → municipios → datos). Se eliminó `admin_password.sql`; las tres cuentas quedan listas con los datos de demostración, y el esquema solo sigue creando `admin` con el marcador inválido
- [x] Probarlo **desde cero** sobre una base recién creada — verificado por el equipo: la instalación completa corre de principio a fin sin pasos extraordinarios
- [x] Probar la instalación completa en una máquina limpia de otro integrante
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
- [x] **Fuentes reales cargadas para COVID-19 e Influenza**: ambas quedaron **simulables**, con 4 parámetros con referencia publicada y 2 marcados como supuesto en cada una. Cada cifra se verificó en el texto de su fuente antes de capturarla. Las dos tasas de influenza son derivadas (CDC cuenta por caso sintomático y el motor necesita por infección), por eso van marcadas como supuesto con la conversión explicada
- [x] Migración `017_parametros_enfermedades.sql`: los parámetros quedan en el repositorio, no solo en la base de quien los capturó. Fusiona con `||` (respeta `letalidad_por_edad` y demás) y no pisa lo que alguien ya haya capturado desde la pantalla
- [x] (Opcional, mejora) Letalidad **por grupo de edad** con fuente, en vez del promedio: COVID-19 de Verity et al. 2020 (tabla 1, verificada contra el texto completo y contra sus dos fe de erratas, que no la tocan) e influenza del CDC 2019-2020 por grupo de edad, de la misma revisión de la que salen los valores globales del catálogo. Ambas reagrupadas a los cinco grupos del motor ponderando por la estructura de edad de Nuevo León, y por eso marcadas como supuesto: el reagrupamiento es aritmética del equipo, no un dato publicado. Migración `020_letalidad_por_edad.sql`, generada por `datos/scripts/build_letalidad_edad.py`
- [x] Corregido de paso: el motor **aceptaba** `letalidad_por_edad` pero la letalidad global le ganaba siempre, así que la tabla nunca se aplicaba. Ahora manda la tabla cuando la población viene abierta por grupos de edad
- [ ] Población municipal por los cinco grupos de edad: hoy `regions` solo guarda total y 60+, así que un escenario municipal estratificado se rechaza porque los grupos no coinciden con los de la tabla de letalidad. El ITER 2020 que ya descargamos trae las columnas quinquenales por municipio; solo extrajimos `P_60YMAS`. **Conviene resolverlo antes del bloque D**, porque los escenarios se arman sobre municipios
- [x] Solo `EPIDEMIOLOGO` y `ADMINISTRADOR` pueden editar (`roles_required`); el intento de un analista queda en la bitácora como `PERMISSION_DENIED`
- [x] Auditoría de crear / editar / activar / desactivar, con estado antes y después

---

## C. Catálogo de regiones

- [x] Vista de consulta jerárquica: Nuevo León → municipios
- [x] Columnas: clave INEGI, nombre, población, población 60+, fuente
- [x] Búsqueda y orden por población
- [x] Sin aproximaciones: los datos vienen del bloque A
- [x] (Opcional) Edición de población solo para `ADMINISTRADOR`, con auditoría

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
- [x] Sustituir la población por grupo de edad del ejemplo por datos del Censo 2020: `python -m motor` ya reparte con la estructura real del estado
- [x] COVID-19 ancestral e influenza estacional: los seis parámetros con fuente publicada o con la marca explícita de supuesto (migraciones `017` y `020`). Las dos quedaron **simulables**
- [ ] Dengue, malaria y zika: faltan R0, tasa de hospitalización, días de hospitalización y letalidad; incubación y período infeccioso ya están pero **sin fuente**. **Ojo antes de capturar**: las tres se transmiten por vector y el motor es un SEIR de persona a persona con capas de contacto, así que un R0 bien citado igual produce una simulación segura y equivocada, y `CIERRE_ESCUELAS` o `REDUCCION_AFORO` no actúan como el modelo supone. Decidir primero: se simulan con este motor asumiéndolo, se marcan como no simulables, o esperan a un modelo con vector
- [ ] Añadir a `SIMPLIFICACIONES` del motor que el modelo asume **transmisión directa persona a persona**; hoy la lista no lo dice
- [ ] Patógeno X: es hipotético y no tiene literatura que buscar. Definir en equipo qué escenario representa (¿más transmisible que COVID? ¿más letal?); sus seis parámetros van como supuesto por diseño, no por falta de trabajo

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
