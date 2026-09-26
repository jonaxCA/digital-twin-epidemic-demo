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
- [x] Población municipal por los cinco grupos de edad: tabla `region_age_groups` con los 51 municipios y el estado abiertos en 0-19, 20-39, 40-59, 60-79 y 80+ (migración `021`, generada por `datos/scripts/build_grupos_edad.py` desde el ITER 2020). Cada grupo es una **suma exacta** de columnas quinquenales publicadas: ningún límite queda partido, así que no hay reparto supuesto. Comprobado contra PostgreSQL: un escenario municipal estratificado que antes se rechazaba ahora valida y corre
- [x] **Edad no especificada**: las columnas de edad del censo dejan fuera a quien no la declaró — 18,132 personas en el estado (0.31%), en 30 de los 51 municipios. No se reparten entre los grupos, porque los cinco son dato observado y prorratearlos los volvería una imputación. Van como una sexta categoría, `edad_no_especificada`, con `lower_bound` NULL para que ninguna consulta la confunda con una banda de edad. Así la suma de **todas** las filas sí cuadra con `regions.population`
- [x] El motor exige decidir: un escenario con población sin edad declarada tiene que traer `politica_edad_desconocida` en `excluir` o `prorratear`. Prorratear se registra como **supuesto** en la trazabilidad y avisa que es una imputación; excluir avisa que los resultados cubren solo a la población con edad conocida. Sin política, el escenario no valida
- [x] `regions.population_60plus` ya no se edita a mano: pasó a derivarse de `region_age_groups` (migración `022`), así que no puede desalinearse de las bandas de edad
- [x] Solo `EPIDEMIOLOGO` y `ADMINISTRADOR` pueden editar (`roles_required`); el intento de un analista queda en la bitácora como `PERMISSION_DENIED`
- [x] Auditoría de crear / editar / activar / desactivar, con estado antes y después

---

## C. Catálogo de regiones

- [x] Vista de consulta jerárquica: Nuevo León → municipios
- [x] Columnas: clave INEGI, nombre, población, población 60+, fuente
- [x] Búsqueda y orden por población
- [x] Sin aproximaciones: los datos vienen del bloque A
- [x] (Opcional) Edición de población solo para `ADMINISTRADOR`, con auditoría — GET y POST pasan por `admin_required`, y el intento denegado queda en la bitácora
- [x] `population_60plus` es **derivada**, no un dato capturable: la mantiene el trigger `trg_rag_sincroniza_60plus` como `grupo 60-79 + grupo 80+` de `region_age_groups` (migración `022`). La pantalla la muestra de solo lectura. Mientras las dos cifras se podían editar por separado, nada impedía que la columna y las bandas de edad se contradijeran
- [ ] Corregir el 60 y más ahora significa corregir las bandas de edad, y para eso **no hay pantalla**. Si el equipo lo necesita, es una vista nueva sobre `region_age_groups`; si no, queda como dato censal fijo

---

## D. Escenarios, versiones y aprobación

### Crear escenario (pantalla central)
- [x] Formulario: nombre, descripción, enfermedad, región (`/escenarios/nuevo`, solo `ANALISTA`, `EPIDEMIOLOGO` y `ADMINISTRADOR`)
- [x] Población tomada de la región, editable dentro de los límites del CHECK. **Con una excepción:** si el escenario se abre por grupos de edad, la población deja de ser editable, porque el reparto por grupos es censal y escalarlo para cuadrarlo con un total escrito a mano lo volvería una invención
- [x] Infectados iniciales
- [x] Duración en días (horizonte)
- [x] Guardar crea el escenario + **versión 1** (`borrador`, `is_current`) en una sola transacción, con su entrada en la bitácora
- [x] Escenario abierto por grupo de edad: toma el reparto del Censo 2020 de `region_age_groups`, y lo guarda en la versión como fotografía, no como puntero a la región
- [x] El tope de población subió de 5 a 20 millones (migración `023`). Con el anterior, **Nuevo León completo era imposible de guardar** — 5,784,442 habitantes — y es el primer escenario que alguien va a pedir
- [x] Listado de escenarios con su versión vigente, estado, población y autor, con búsqueda

### Intervenciones
- [x] Agregar intervención a una versión: tipo, día inicio, día fin, cobertura y cumplimiento, en el detalle del escenario (`/escenarios/<id>`)
- [x] Soporta **los seis** tipos del catálogo, no solo los tres del mínimo: el formulario de parámetros se genera desde `intervention_types.param_schema`, que es JSON Schema. Agregar un séptimo tipo es una fila en el catálogo, no código nuevo
- [x] `VACUNACION` con grupo 60+ funciona, y el motor **exige** que el escenario esté abierto por grupos de edad para una prioridad por edad: sin grupos la rechaza en vez de aplicarla a ciegas
- [x] Quitar y reordenar mientras la versión es borrador. Quitar cierra el hueco del `order_index`, para que «mover una posición» siga siendo predecible
- [x] Línea de tiempo de intervenciones sobre el horizonte de la versión, en porcentajes: sin JavaScript y sin depender de cuántos días sean
- [x] Editar pide tres cosas a la vez: el rol, que la versión siga en **borrador**, y ser dueño del escenario o `ADMINISTRADOR`. Cambiar una versión ya enviada dejaría al revisor aprobando algo que ya no existe
- [x] Los **avisos** del motor se muestran, no solo los errores: ahí es donde dice, por ejemplo, que una prioridad de vacunación no la modela un compartimental y se degrada a aleatoria. Sin mostrarlos, el usuario cree que pidió algo que no está pasando

### Validación
- [x] El alta se contrasta contra el motor antes de guardar: días dentro del horizonte y parámetros de enfermedad completos. Los límites del formulario se **importan** de `motor.parametros` en vez de copiarse, para que la pantalla no pueda aceptar algo que la corrida rechaza
- [x] Cobertura y cumplimiento 0–1, y los parámetros de cada tipo validados contra su propio `param_schema` (mínimos, máximos, enumeraciones y obligatorios)
- [x] Sin intervenciones duplicadas: se rechaza el **traslape** de dos del mismo tipo, que es más amplio que el índice único de la base (`uq_scenario_interventions_unica`, que solo atrapa el mismo tipo empezando el mismo día). Dos cierres de escuelas encimados contarían su efecto dos veces
- [x] Mostrar errores de validación claros en la UI: los del formulario y los del motor se muestran por separado, porque hablan de cosas distintas (un campo vacío contra un parámetro epidemiológico faltante)

### Versionamiento (obligatorio)
- [x] Modificar **nunca sobrescribe**: `/escenarios/<id>/versiones/nueva` crea la siguiente y la anterior queda intacta. Las intervenciones se **copian** a la nueva; si hubiera que recapturarlas, nadie versionaría nada
- [x] Cada versión guarda autor, fecha, comentario y parámetros. El **comentario es obligatorio**: un historial sin el motivo de cada cambio no explica cómo llegó el escenario a donde está
- [x] La versión nueva nace en `borrador` aunque la anterior estuviera aprobada, y apagar la vigente anterior va en la misma transacción que prender la nueva — `uq_scenario_versions_vigente` no admite dos
- [x] Solo una versión vigente por escenario, comprobado con una prueba que crea cuatro
- [x] Historial de versiones en el detalle: número, estado, población, horizonte, infectados, cuántas intervenciones, autor, fecha y comentario
- [x] Ver una versión anterior (`?version=N`), de **solo lectura** y con aviso de que no es la vigente
- [x] Duplicar desde cualquier versión: crea un escenario nuevo con sus intervenciones, del que duplica, en `borrador` y con versión 1. No hereda el estado de aprobación, porque nadie ha revisado la copia, y no toca el original
- [x] La versión **congela los parámetros de la enfermedad** al salir de borrador (`scenario_versions.disease_params`, migración `024`). Mientras es borrador usa los vivos del catálogo, que es coherente con que todo lo demás de un borrador se pueda cambiar; en el envío a revisión se congelan. La regla es una línea: **editable ⇔ parámetros vivos, congelada ⇔ su fotografía**. Así todo lo revisable y todo lo simulable queda explicándose a sí mismo, y corregir el catálogo ya no cambia el significado de lo aprobado
- [x] Adoptar un parámetro corregido es crear la versión siguiente: nace borrador y vuelve a tomar los vivos. La anterior conserva la suya. Las versiones que salieron de borrador **antes** de la `024` tienen `disease_params` en NULL. No se rellenan con los parámetros de hoy porque eso afirmaría algo no verificable; la pantalla lo advierte. Afecta solo al escenario de demostración

### Flujo de aprobación
- [x] Migración `013`: estados de versión `borrador → en_revision → aprobado | rechazado`
- [x] Migración `013`: columnas `submitted_at`, `reviewed_by`, `reviewed_at`, `review_comment`, con CHECK de coherencia (rechazar exige motivo)
- [x] `ANALISTA` crea y envía a revisión: `POST /escenarios/<id>/enviar`, solo para quien creó el escenario (o `ADMINISTRADOR`). Al enviarla la versión deja de ser editable
- [x] Antes de aceptar el envío se vuelve a contrastar con el motor: mandar a revisar algo que no se puede simular le hace perder el tiempo a quien revisa
- [x] `EPIDEMIOLOGO` aprueba o rechaza desde el detalle. Rechazar **exige motivo** — lo pide el CHECK de la base y es lo único que tiene quien va a corregir
- [x] Una versión rechazada no se corrige: se crea la siguiente, que nace en borrador con las intervenciones copiadas. La rechazada queda con su motivo y su revisor
- [x] **Nadie aprueba su propia versión**: `ck_scenario_versions_no_autoaprobacion` lo impide en la base
- [x] En el backend se exige el rol `EPIDEMIOLOGO` para dictaminar, y **solo ese**: el `ADMINISTRADOR` ve la bandeja pero no aprueba, porque quien opera el sistema no es quien valida la epidemiología. El intento de un analista queda en la bitácora como `PERMISSION_DENIED`
- [x] **Nadie revisa su propia versión.** La base lo impide (`ck_scenario_versions_no_autoaprobacion`) y la aplicación lo dice antes, con un mensaje útil en vez de un error de restricción
- [x] Una versión nueva de un escenario aprobado vuelve a `borrador` (es el default de la columna)
- [x] **Solo se simula una versión aprobada**: el trigger `fn_version_aprobada` (014) rechaza corridas sobre cualquier otro estado
- [x] Bandeja «Pendientes de revisión» (`/revisiones`), la que lleva más tiempo esperando primero. Marca las versiones que el propio revisor escribió, para que no las intente dictaminar
- [x] Auditoría de envío, aprobación y rechazo: cada cambio de estado deja el antes y el después en `audit_log`, dentro de la misma transacción que el cambio. Verificado que las tres entidades nuevas (`scenarios`, `scenario_versions`, `scenario_interventions`) se consultan desde la pantalla de Auditoría
- [x] La política de edad desconocida se elige en el formulario y se guarda en la versión (`age_unknown_policy`). El CHECK la exige cuando hay gente sin edad y la prohíbe cuando no; no hay valor por omisión

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
- [ ] Agregar Simulaciones y Comparación al menú lateral. **Escenarios** y **Revisiones** ya están (Revisiones solo para `EPIDEMIOLOGO` y `ADMINISTRADOR`)
- [ ] **Aviso permanente** en pantallas de simulación, resultados y comparación: *"Los resultados representan escenarios simulados basados en parámetros y supuestos. No constituyen una predicción epidemiológica ni una recomendación sanitaria."*
- [ ] Permisos por rol revisados en cada ruta nueva (no solo ocultar el menú)
- [x] Prueba de humo de **todas** las rutas (`frontend_web/tests/test_rutas_humo.py`): recorre el mapa de Flask y pide cada GET, más el POST de captura de casos. Existe porque una función nueva en `queries.py` se llamó igual que otra con distinta firma, `/reportes/nuevo` empezó a responder 500 y ninguna suite lo notó — cubrían regiones, enfermedades y escenarios, pero nadie pedía esa ruta
- [x] Prueba de integridad de módulos (`backend_web/tests/test_integridad.py`): ningún archivo puede definir dos veces el mismo nombre de nivel superior. Python se queda con el último y el archivo compila igual, así que el error solo aparece al usar la pantalla afectada
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
