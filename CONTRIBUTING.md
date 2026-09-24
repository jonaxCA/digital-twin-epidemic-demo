# Guía de colaboración

Cómo trabajamos en este repositorio. Si es tu primera vez, lee la sección "Configuración inicial" y luego "El ciclo diario". Lo demás es referencia.

---

## Configuración inicial

Una sola vez, al entrar al proyecto.

```bash
git clone https://github.com/<organizacion>/<repo>.git
cd <repo>
cp .env.example .env      # pide las credenciales al responsable de infraestructura
docker compose up
```

Si `docker compose up` no levanta el sistema, **no le sigas por tu cuenta**: avisa en el canal del equipo. Que el proyecto arranque en menos de 15 minutos es responsabilidad del equipo, no tuya.

Configura tu identidad de Git si no lo has hecho:

```bash
git config --global user.name "Tu Nombre"
git config --global user.email "tucorreo@ejemplo.com"
```

---

## El ciclo diario

Estos son los comandos que vas a usar el 95% del tiempo.

### 1. Antes de empezar una tarea

```bash
git checkout main
git pull
git checkout -b feat/nombre-descriptivo
```

**Nunca te saltes el `git pull`.** La mayoría de los conflictos evitables vienen de arrancar desde un `main` viejo.

### 2. Mientras trabajas

```bash
git add .
git commit -m "Agrega validación de token en auth-service"
```

Commits chicos y frecuentes. Uno por unidad de trabajo que tenga sentido por sí sola, no uno gigante al final del día.

### 3. Cuando terminas

```bash
git push -u origin feat/nombre-descriptivo
```

El `-u` solo la primera vez de cada rama. Después basta con `git push`.

### 4. Abrir el Pull Request

En GitHub aparecerá un botón **Compare & pull request**. Ahí:

- Describe en dos o tres líneas qué hiciste y por qué
- Asigna al menos un revisor
- Si cierra un issue, escribe `Closes #14` en la descripción

### 5. Después de la aprobación

- Botón **Squash and merge** (no "Merge commit")
- Botón **Delete branch**

### 6. Limpieza local

```bash
git checkout main
git pull
git branch -d feat/nombre-descriptivo
```

Y a empezar de nuevo.

---

## Reglas que no se rompen

### Nunca hagas push directo a `main`

Aunque sea "un cambio chiquito". Aunque sea urgente. Aunque sea solo el README. Así empieza siempre.

### Nunca subas `.env` ni credenciales

El archivo `.env` está en `.gitignore`. No lo saques de ahí.

**Si ya subiste una credencial por accidente:** borrar el commit **no es suficiente** — quedó en el historial y en los clones de todos. Avisa de inmediato al responsable de infraestructura para **rotar la credencial** (generar una nueva y desactivar la vieja). No intentes arreglarlo en silencio.

### Nadie aprueba su propio PR

Aunque tengas prisa. La revisión es rápida; encontrar el error en la semana 12 no lo es.

### No toques el componente de otro sin avisar

Si tu cambio necesita modificar código de otro componente, coméntalo con su responsable antes.

---

## Convenciones

### Nombres de rama

Prefijo, diagonal, descripción corta en minúsculas con guiones.

| Prefijo | Para qué | Ejemplo |
|---|---|---|
| `feat/` | Funcionalidad nueva | `feat/android-captura-casos` |
| `fix/` | Corrección de error | `fix/error-validacion-xml` |
| `docs/` | Documentación | `docs/contrato-openapi` |
| `chore/` | Configuración, dependencias, infraestructura | `chore/dockerfile-worker` |
| `refactor/` | Reorganización sin cambiar comportamiento | `refactor/esquemas-marshmallow` |

### Mensajes de commit

En español, en imperativo, sin punto final.

**Bien:**
```
Agrega endpoint de salud a analytics-service
Corrige cálculo de días-cama en el módulo de costo
Elimina dependencia sin usar en el worker
```

**Mal:**
```
cambios
arreglé el bug
WIP
asdasd
```

### Una rama, una tarea, vida corta

Si tu rama lleva más de tres días abierta, se está alejando de `main` y el conflicto crece. Mejor parte la tarea en pedazos que se puedan mezclar antes.

### La carpeta `/docs/contratos` es especial

Contiene la especificación OpenAPI y el esquema XSD de escenario. **Son contratos entre componentes.**

Cualquier cambio ahí:

- Requiere aviso previo en el canal del equipo
- Requiere aprobación de los responsables de todos los componentes afectados

- Debe incrementar la versión del contrato

Cambiar un contrato sin avisar rompe el trabajo de otras personas sin que se enteren hasta que ya es tarde.

---

## Prevenir conflictos

Cuando tu rama lleva días abierta, trae lo nuevo de `main` hacia tu rama:

```bash
git checkout main
git pull
git checkout mi-rama
git merge main
```

Resuelves el conflicto ahí, en pequeño, en vez de acumularlo hasta la PR.

**Regla general:** es mucho mejor resolver un conflicto en tu rama que en el pull request.

---

## Si algo sale mal

### Hice commit en `main` sin querer, todavía no hice push

```bash
git branch mi-rama-nueva     # guarda el trabajo en una rama
git reset --hard origin/main # regresa main a como estaba
git checkout mi-rama-nueva   # sigue trabajando ahí
```

### Quiero deshacer el último commit pero conservar los cambios

```bash
git reset --soft HEAD~1
```

### Me equivoqué de rama y ya escribí código

```bash
git stash                    # guarda los cambios temporalmente
git checkout rama-correcta
git stash pop                # los recupera aquí
```

### Ya no sé en qué estado estoy

```bash
git status
git log --oneline -10
```

Y si sigues sin entender: **pregunta antes de ejecutar comandos que no conoces.** Especialmente evita `git push --force`, que puede borrar el trabajo de otros.

---

## Tareas e issues (por discutir)

- Las tareas idealmente viven en **GitHub Issues**
- Un issue por tarea, asignado a una persona
- El tablero está en la pestaña **Projects**
- Al abrir el PR, escribe `Closes #NN` para que el issue se cierre solo al mezclar

---

## Checklist antes de abrir un Pull Request

- [ ] El código corre localmente con `docker compose up`
- [ ] No hay credenciales, `.env` ni datos personales en los archivos
- [ ] Los commits tienen mensajes descriptivos
- [ ] Traje `main` a mi rama si llevaba días abierta
- [ ] Si toqué un contrato en `/docs/contratos`, avisé al equipo
- [ ] La descripción del PR explica qué hace y por qué
- [ ] Asigné un revisor
