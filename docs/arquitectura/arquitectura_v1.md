> **Estado: Vigente, con excepciones** · convertido el 2026-09-25
> Vale para los principios, las fronteras de datos y la forma final del sistema.
> Quedó desactualizado en:
> - 3.1: en este avance, escenarios, versiones, aprobación y comparación se construyen en la web.
>   El reparto con la app de escritorio está en discusión.
> - 4.1 y 8: marshmallow y flask-smorest no están confirmados.
> - 5.1: el esquema real está en `datos/postgres/migraciones/` (incluye `simulation_results`,
>   el flujo de aprobación por versión y los costos de `intervention_types`).
> - 5.2: mientras sea monolito, los resultados van en `simulation_results` (PostgreSQL), no en MongoDB.
> - 6.2: el motor actual es un SEIR de prueba; el acelerado será FLAME GPU, no CUDA propio.
> - 9.5: los contratos (OpenAPI, XSD) se definen en el segundo parcial.
> - 10: este avance es un monolito Flask + PostgreSQL; MongoDB, Redis y microservicios quedan fuera.
> Cuando se publique el v2, este archivo pasa a **Histórico**.


# **La Arquitectura y stack tecnológico** {#la-arquitectura-y-stack-tecnológico}

**Documento de proyecto — v1** Simulador de respuesta a epidemias · Prácticas de investigación \+ Integración de Aplicaciones Computacionales

[**La Arquitectura y stack tecnológico	1**](#la-arquitectura-y-stack-tecnológico)

[1\. Principios de diseño	2](#1.-principios-de-diseño)

[2\. Vista general	2](#2.-vista-general)

[3\. Capa de clientes	3](#3.-capa-de-clientes)

[3.1 Sistema web	3](#3.1-sistema-web)

[3.2 Aplicación Android	4](#3.2-aplicación-android)

[3.3 Aplicación de escritorio	5](#3.3-aplicación-de-escritorio)

[4\. Capa de microservicios	5](#4.-capa-de-microservicios)

[4.1 Convenciones obligatorias en todos los servicios	6](#4.1-convenciones-obligatorias-en-todos-los-servicios)

[4.2 Endpoints principales	7](#4.2-endpoints-principales)

[4.3 Servicio de monitoreo	8](#4.3-servicio-de-monitoreo)

[5\. Capa de datos	9](#5.-capa-de-datos)

[5.1 PostgreSQL — datos transaccionales estructurados	9](#5.1-postgresql-—-datos-transaccionales-estructurados)

[5.2 MongoDB — documentos y series	9](#5.2-mongodb-—-documentos-y-series)

[5.3 Redis — temporal y rápido	9](#5.3-redis-—-temporal-y-rápido)

[5.4 Google Cloud Storage	10](#5.4-google-cloud-storage)

[6\. Procesamiento asíncrono	10](#6.-procesamiento-asíncrono)

[6.1 Ciclo de vida de un trabajo	10](#6.1-ciclo-de-vida-de-un-trabajo)

[6.2 El motor de simulación	11](#6.2-el-motor-de-simulación)

[7\. Infraestructura y despliegue	11](#7.-infraestructura-y-despliegue)

[7.1 Contenedores	11](#7.1-contenedores)

[7.2 Entornos	12](#7.2-entornos)

[7.3 Red y seguridad	12](#7.3-red-y-seguridad)

[7.4 Máquinas	12](#7.4-máquinas)

[7.5 Integración continua	12](#7.5-integración-continua)

[7.6 Pruebas de carga	12](#7.6-pruebas-de-carga)

[8\. Stack tecnológico completo	13](#8.-stack-tecnológico-completo)

[9\. Decisiones abiertas	14](#9.-decisiones-abiertas)

[10\. Orden de construcción	14](#10.-orden-de-construcción)

## **1\. Principios de diseño** {#1.-principios-de-diseño}

Cuatro reglas que explican por qué el sistema está armado así. Si en algún momento hay duda sobre dónde poner algo, se resuelve con estas.

**1\. Los clientes no tocan las bases de datos.** Ni la app móvil, ni la de escritorio, ni siquiera el sistema web acceden directo a PostgreSQL, MongoDB o Redis. Todo pasa por microservicios. Esto no es burocracia: es lo que evita que la misma regla de negocio esté escrita en tres lugares distintos y se desincronice.

**2\. Una responsabilidad por servicio.** Cada microservicio hace una cosa. Si el servicio de escenarios se cae, la captura de casos desde campo sigue funcionando.

**3\. Lo lento va a una cola.** Una petición HTTP responde en segundos; una simulación tarda minutos. Nunca se ejecuta trabajo pesado dentro de una petición. Se encola, se devuelve un identificador, y el cliente consulta después.

**4\. El motor de simulación está aislado.** No conoce HTTP, ni sesiones, ni usuarios. Solo sabe sacar trabajos de una cola y escribir resultados. Esto permite reemplazarlo completo sin tocar nada más.

---

## **2\. Vista general** {#2.-vista-general}

```
┌─────────────────────────────────────────────────────────────┐
│  CAPA DE CLIENTES                                           │
│  Sistema web (Flask+Jinja2) · Android (Kotlin) · Escritorio │
└────────────────────────┬────────────────────────────────────┘
                         │  HTTPS + JWT
┌────────────────────────▼────────────────────────────────────┐
│  PUERTA DE ENTRADA — Nginx                                  │
│  TLS, enrutamiento por ruta, límites de consumo             │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  CAPA DE MICROSERVICIOS (Flask, un contenedor c/u)          │
│  auth · catalog · scenario · simulation                     │
│  surveillance · analytics · monitoring                      │
└──────┬──────────────────────────────────┬───────────────────┘
       │                                  │
       │                          ┌───────▼────────┐
       │                          │  COLA (Redis)  │
       │                          └───────┬────────┘
       │                                  │
       │                          ┌───────▼─────────────────┐
       │                          │  MOTOR DE SIMULACIÓN    │
       │                          │  C++/CUDA · contenedor  │
       │                          └───────┬─────────────────┘
       │                                  │
┌──────▼──────────────────────────────────▼───────────────────┐
│  CAPA DE DATOS                                              │
│  PostgreSQL · MongoDB · Redis · Google Cloud Storage        │
└─────────────────────────────────────────────────────────────┘
```

---

## **3\. Capa de clientes** {#3.-capa-de-clientes}

### **3.1 Sistema web** {#3.1-sistema-web}

**Stack:** Python 3.12, Flask, Jinja2, HTML5, CSS3, JavaScript, Highcharts

Es el núcleo administrativo. Funciona de manera independiente: si la app móvil y la de escritorio están caídas, el sistema web sigue operando.

**Sitio público** (sin autenticación): descripción del proyecto, escenarios publicados, tablero de indicadores agregados de acceso libre.

**Portal privado** (autenticado):

| Módulo | Contenido |
| ----- | ----- |
| Tablero de control | Curvas epidémicas con Highcharts, mapa de incidencia por zona, indicadores del día |
| Administración de usuarios | Alta, baja, edición, restablecimiento de contraseña |
| Roles y permisos | Cuatro perfiles: administrador, epidemiólogo, analista, capturista |
| Catálogos | Enfermedades, regiones, tipos de intervención, parámetros base |
| Escenarios | Consulta y publicación (la edición pesada vive en escritorio) |
| Reportes | Generación y descarga |
| Bitácora de auditoría | Quién hizo qué, cuándo, desde dónde |
| Gestión de archivos | Evidencias, exportaciones, reportes |
| Notificaciones | Avisos de corridas terminadas y umbrales rebasados |
| Configuración | Parámetros del sistema |
| Registro de errores | Eventos y fallas |

**Nota de arquitectura:** el sistema web consume los microservicios igual que cualquier otro cliente. No tiene acceso privilegiado a la base de datos.

### **3.2 Aplicación Android** {#3.2-aplicación-android}

**Stack:** Kotlin, Retrofit (HTTP), Room (base local), CameraX, ML Kit (lectura de QR y códigos de barras), WorkManager (sincronización)

Consume **exclusivamente JSON**. Nunca accede a PostgreSQL, MongoDB ni Redis.

| Función | Detalle |
| ----- | ----- |
| Autenticación | Login con JWT, renovación automática de token |
| Registro de casos | Formulario con validación local |
| Geolocalización | Coordenadas automáticas del reporte |
| Cámara | Evidencia fotográfica adjunta |
| Escaneo | QR de lotes de vacuna y códigos de barras de kits de prueba |
| Modo sin conexión | Cola local en Room, sincronización posterior con WorkManager |
| Notificaciones | Avisos push de alertas y asignaciones |
| Registro de dispositivo | Identificador seguro por dispositivo |

**Estrategia offline:** cada registro se guarda primero en Room con estado `pendiente` y un identificador generado en el dispositivo. WorkManager reintenta el envío cuando hay red. El identificador local viaja al servidor para evitar duplicados si un envío se repite.

### **3.3 Aplicación de escritorio** {#3.3-aplicación-de-escritorio}

**Stack:** Python \+ PySide6 recomendado

Consume **exclusivamente XML**. Se eligió PySide porque el equipo ya trabaja Python en el backend — no hay que aprender un lenguaje más.

| Función | Detalle |
| ----- | ----- |
| Autenticación | JWT, validación de sesión contra Redis vía microservicio |
| Editor de escenarios | Carga, edición y guardado de definiciones en XML |
| Lanzamiento por lotes | Encola decenas de corridas de una vez |
| Comparador | Curvas superpuestas, frontera de eficiencia |
| Mapa 2D | Incidencia por zona geográfica |
| Reportes | Generación, exportación e impresión |
| Registro de actividades | Bitácora local de operaciones |

**Por qué XML aquí tiene sentido:** un escenario es una estructura jerárquica (población, parámetros de enfermedad, calendario de intervenciones, condiciones iniciales). Los formatos de configuración de simuladores epidemiológicos son tradicionalmente XML. El requisito de la materia coincide con la práctica del área.

---

## **4\. Capa de microservicios** {#4.-capa-de-microservicios}

Siete servicios, cada uno en su contenedor, desplegable y actualizable de forma individual.

| Servicio | Responsabilidad | Almacenamiento |
| ----- | ----- | ----- |
| `auth-service` | Login, emisión y renovación de JWT, revocación, permisos | PostgreSQL \+ Redis |
| `catalog-service` | Enfermedades, regiones, tipos de intervención, parámetros base | PostgreSQL |
| `scenario-service` | CRUD y versionado de escenarios, validación, exportación XML | PostgreSQL \+ GCS |
| `simulation-service` | Encola corridas, consulta estado y progreso, entrega resultados | Redis \+ MongoDB |
| `surveillance-service` | Ingesta de casos de campo, evidencias, lotes escaneados, deduplicación | PostgreSQL \+ MongoDB \+ GCS |
| `analytics-service` | Agregaciones, comparación de escenarios, series para gráficas | MongoDB \+ Redis |
| `monitoring-service` | Sondeo de salud de todos los servicios, historial de disponibilidad | MongoDB |

### **4.1 Convenciones obligatorias en todos los servicios** {#4.1-convenciones-obligatorias-en-todos-los-servicios}

**Versionado de API.** Todas las rutas bajo `/api/v1/`. Un cambio incompatible crea `/api/v2/` y `v1` se mantiene funcionando.

**Autenticación.** Todo endpoint protegido valida el JWT y consulta Redis para verificar que el token no haya sido revocado.

**Negociación de contenido.** Un solo esquema por recurso, dos formatos de salida según el header `Accept`:

```
Accept: application/json  →  Android
Accept: application/xml   →  Escritorio
```

Se implementa con marshmallow (esquema → diccionario) y luego serialización a JSON o XML. **Una sola definición del recurso, dos representaciones.** Esto es lo que evita duplicar la lógica.

**Validación de entradas.** Toda petición se valida contra un esquema marshmallow antes de tocar la lógica de negocio.

**Manejo de errores.** Códigos HTTP consistentes y cuerpo de error uniforme:

| Código | Uso |
| ----- | ----- |
| 400 | Datos mal formados |
| 401 | Sin token o token inválido |
| 403 | Token válido, permisos insuficientes |
| 404 | Recurso inexistente |
| 409 | Conflicto (duplicado, versión desactualizada) |
| 422 | Datos bien formados pero semánticamente inválidos |
| 429 | Límite de consumo excedido |
| 500 | Error interno |

**Identificadores de correlación.** Cada petición recibe un `X-Correlation-ID` (generado por Nginx si no viene). Se propaga a todas las llamadas internas y se escribe en cada línea de bitácora. Permite rastrear una operación completa a través de varios servicios.

**Límites de consumo.** Flask-Limiter con backend en Redis. Límites diferenciados: la ingesta desde campo es más permisiva, el lanzamiento de simulaciones es restrictivo.

**Registro de peticiones.** Método, ruta, código de respuesta, duración, usuario e identificador de correlación, en formato estructurado.

**Endpoints de salud.** Los seis exigidos, en todos los servicios:

```
/health/live       ¿el proceso responde?
/health/ready      ¿puede atender tráfico?
/health/database   ¿PostgreSQL responde?
/health/redis      ¿Redis responde?
/health/mongodb    ¿MongoDB responde?
/health/storage    ¿Cloud Storage responde?
```

**Documentación.** OpenAPI generado automáticamente con flask-smorest, que deriva la especificación de los mismos esquemas marshmallow que se usan para validar. Interfaz Swagger en `/api/v1/docs`.

### **4.2 Endpoints principales** {#4.2-endpoints-principales}

```
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout

GET    /api/v1/catalogs/diseases
GET    /api/v1/catalogs/regions
GET    /api/v1/catalogs/interventions

GET    /api/v1/scenarios
POST   /api/v1/scenarios
GET    /api/v1/scenarios/{id}
PUT    /api/v1/scenarios/{id}
GET    /api/v1/scenarios/{id}/export      (XML)

POST   /api/v1/simulations                 → devuelve job_id
GET    /api/v1/simulations/{job_id}        → estado y progreso
GET    /api/v1/simulations/{job_id}/results
POST   /api/v1/simulations/batch           → ensamble de N corridas

POST   /api/v1/surveillance/cases
POST   /api/v1/surveillance/sync           → lote desde móvil
POST   /api/v1/surveillance/cases/{id}/evidence

GET    /api/v1/analytics/curves
GET    /api/v1/analytics/compare?scenarios=a,b,c
GET    /api/v1/analytics/frontier

GET    /api/v1/monitoring/status
GET    /api/v1/monitoring/history
```

### **4.3 Servicio de monitoreo** {#4.3-servicio-de-monitoreo}

Sondea los endpoints de salud de todos los demás cada 30 segundos y expone:

* Servicios disponibles, degradados y caídos  
* Tiempo promedio de respuesta por servicio  
* Último error registrado  
* Cuál dependencia provocó la falla (si `/health/redis` falla, se reporta Redis, no el servicio)  
* Historial de disponibilidad

**Definición de estados:** *disponible* \= `/health/ready` responde 200\. *Degradado* \= responde 200 pero alguna dependencia secundaria falla, o el tiempo de respuesta supera el umbral. *Caído* \= no responde o responde error.

---

## **5\. Capa de datos** {#5.-capa-de-datos}

### **5.1 PostgreSQL — datos transaccionales estructurados** {#5.1-postgresql-—-datos-transaccionales-estructurados}

```
users, roles, permissions, user_roles, role_permissions
devices                        registro de dispositivos móviles
diseases, regions, intervention_types
scenarios, scenario_versions, scenario_interventions
cases                          reportes de campo
case_attachments               referencias a archivos en GCS
vaccine_lots                   lotes escaneados
simulation_runs                metadatos: escenario, semilla, estado, tiempos
audit_log                      bitácora de auditoría
```

Todo lo que tiene forma fija y no se puede perder ni corromper.

### **5.2 MongoDB — documentos y series** {#5.2-mongodb-—-documentos-y-series}

```
run_results          series diarias completas por corrida
run_summaries        indicadores agregados por corrida
raw_sync_payloads    lo que envió el móvil, tal como llegó
health_history       historial del servicio de monitoreo
event_log            registro de eventos y errores del sistema
```

**Por qué aquí y no en PostgreSQL:** una corrida produce cientos de miles de puntos, y cada versión del modelo genera una estructura de resultado distinta. Agregar una variable nueva al modelo no debe implicar una migración de esquema.

**Nota importante:** los metadatos de la corrida (quién, cuándo, con qué escenario) viven en PostgreSQL; los resultados voluminosos viven en MongoDB, enlazados por `run_id`.

### **5.3 Redis — temporal y rápido** {#5.3-redis-—-temporal-y-rápido}

```
session:{jti}                 sesiones activas
revoked:{jti}                 lista de revocación de tokens
queue:simulations             cola de trabajos pendientes
job:{id}:progress             progreso de una corrida en curso
cache:curves:{scenario_id}    caché de series para el tablero
ratelimit:{user}:{endpoint}   contadores de consumo
lock:{recurso}                bloqueos para operaciones concurrentes
```

Nada aquí es crítico: si Redis se reinicia, los usuarios vuelven a autenticarse y las cachés se reconstruyen.

### **5.4 Google Cloud Storage** {#5.4-google-cloud-storage}

```
/evidence/{case_id}/...        fotos desde campo
/reports/{report_id}.pdf       reportes generados
/scenarios/{id}/export.xml     escenarios exportados
/runs/{run_id}/artifacts/...   salidas voluminosas de simulación
```

Los archivos nunca van en base de datos. La base guarda únicamente la ruta.

---

## **6\. Procesamiento asíncrono** {#6.-procesamiento-asíncrono}

### **6.1 Ciclo de vida de un trabajo** {#6.1-ciclo-de-vida-de-un-trabajo}

```
encolado → ejecutando → { completado | fallido | cancelado }
```

1. El cliente hace `POST /api/v1/simulations` con el identificador de escenario y el número de réplicas.  
2. `simulation-service` valida, crea el registro en `simulation_runs` (PostgreSQL) con estado `encolado`, empuja el trabajo a `queue:simulations` y **responde de inmediato** con el `job_id`.  
3. Un worker del motor toma el trabajo, cambia el estado a `ejecutando` y actualiza `job:{id}:progress` conforme avanza.  
4. Al terminar, escribe resultados en MongoDB y marca `completado`.  
5. El cliente consulta `GET /api/v1/simulations/{job_id}` para conocer el estado, o recibe una notificación.

### **6.2 El motor de simulación** {#6.2-el-motor-de-simulación}

**Es la única pieza del sistema que no es Flask.** Su interfaz con el resto del mundo son dos cosas: leer de la cola y escribir en MongoDB.

**Estructura interna:**

| Componente | Función |
| ----- | ----- |
| Generador de población | Construye la población sintética desde datos censales |
| Núcleo de simulación | Kernels que ejecutan el paso diario sobre todos los agentes |
| Motor de intervenciones | Aplica las reglas programadas en cada fecha |
| Recolector de métricas | Agrega indicadores diarios |
| Escritor de resultados | Persiste en MongoDB y GCS |

**Dos implementaciones detrás del mismo contrato:**

* **Implementación de referencia:** Python \+ NumPy/Numba. Más lenta, se limita a unos 100 mil agentes. Es la que garantiza que el sistema funcione.  
* **Implementación acelerada:** C++20 \+ CUDA. Objetivo de 1 millón de agentes.

Ambas leen el mismo formato de trabajo y escriben el mismo formato de resultado. **Si la versión con GPU no llega a tiempo, se sustituye por la de Python y ningún otro componente se entera.** Este es el principal mecanismo de control de riesgo del proyecto.

---

## **7\. Infraestructura y despliegue** {#7.-infraestructura-y-despliegue}

### **7.1 Contenedores** {#7.1-contenedores}

Cada componente en su propio contenedor Docker. Un `docker-compose.yml` levanta el sistema completo en la máquina de cualquier integrante del equipo, sin importar su sistema operativo.

```
nginx · web · auth · catalog · scenario · simulation
surveillance · analytics · monitoring · sim-worker
postgres · mongo · redis
```

### **7.2 Entornos** {#7.2-entornos}

| Entorno | Dónde | Para qué |
| ----- | ----- | ----- |
| Desarrollo | Local, docker-compose | Trabajo diario |
| Producción | Google Compute Engine | Demostración y evaluación |

### **7.3 Red y seguridad** {#7.3-red-y-seguridad}

* Solo Nginx expuesto al exterior, en 80 y 443  
* Bases de datos y microservicios en red privada, sin IP pública  
* Reglas de firewall restrictivas por puerto y origen  
* Secretos en Google Secret Manager, inyectados como variables de entorno  
* **Ningún secreto en el repositorio.** Un archivo `.env.example` documenta las variables necesarias, sin valores

### **7.4 Máquinas** {#7.4-máquinas}

| Instancia | Contenido |
| ----- | ----- |
| VM principal | Nginx, web, microservicios, bases de datos |
| VM con GPU | Motor de simulación acelerado |

La VM con GPU se enciende solo cuando se necesita, para controlar costo. Si no hay presupuesto de GPU, el motor de referencia corre en la VM principal.

### **7.5 Integración continua** {#7.5-integración-continua}

GitHub Actions en cada push: linter, pruebas unitarias, construcción de imágenes Docker. Impide que llegue código roto a la rama principal.

### **7.6 Pruebas de carga** {#7.6-pruebas-de-carga}

Locust contra los endpoints de consulta y de ingesta: tablero, listado de escenarios, sincronización desde campo. **No contra el lanzamiento de simulaciones** — ese endpoint solo encola, es trivialmente rápido, y medirlo no dice nada útil.

---

## **8\. Stack tecnológico completo** {#8.-stack-tecnológico-completo}

| Capa | Tecnología | Por qué |
| ----- | ----- | ----- |
| Web | Python 3.12, Flask, Jinja2 | Requisito de la materia |
| Gráficas | Highcharts | Requisito de la materia |
| Frontend | HTML5, CSS3, JavaScript | Requisito de la materia |
| Microservicios | Flask, flask-smorest, marshmallow | REST \+ OpenAPI \+ validación desde un solo esquema |
| Autenticación | JWT (PyJWT), Redis | Requisito de la materia |
| Límites de consumo | Flask-Limiter | Backend en Redis, integración directa con Flask |
| Móvil | Kotlin, Retrofit, Room, CameraX, ML Kit, WorkManager | Estándar de Android; ML Kit resuelve QR y códigos de barras sin servicio externo |
| Escritorio | Python, PySide6 | El equipo ya usa Python; no agrega un lenguaje nuevo |
| Motor (referencia) | Python, NumPy, Numba | Implementación segura, siempre funciona |
| Motor (acelerado) | C++20, CUDA 12 | Objetivo de escala |
| Base relacional | PostgreSQL | Requisito de la materia |
| Base documental | MongoDB | Requisito de la materia |
| Caché y cola | Redis | Requisito de la materia |
| Archivos | Google Cloud Storage | Requisito de la materia |
| Contenedores | Docker, docker-compose | Requisito de la materia |
| Nube | Google Compute Engine, Secret Manager | Requisito de la materia |
| Puerta de entrada | Nginx | TLS y enrutamiento |
| Documentación de API | OpenAPI / Swagger | Requisito de la materia |
| Pruebas de carga | Locust | Requisito de la materia |
| Integración continua | GitHub Actions | Control de calidad básico |

---

## **9\. Decisiones abiertas**  {#9.-decisiones-abiertas}

**2\. Presupuesto de GPU en la nube.** Si no hay créditos suficientes, el motor acelerado corre en una máquina local del equipo y solo el motor de referencia se despliega en GCE.

**3\. Fuente de datos para la calibración.** Hay que confirmar disponibilidad y granularidad de la serie histórica que se usará.

**4\. Alcance del módulo de costo económico.** Se necesita para la frontera de eficiencia. Definir qué componentes de costo se incluyen y con qué supuestos.

**5\. Formato exacto del XML de escenario.** Definirlo en las primeras dos semanas: es un contrato entre el editor de escritorio, `scenario-service` y el motor. Cambiarlo tarde afecta a tres componentes a la vez.

---

## **10\. Orden de construcción** {#10.-orden-de-construcción}

El orden importa porque hay dependencias duras, y porque cada parcial de la materia exige un incremento ejecutable, no solo documentos.

**Primer parcial — semanas 1 a 4\. Análisis, datos y web mínimo.**

* Análisis del problema, actores y perfiles, requerimientos, reglas de negocio, matriz de permisos  
* Modelo de PostgreSQL: conceptual, lógico y físico  
* Diseño de colecciones de MongoDB y estructura de claves de Redis  
* Los nueve diagramas de arquitectura  
* Sistema web mínimo funcional: login con JWT, roles, dos catálogos y un proceso de negocio, guardando de verdad en PostgreSQL  
* Repositorio organizado y `docker-compose` con PostgreSQL, MongoDB y Redis

**Segundo parcial — semanas 5 a 9\. Contratos, microservicios y clientes.**

* Semana 5, antes de tocar los clientes: congelar los cuatro contratos — esquemas de recursos REST en JSON, sus XSD correspondientes, `scenario.xsd`, y el JSON Schema del trabajo y del resultado del motor  
* Microservicios: auth, catalog, scenario, surveillance, simulation  
* Negociación de contenido JSON/XML y documentación OpenAPI en Swagger  
* Motor de referencia en Python/Numba produciendo curvas contra la cola  
* App Android y app de escritorio, cada una consumiendo al menos cuatro microservicios

**Tercer parcial — semanas 10 a 12\. Nube, escala y pruebas.**

* Despliegue en Google Compute Engine: red privada, firewall, secretos, URLs firmadas  
* `analytics-service` y `monitoring-service` con el panel de salud  
* Motor acelerado en C++/CUDA  
* Calibración contra la ola histórica y carga de datos de alto volumen  
* Pruebas de carga con Locust y demostración de tolerancia a fallos

**Entrega final — semanas 13 a 14\.**

* Corrección de defectos, pruebas de regresión y de contratos  
* Expediente técnico, manuales, video y ensayo de la demostración

