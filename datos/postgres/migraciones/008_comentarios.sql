-- ===========================================================================
-- 008_comentarios.sql
-- Documentacion embebida en la base de datos.
--
-- Generado a partir del diccionario de datos: no editar a mano. Si cambia una
-- descripcion, cambiarla en el diccionario y volver a generar este archivo.
--
-- Consultar desde psql con \d+ nombre_tabla, o desde SQL con:
--   SELECT c.column_name, col_description(c.table_name::regclass, c.ordinal_position)
--   FROM information_schema.columns c WHERE c.table_name = 'cases';
-- ===========================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- users  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE users IS 'Cuentas de acceso a la plataforma. Unica fuente de identidad para los tres clientes.';
COMMENT ON COLUMN users.id IS 'Identificador interno de la cuenta. [llave primaria]';
COMMENT ON COLUMN users.username IS 'Nombre de acceso. Unico, sin distincion de mayusculas.';
COMMENT ON COLUMN users.email IS 'Correo institucional. Se usa para recuperacion de contrasena.';
COMMENT ON COLUMN users.password_hash IS 'Hash con algoritmo de costo alto (bcrypt o argon2). Nunca la contrasena.';
COMMENT ON COLUMN users.full_name IS 'Nombre completo mostrado en la interfaz y en la bitacora.';
COMMENT ON COLUMN users.is_active IS 'Baja logica. Un usuario inactivo no puede autenticarse pero conserva su historial.';
COMMENT ON COLUMN users.failed_attempts IS 'Intentos fallidos consecutivos. Se reinicia al iniciar sesion con exito.';
COMMENT ON COLUMN users.last_login_at IS 'Ultimo inicio de sesion exitoso, en cualquier cliente.';
COMMENT ON COLUMN users.created_at IS 'Fecha de alta de la cuenta.';
COMMENT ON COLUMN users.updated_at IS 'Ultima modificacion del registro.';

-- ---------------------------------------------------------------------------
-- roles  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE roles IS 'Catalogo de perfiles: administrador, epidemiologo, analista, capturista.';
COMMENT ON COLUMN roles.id IS 'Identificador del rol. [llave primaria]';
COMMENT ON COLUMN roles.code IS 'Clave estable usada en el codigo y en el JWT. Ejemplo: EPIDEMIOLOGO.';
COMMENT ON COLUMN roles.name IS 'Nombre visible del rol.';
COMMENT ON COLUMN roles.description IS 'Responsabilidades del perfil.';
COMMENT ON COLUMN roles.is_system IS 'Los roles de sistema no se pueden borrar desde la interfaz.';
COMMENT ON COLUMN roles.created_at IS 'Fecha de alta.';

-- ---------------------------------------------------------------------------
-- permissions  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE permissions IS 'Permisos atomicos por recurso y accion. Base de la matriz de permisos.';
COMMENT ON COLUMN permissions.id IS 'Identificador del permiso. [llave primaria]';
COMMENT ON COLUMN permissions.code IS 'Clave compuesta recurso.accion. Ejemplo: scenarios.publish.';
COMMENT ON COLUMN permissions.resource IS 'Recurso protegido: scenarios, cases, users, simulations.';
COMMENT ON COLUMN permissions.action IS 'Accion: read, create, update, delete, publish, run.';
COMMENT ON COLUMN permissions.description IS 'Que habilita el permiso en terminos de negocio.';

-- ---------------------------------------------------------------------------
-- user_roles  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE user_roles IS 'Asignacion de roles a usuarios. Un usuario puede tener varios roles.';
COMMENT ON COLUMN user_roles.user_id IS 'Usuario al que se asigna el rol. Referencia a users.id. [llave primaria]';
COMMENT ON COLUMN user_roles.role_id IS 'Rol asignado. Referencia a roles.id. [llave primaria]';
COMMENT ON COLUMN user_roles.assigned_by IS 'Administrador que hizo la asignacion. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN user_roles.assigned_at IS 'Momento de la asignacion.';

-- ---------------------------------------------------------------------------
-- role_permissions  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE role_permissions IS 'Permisos concedidos a cada rol. Es la matriz de permisos del primer parcial.';
COMMENT ON COLUMN role_permissions.role_id IS 'Rol que recibe el permiso. Referencia a roles.id. [llave primaria]';
COMMENT ON COLUMN role_permissions.permission_id IS 'Permiso concedido. Referencia a permissions.id. [llave primaria]';

-- ---------------------------------------------------------------------------
-- password_resets  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE password_resets IS 'Solicitudes de recuperacion de contrasena. Requisito explicito de la materia.';
COMMENT ON COLUMN password_resets.id IS 'Identificador de la solicitud. [llave primaria]';
COMMENT ON COLUMN password_resets.user_id IS 'Usuario que solicito el restablecimiento. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN password_resets.token_hash IS 'Hash del token enviado por correo. El token en claro nunca se guarda.';
COMMENT ON COLUMN password_resets.expires_at IS 'Vencimiento del token, tipicamente una hora.';
COMMENT ON COLUMN password_resets.used_at IS 'Momento de uso. Un token usado no se puede reutilizar.';
COMMENT ON COLUMN password_resets.requested_ip IS 'Direccion desde la que se pidio, para deteccion de abuso.';
COMMENT ON COLUMN password_resets.created_at IS 'Fecha de la solicitud.';

-- ---------------------------------------------------------------------------
-- devices  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE devices IS 'Dispositivos moviles registrados. Permite revocar un telefono perdido sin tocar la cuenta.';
COMMENT ON COLUMN devices.id IS 'Identificador interno del dispositivo. [llave primaria]';
COMMENT ON COLUMN devices.user_id IS 'Duenio del dispositivo. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN devices.device_uid IS 'Identificador seguro generado por la app Android. Requisito de la materia.';
COMMENT ON COLUMN devices.platform IS 'Plataforma del cliente.';
COMMENT ON COLUMN devices.model IS 'Modelo del equipo, util para depurar fallas de camara o GPS.';
COMMENT ON COLUMN devices.app_version IS 'Version instalada de la app, para diagnosticar incompatibilidades.';
COMMENT ON COLUMN devices.push_token IS 'Token de notificaciones push. Cambia con reinstalaciones.';
COMMENT ON COLUMN devices.is_revoked IS 'Un dispositivo revocado no puede sincronizar aunque tenga JWT valido.';
COMMENT ON COLUMN devices.last_seen_at IS 'Ultima sincronizacion registrada.';
COMMENT ON COLUMN devices.created_at IS 'Fecha de registro del dispositivo.';

-- ---------------------------------------------------------------------------
-- audit_log  (Sistema y auditoria · sistema web / todos)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE audit_log IS 'Bitacora de auditoria: quien hizo que, cuando y desde donde. Solo insercion.';
COMMENT ON COLUMN audit_log.id IS 'Identificador del asiento. [llave primaria]';
COMMENT ON COLUMN audit_log.user_id IS 'Autor de la accion. Nulo en procesos automaticos. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN audit_log.action IS 'Operacion: LOGIN, CREATE, UPDATE, DELETE, PUBLISH, RUN.';
COMMENT ON COLUMN audit_log.entity_type IS 'Tabla o recurso afectado.';
COMMENT ON COLUMN audit_log.entity_id IS 'Identificador del registro afectado, como texto para admitir cualquier tipo.';
COMMENT ON COLUMN audit_log.correlation_id IS 'X-Correlation-ID de la peticion. Permite rastrear la operacion entre servicios.';
COMMENT ON COLUMN audit_log.ip_address IS 'Origen de la peticion.';
COMMENT ON COLUMN audit_log.user_agent IS 'Cliente que origino la accion: navegador, Android o escritorio.';
COMMENT ON COLUMN audit_log.data_before IS 'Estado previo del registro. Nulo en altas.';
COMMENT ON COLUMN audit_log.data_after IS 'Estado posterior. Nulo en bajas.';
COMMENT ON COLUMN audit_log.occurred_at IS 'Momento del evento. Indice para consultas por rango de fechas.';

-- ---------------------------------------------------------------------------
-- notifications  (Sistema y auditoria · sistema web / todos)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE notifications IS 'Avisos al usuario: corrida terminada, umbral rebasado, asignacion de zona.';
COMMENT ON COLUMN notifications.id IS 'Identificador del aviso. [llave primaria]';
COMMENT ON COLUMN notifications.user_id IS 'Destinatario. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN notifications.type IS 'Tipo: RUN_FINISHED, THRESHOLD_EXCEEDED, ASSIGNMENT.';
COMMENT ON COLUMN notifications.title IS 'Titulo corto mostrado en la campana del portal y en el push.';
COMMENT ON COLUMN notifications.body IS 'Cuerpo del mensaje.';
COMMENT ON COLUMN notifications.payload IS 'Datos para navegar al recurso: run_id, scenario_id, region_id.';
COMMENT ON COLUMN notifications.read_at IS 'Momento de lectura. Nulo mientras no se lee.';
COMMENT ON COLUMN notifications.created_at IS 'Fecha de emision.';

-- ---------------------------------------------------------------------------
-- system_settings  (Sistema y auditoria · sistema web / todos)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE system_settings IS 'Configuracion del sistema editable sin desplegar codigo.';
COMMENT ON COLUMN system_settings.key IS 'Clave del parametro. Ejemplo: max_replicas_por_lote. [llave primaria]';
COMMENT ON COLUMN system_settings.value IS 'Valor. JSONB para admitir numeros, textos, listas y objetos.';
COMMENT ON COLUMN system_settings.description IS 'Que controla el parametro y que rango es seguro.';
COMMENT ON COLUMN system_settings.updated_by IS 'Ultimo administrador que lo cambio. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN system_settings.updated_at IS 'Fecha del ultimo cambio.';

-- ---------------------------------------------------------------------------
-- diseases  (Catalogos · catalog-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE diseases IS 'Catalogo de enfermedades con sus parametros epidemiologicos base.';
COMMENT ON COLUMN diseases.id IS 'Identificador de la enfermedad. [llave primaria]';
COMMENT ON COLUMN diseases.code IS 'Clave estable. Ejemplo: COVID19_ORIGINAL.';
COMMENT ON COLUMN diseases.name IS 'Nombre de la enfermedad o variante.';
COMMENT ON COLUMN diseases.description IS 'Contexto y fuente de los parametros.';
COMMENT ON COLUMN diseases.default_params IS 'Parametros base: incubacion, duracion infecciosa, letalidad por grupo de edad.';
COMMENT ON COLUMN diseases.is_active IS 'Baja logica del catalogo.';
COMMENT ON COLUMN diseases.created_at IS 'Fecha de alta.';

-- ---------------------------------------------------------------------------
-- regions  (Catalogos · catalog-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE regions IS 'Jerarquia geografica del area metropolitana. Autorreferencial: estado, municipio, AGEB.';
COMMENT ON COLUMN regions.id IS 'Identificador interno de la zona. [llave primaria]';
COMMENT ON COLUMN regions.code IS 'Clave oficial INEGI. Ejemplo: 19039-0123.';
COMMENT ON COLUMN regions.name IS 'Nombre de la zona.';
COMMENT ON COLUMN regions.level IS 'Nivel jerarquico: estado, municipio o ageb.';
COMMENT ON COLUMN regions.parent_region_id IS 'Zona superior. Nulo solo en la raiz. Referencia a regions.id. [llave foranea]';
COMMENT ON COLUMN regions.population IS 'Poblacion censal. Insumo del generador de poblacion sintetica.';
COMMENT ON COLUMN regions.centroid_lat IS 'Latitud del centroide, para el mapa de incidencia.';
COMMENT ON COLUMN regions.centroid_lon IS 'Longitud del centroide.';
COMMENT ON COLUMN regions.created_at IS 'Fecha de carga.';

-- ---------------------------------------------------------------------------
-- intervention_types  (Catalogos · catalog-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE intervention_types IS 'Catalogo de intervenciones modelables y como se traducen al motor.';
COMMENT ON COLUMN intervention_types.id IS 'Identificador del tipo de intervencion. [llave primaria]';
COMMENT ON COLUMN intervention_types.code IS 'Clave estable. Ejemplo: CIERRE_ESCUELAS.';
COMMENT ON COLUMN intervention_types.name IS 'Nombre visible.';
COMMENT ON COLUMN intervention_types.target_layer IS 'Capa de contacto afectada: hogar, escuela, trabajo, comunidad o todas.';
COMMENT ON COLUMN intervention_types.primitive IS 'Primitiva del motor: edge_modifier o node_attr. Define como compila el XML.';
COMMENT ON COLUMN intervention_types.param_schema IS 'Esquema de los parametros admitidos. Valida el escenario antes de encolar.';
COMMENT ON COLUMN intervention_types.description IS 'Efecto de la intervencion en el modelo.';
COMMENT ON COLUMN intervention_types.is_active IS 'Baja logica del catalogo.';

-- ---------------------------------------------------------------------------
-- cases  (Vigilancia de campo · surveillance-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE cases IS 'Casos capturados en campo desde la app movil. Alimentan la recalibracion del modelo.';
COMMENT ON COLUMN cases.id IS 'Identificador del caso en el servidor. [llave primaria]';
COMMENT ON COLUMN cases.local_uuid IS 'Identificador generado en el dispositivo. Evita duplicados si un envio se repite.';
COMMENT ON COLUMN cases.device_id IS 'Dispositivo que capturo el caso. Referencia a devices.id. [llave foranea]';
COMMENT ON COLUMN cases.reported_by IS 'Brigadista que reporto. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN cases.disease_id IS 'Enfermedad reportada. Referencia a diseases.id. [llave foranea]';
COMMENT ON COLUMN cases.region_id IS 'Zona de residencia del caso. Referencia a regions.id. [llave foranea]';
COMMENT ON COLUMN cases.vaccine_lot_id IS 'Lote aplicado, si aplica. Referencia a vaccine_lots.id. [llave foranea]';
COMMENT ON COLUMN cases.age IS 'Edad en anios. Determina el riesgo de curso grave.';
COMMENT ON COLUMN cases.sex IS 'Sexo registrado: M, F u O.';
COMMENT ON COLUMN cases.onset_date IS 'Fecha de inicio de sintomas. Es la fecha epidemiologicamente relevante.';
COMMENT ON COLUMN cases.report_date IS 'Fecha de captura. La diferencia con onset_date estima el rezago de notificacion.';
COMMENT ON COLUMN cases.latitude IS 'Latitud capturada por GPS.';
COMMENT ON COLUMN cases.longitude IS 'Longitud capturada por GPS.';
COMMENT ON COLUMN cases.test_result IS 'Resultado de prueba: positivo, negativo, pendiente o sin prueba.';
COMMENT ON COLUMN cases.severity IS 'Gravedad: asintomatico, leve, grave o fallecido.';
COMMENT ON COLUMN cases.status IS 'Estado de validacion: pendiente, validado, duplicado o descartado.';
COMMENT ON COLUMN cases.created_at IS 'Momento de captura en el dispositivo.';
COMMENT ON COLUMN cases.synced_at IS 'Momento de llegada al servidor. Puede ser mucho posterior por el modo sin conexion.';

-- ---------------------------------------------------------------------------
-- case_attachments  (Vigilancia de campo · surveillance-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE case_attachments IS 'Referencias a evidencias fotograficas. El archivo vive en Cloud Storage, nunca en la base.';
COMMENT ON COLUMN case_attachments.id IS 'Identificador del adjunto. [llave primaria]';
COMMENT ON COLUMN case_attachments.case_id IS 'Caso al que pertenece la evidencia. Referencia a cases.id. [llave foranea]';
COMMENT ON COLUMN case_attachments.storage_path IS 'Ruta en el bucket: /evidence/{case_id}/archivo.';
COMMENT ON COLUMN case_attachments.mime_type IS 'Tipo de contenido validado en el servidor, no confiando en la extension.';
COMMENT ON COLUMN case_attachments.size_bytes IS 'Tamanio del archivo, para control de cuota.';
COMMENT ON COLUMN case_attachments.sha256 IS 'Huella del contenido. Detecta duplicados y corrupcion.';
COMMENT ON COLUMN case_attachments.privacy IS 'Nivel de privacidad. Los privados requieren URL firmada.';
COMMENT ON COLUMN case_attachments.uploaded_by IS 'Usuario que subio el archivo. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN case_attachments.uploaded_at IS 'Fecha de subida.';

-- ---------------------------------------------------------------------------
-- vaccine_lots  (Vigilancia de campo · surveillance-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE vaccine_lots IS 'Lotes de vacuna escaneados por QR desde la app movil.';
COMMENT ON COLUMN vaccine_lots.id IS 'Identificador del lote. [llave primaria]';
COMMENT ON COLUMN vaccine_lots.lot_code IS 'Codigo impreso en el lote, leido por QR o codigo de barras.';
COMMENT ON COLUMN vaccine_lots.manufacturer IS 'Fabricante.';
COMMENT ON COLUMN vaccine_lots.disease_id IS 'Enfermedad que previene. Referencia a diseases.id. [llave foranea]';
COMMENT ON COLUMN vaccine_lots.region_id IS 'Zona donde esta asignado el lote. Referencia a regions.id. [llave foranea]';
COMMENT ON COLUMN vaccine_lots.doses_total IS 'Dosis totales del lote.';
COMMENT ON COLUMN vaccine_lots.doses_used IS 'Dosis aplicadas. Nunca debe superar doses_total.';
COMMENT ON COLUMN vaccine_lots.expires_on IS 'Fecha de caducidad.';
COMMENT ON COLUMN vaccine_lots.scanned_by IS 'Usuario que registro el lote. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN vaccine_lots.scanned_at IS 'Momento del escaneo.';

-- ---------------------------------------------------------------------------
-- scenarios  (Escenarios · scenario-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE scenarios IS 'Escenario de politica publica. El contenido pesado vive en sus versiones.';
COMMENT ON COLUMN scenarios.id IS 'Identificador del escenario. [llave primaria]';
COMMENT ON COLUMN scenarios.name IS 'Nombre del escenario. Ejemplo: Cierre de escuelas semana 3.';
COMMENT ON COLUMN scenarios.description IS 'Pregunta de politica publica que busca responder.';
COMMENT ON COLUMN scenarios.disease_id IS 'Enfermedad simulada. Referencia a diseases.id. [llave foranea]';
COMMENT ON COLUMN scenarios.region_id IS 'Ambito geografico. Referencia a regions.id. [llave foranea]';
COMMENT ON COLUMN scenarios.owner_id IS 'Analista propietario. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN scenarios.status IS 'Estado: borrador, publicado o archivado.';
COMMENT ON COLUMN scenarios.is_public IS 'Si es visible en el sitio publico sin autenticacion.';
COMMENT ON COLUMN scenarios.created_at IS 'Fecha de creacion.';
COMMENT ON COLUMN scenarios.updated_at IS 'Ultima modificacion.';

-- ---------------------------------------------------------------------------
-- scenario_versions  (Escenarios · scenario-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE scenario_versions IS 'Versionado inmutable. Una corrida siempre apunta a una version, nunca al escenario.';
COMMENT ON COLUMN scenario_versions.id IS 'Identificador de la version. [llave primaria]';
COMMENT ON COLUMN scenario_versions.scenario_id IS 'Escenario al que pertenece. Unico junto con version_number. [llave foranea]';
COMMENT ON COLUMN scenario_versions.version_number IS 'Numero consecutivo dentro del escenario.';
COMMENT ON COLUMN scenario_versions.is_current IS 'Marca la version vigente. Solo una por escenario.';
COMMENT ON COLUMN scenario_versions.xml_path IS 'Ruta del XML exportado en el bucket: /scenarios/{id}/export.xml.';
COMMENT ON COLUMN scenario_versions.xml_checksum IS 'SHA-256 del XML. Garantiza que la corrida uso exactamente ese archivo.';
COMMENT ON COLUMN scenario_versions.population_size IS 'Numero de agentes de la poblacion sintetica.';
COMMENT ON COLUMN scenario_versions.horizon_days IS 'Dias simulados.';
COMMENT ON COLUMN scenario_versions.notes IS 'Que cambio respecto de la version anterior.';
COMMENT ON COLUMN scenario_versions.created_by IS 'Autor de la version. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN scenario_versions.created_at IS 'Fecha de congelamiento de la version.';

-- ---------------------------------------------------------------------------
-- scenario_interventions  (Escenarios · scenario-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE scenario_interventions IS 'Calendario de intervenciones de una version. Es el corazon del escenario.';
COMMENT ON COLUMN scenario_interventions.id IS 'Identificador de la intervencion programada. [llave primaria]';
COMMENT ON COLUMN scenario_interventions.scenario_version_id IS 'Version a la que pertenece. Referencia a scenario_versions.id. [llave foranea]';
COMMENT ON COLUMN scenario_interventions.intervention_type_id IS 'Tipo de intervencion. Referencia a intervention_types.id. [llave foranea]';
COMMENT ON COLUMN scenario_interventions.target_region_id IS 'Zona donde aplica. Nulo significa toda la region del escenario. [llave foranea]';
COMMENT ON COLUMN scenario_interventions.start_day IS 'Dia de simulacion en que se activa, contado desde el dia cero.';
COMMENT ON COLUMN scenario_interventions.end_day IS 'Dia en que se retira. Nulo significa hasta el fin del horizonte.';
COMMENT ON COLUMN scenario_interventions.coverage IS 'Fraccion de la poblacion objetivo alcanzada, de 0 a 1.';
COMMENT ON COLUMN scenario_interventions.compliance IS 'Nivel de cumplimiento esperado, de 0 a 1. Modula el efecto real.';
COMMENT ON COLUMN scenario_interventions.params IS 'Parametros propios del tipo: eficacia, criterio de prioridad, porcentaje de aforo.';
COMMENT ON COLUMN scenario_interventions.order_index IS 'Orden de aplicacion cuando dos intervenciones tocan la misma capa el mismo dia.';

-- ---------------------------------------------------------------------------
-- simulation_batches  (Simulacion · simulation-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE simulation_batches IS 'Lote de replicas de una misma version. Es la unidad que se compara en la frontera.';
COMMENT ON COLUMN simulation_batches.id IS 'Identificador del lote. [llave primaria]';
COMMENT ON COLUMN simulation_batches.scenario_version_id IS 'Version simulada. Referencia a scenario_versions.id. [llave foranea]';
COMMENT ON COLUMN simulation_batches.requested_by IS 'Usuario que lanzo el lote. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN simulation_batches.replicas IS 'Numero de corridas con semillas distintas. Entre 30 y 50.';
COMMENT ON COLUMN simulation_batches.engine IS 'Implementacion usada: numba o cuda.';
COMMENT ON COLUMN simulation_batches.status IS 'Estado agregado: encolado, ejecutando, completado, fallido o cancelado.';
COMMENT ON COLUMN simulation_batches.summary_doc_id IS 'Documento en MongoDB run_summaries con mediana y banda de incertidumbre.';
COMMENT ON COLUMN simulation_batches.created_at IS 'Fecha de encolado del lote.';
COMMENT ON COLUMN simulation_batches.finished_at IS 'Momento en que termino la ultima replica.';

-- ---------------------------------------------------------------------------
-- simulation_runs  (Simulacion · simulation-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE simulation_runs IS 'Metadatos de una corrida individual. Los resultados voluminosos viven en MongoDB y GCS.';
COMMENT ON COLUMN simulation_runs.id IS 'Identificador de la corrida. Es el job_id devuelto al cliente. [llave primaria]';
COMMENT ON COLUMN simulation_runs.batch_id IS 'Lote al que pertenece. Nulo en corridas sueltas. Referencia a simulation_batches.id. [llave foranea]';
COMMENT ON COLUMN simulation_runs.scenario_version_id IS 'Version simulada. Se guarda tambien aqui para consultar sin unir el lote. [llave foranea]';
COMMENT ON COLUMN simulation_runs.seed IS 'Semilla del generador aleatorio. Hace la corrida reproducible.';
COMMENT ON COLUMN simulation_runs.replica_index IS 'Numero de replica dentro del lote.';
COMMENT ON COLUMN simulation_runs.status IS 'Ciclo de vida: encolado, ejecutando, completado, fallido o cancelado.';
COMMENT ON COLUMN simulation_runs.progress IS 'Porcentaje de avance. Se espeja en Redis durante la ejecucion.';
COMMENT ON COLUMN simulation_runs.engine_version IS 'Version del motor. Permite detectar resultados no comparables entre si.';
COMMENT ON COLUMN simulation_runs.queued_at IS 'Momento de entrada a la cola.';
COMMENT ON COLUMN simulation_runs.started_at IS 'Momento en que un worker tomo el trabajo.';
COMMENT ON COLUMN simulation_runs.finished_at IS 'Momento de termino, exitoso o no.';
COMMENT ON COLUMN simulation_runs.result_doc_id IS 'Documento en MongoDB run_results con las series diarias completas.';
COMMENT ON COLUMN simulation_runs.artifacts_path IS 'Ruta en el bucket con las salidas voluminosas: /runs/{run_id}/artifacts/.';
COMMENT ON COLUMN simulation_runs.error_message IS 'Causa de la falla cuando el estado es fallido.';

INSERT INTO schema_migrations (version, description)
VALUES ('008', 'Comentarios de tablas y columnas')
ON CONFLICT (version) DO NOTHING;

COMMIT;
