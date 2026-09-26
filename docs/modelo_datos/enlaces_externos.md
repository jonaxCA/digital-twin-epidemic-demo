# Fronteras con mongo db redis y cloud storage
Estas columnas no son llaves foraneas: PostgreSQL no puede validarlas. La integridad la sostiene el codigo del servicio.

| Tabla de postgre sql | Columna        | Almacen destino | Coleccion clave o ruta     | Que guarda del otro lado                                                   |
| simulation_runs      | result_doc_id  | MongoDB         | run_results                | Series diarias completas de la corrida: casos, hospitalizados, fallecidos. |
| simulation_batches   | summary_doc_id | MongoDB         | run_summaries              | Indicadores agregados del lote: mediana y banda de incertidumbre.          |
| simulation_runs      | artifacts_path | Cloud Storage   | /runs/{run_id}/artifacts/  | Salidas voluminosas que exceden el limite de 16 MB de MongoDB.             |
| case_attachments     | storage_path   | Cloud Storage   | /evidence/{case_id}/       | Fotografias capturadas en campo. Se sirven con URL firmada.                |
| scenario_versions    | xml_path       | Cloud Storage   | /scenarios/{id}/export.xml | XML del escenario tal como lo exporto la app de escritorio.                |
| users                | id             | Redis           | session:{jti}              | Sesion activa. Si Redis se reinicia el usuario vuelve a autenticarse.      |
| users                | id             | Redis           | revoked:{jti}              | Lista de revocacion consultada por todo endpoint protegido.                |
| simulation_runs      | id             | Redis           | job:{id}:progress          | Progreso en vivo de la corrida. La base guarda el valor consolidado.       |
| simulation_runs      | id             | Redis           | queue:simulations          | Cola de trabajos pendientes que lee el motor de simulacion.                |
| scenarios            | id             | Redis           | cache:curves:{scenario_id} | Cache de series para el tablero. Reconstruible.                            |

## Principio  
Los archivos nunca van en la base: PostgreSQL guarda unicamente identificador, ruta, tipo, tamanio, hash, propietario, fecha y nivel de privacidad. Los resultados voluminosos van a MongoDB, y lo que exceda su limite de 16 MB por documento va a Cloud Storage.
