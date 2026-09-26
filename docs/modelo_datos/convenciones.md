# Convenciones supuestos y decisiones abiertas

Leelo antes de escribir las migraciones. Cada supuesto aqui es una decision que el equipo puede revertir. 

## Notacion del diccionario
| PK | Llave primaria. En el diccionario aparece en negritas.                                   |
| FK | Llave foranea. En el diccionario aparece en cursivas.                                    |
| UQ | Restriccion de unicidad, sola o compuesta con otra columna marcada UQ de la misma tabla. |
| IX | Indice recomendado por patron de consulta previsto, no por restriccion.                  |

## Convenciones de nombres
| Tablas         | Plural, minusculas, guion bajo. Ejemplo: scenario_versions.          |
| Llave primaria | Siempre id, salvo tablas puente que usan llave compuesta.            |
| Llave foranea  | Nombre de la tabla en singular mas _id. Ejemplo: disease_id.         |
| Fechas         | Sufijo _at para marcas de tiempo y _on o _date para fechas sin hora. |
| Booleanos      | Prefijo is_ o has_. Ejemplo: is_active.                              |

## Supuestos tecnicos
| Zona horaria | Todo TIMESTAMPTZ se guarda en UTC. La conversion a hora local ocurre en el cliente.                |
| Cadenas      | VARCHAR con limite explicito donde el dominio lo define; TEXT donde el texto es libre.             |
| Dinero       | No hay columnas monetarias: el costo se expresa en dias-persona de actividad perdida, no en pesos. |
| Borrado      | Los usuarios se dan de baja logica con is_active. El borrado fisico se reserva a datos de prueba.  |
| Auditoria    | audit_log es solo de insercion. Ningun servicio debe actualizar ni borrar filas ahi.               |
| Contrasenas  | Solo se guarda el hash. Tampoco se guardan tokens en claro en password_resets.                     |

## Tablas propuestas, no presentes en el documento de arquitectura
| simulation_batches | Un escenario se corre entre 30 y 50 veces. Sin registro padre no hay donde guardar el resumen del ensamble, que es lo que alimenta la frontera de eficiencia. |
| password_resets    | La materia pide recuperacion de contrasena de forma explicita.                                                                                                |
| notifications      | El portal privado incluye modulo de notificaciones y Redis no sirve: ahi nada es critico.                                                                     |
| system_settings    | La materia pide configuracion del sistema.                                                                                                                    |

## Decisiones de modelado que conviene revisar en equipo
| Version vigente           | Se quito current_version_id de scenarios y se puso is_current en scenario_versions. Un FK cruzado en ambos sentidos crea un ciclo que complica inserts y migraciones.                                                 |
| Jerarquia geografica      | regions es autorreferencial para estado, municipio y AGEB en una sola tabla, en vez de tres tablas separadas.                                                                                                         |
| Primitiva de intervencion | intervention_types.primitive declara si el tipo compila a modificador de aristas o a atributo de nodo. Hace explicito en el catalogo lo que el motor va a ejecutar y permite validar el escenario antes de encolarlo. |
| Version duplicada         | simulation_runs guarda scenario_version_id ademas de batch_id, para consultar corridas sin unir con el lote. Es desnormalizacion deliberada.                                                                          |

## Pendiente de definir
| Restricciones CHECK | Faltan los CHECK de los campos de estado (status, level, severity, primitive) y de los rangos 0 a 1 en coverage y compliance. |
| Indices             | Solo estan marcados los evidentes. Los definitivos salen de las consultas reales del tablero y del comparador.                |
| Particionamiento    | Si simulation_runs o audit_log crecen mucho, evaluar particion por rango de fecha.                                            |
| Datos de prueba     | El primer parcial pide carga inicial de datos para los catalogos: diseases, regions, intervention_types, roles y permissions. |

