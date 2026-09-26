# **Simulador de respuesta a epidemias**

**Documento de proyecto — v1** Prácticas de investigación \+ Integración de Aplicaciones Computacionales

## **1\. Resumen ejecutivo**

### **Qué vamos a construir**

Una plataforma que permite **ensayar decisiones de salud pública antes de tomarlas**.

El usuario define un escenario ("¿qué pasa si cerramos escuelas en la semana 3 y vacunamos primero a mayores de 60?"), el sistema simula cómo se propagaría la epidemia bajo esa decisión, y devuelve resultados comparables: cuántos casos, cuántas muertes, cuánta saturación hospitalaria, cuánto costo económico.

No es un solo programa: es un sistema con tres formas de usarse (web, móvil y escritorio) conectadas a un motor de simulación.

### **El problema que resuelve**

Cuando llega una crisis sanitaria, las decisiones se toman con información incompleta y sin forma de comparar alternativas. Las herramientas que existen para esto tienen un problema en común: **son scripts de investigación**. Las corre un investigador, en su máquina, desde una terminal. Nadie más del equipo puede usarlas, no hay control de quién cambió qué supuesto, y no hay manera de meter datos frescos del campo.

Nuestra aportación no es inventar un modelo epidemiológico nuevo. Es tomar un modelo sólido y **convertirlo en una plataforma que un equipo real puede operar**: con roles y permisos, con captura de datos desde campo, con historial auditable y con despliegue reproducible en la nube.

### **Qué lo hace distinto**

* **Modelo basado en agentes.** Simulamos personas individuales, no promedios poblacionales. Eso permite representar hogares, escuelas, trabajos y movilidad — cosas que los modelos clásicos no capturan.  
* **Datos reales de campo.** La app móvil permite que brigadistas capturen casos geolocalizados, lo que alimenta la calibración del modelo. La mayoría de los simuladores académicos usan datos sintéticos o históricos descargados.  
* **Multiusuario con roles.** Epidemiólogo, analista, capturista y tomador de decisiones ven cosas distintas y pueden hacer cosas distintas.  
* **Comparación sistemática.** No corre un escenario: corre decenas y los grafica juntos para que se vea el balance entre salud y costo.

### **Doble propósito**

Este proyecto se entrega simultáneamente para prácticas de investigación y para la materia de Integración de Aplicaciones Computacionales. Esto **no reduce el trabajo a la mitad** — reduce la duplicación de documentación y presentaciones, alrededor de un 15-20%. Lo asumimos con los ojos abiertos.

La materia exige una arquitectura específica (web en Flask, microservicios REST, app Android, app de escritorio, PostgreSQL/MongoDB/Redis, despliegue en Google Cloud). Esa arquitectura no es un impuesto: **es exactamente lo que convierte el simulador en plataforma**, que es nuestra aportación de investigación.

### **Alcance del semestre**

**Sí entra:**

* Motor de simulación basado en agentes, \~1 millón de agentes, zona metropolitana de Monterrey  
* Población sintética construida a partir de datos censales abiertos (INEGI)  
* Calibración contra una ola epidémica histórica real  
* Intervenciones modelables: cierres, aforo, vacunación, testeo y aislamiento, cubrebocas  
* Comparación de escenarios con frontera de costo-beneficio  
* Los tres clientes (web, Android, escritorio) y la infraestructura completa en la nube

**No entra — queda como trabajo futuro:**

* Visualización inmersiva 3D (Unreal Engine, salas de proyección)  
* Escala global multi-país  
* Aprendizaje por refuerzo para optimizar políticas automáticamente  
* Poblaciones sintéticas con perfiles psicológicos  
* Cómputo distribuido multi-nodo

Esta reducción es deliberada. La propuesta original abarcaba varios problemas de investigación abierta, cada uno de escala doctoral. Lo que queda sigue siendo un proyecto fuerte y, sobre todo, **terminable en catorce semanas**.

### **Entregable final**

Un sistema desplegado y funcionando, con datos reales cargados, capaz de correr una demostración en vivo: capturar un caso desde el celular, verlo aparecer en el tablero web, lanzar tres escenarios desde la app de escritorio y comparar sus resultados.

## **2\. Funcionamiento del simulador**

Esta sección explica el corazón epidemiológico del sistema. Es la parte que hace el trabajo real; todo lo demás existe para alimentarla o para mostrar lo que produce.

### **2.1 La idea básica: simular personas, no promedios**

Los modelos epidemiológicos clásicos (SIR, SEIR) dividen a la población en cajas: *susceptibles*, *expuestos*, *infectados*, *recuperados*, y usan ecuaciones para mover gente de una caja a otra. Son rápidos y útiles, pero asumen que **todos tienen la misma probabilidad de encontrarse con todos**. En la realidad no es así: convives mucho más con tu familia que con alguien del otro lado de la ciudad.

Nosotros usamos un **modelo basado en agentes**. Creamos un millón de individuos digitales, cada uno con sus propias características, sus propios contactos y su propio estado de salud. La epidemia no se calcula con una ecuación: **emerge** de millones de interacciones individuales.

Esto cuesta mucho más cómputo, pero permite responder preguntas que el modelo clásico no puede: ¿sirve más cerrar escuelas o reducir aforo en transporte? Un modelo de cajas no distingue entre esas dos cosas. El nuestro sí.

### **2.2 Qué es un agente**

Cada agente representa a una persona y carga con:

| Atributo | Ejemplo |
| ----- | ----- |
| Edad | 34 años |
| Hogar | Hogar \#182 340, con otras 4 personas |
| Ocupación | Trabaja en el sector servicios |
| Zona | AGEB específica del área metropolitana |
| Estado de salud | Susceptible / Expuesto / Infeccioso / Recuperado |
| Nivel de cumplimiento | Qué tanto respeta las medidas (0 a 1\) |

La **población sintética** se genera antes de simular, a partir de datos censales: si el censo dice que en cierta zona el 22% de los hogares son de cuatro personas y la edad mediana es 31 años, generamos agentes que reproduzcan esa distribución. No son personas reales — son personas estadísticamente plausibles.

### **2.3 Dónde se contagia la gente: capas de contacto**

Cada agente pertenece simultáneamente a varios **contextos** donde puede contagiarse:

* **Hogar** — pocos contactos, pero intensos y diarios. Es donde más se transmite.  
* **Escuela o trabajo** — decenas de contactos, en días laborales.  
* **Comunidad** — transporte, tiendas, eventos. Muchos contactos, breves y aleatorios.

Separar estas capas es lo que da poder al modelo: **cerrar escuelas apaga una capa completa sin tocar las otras**. Ahí es donde se ve el efecto real de una intervención.

### **2.4 Estados de la enfermedad**

Cada agente pasa por esta secuencia:

```
Susceptible → Expuesto → Infeccioso → { Recuperado | Fallecido }
                             │
                             ├── Asintomático  (contagia menos, no se detecta)
                             ├── Leve          (contagia, se queda en casa)
                             └── Grave         (requiere hospitalización)
```

**Importante:** la duración de cada etapa no es un número fijo. Se saca de una distribución de probabilidad, porque en la realidad unos incuban tres días y otros ocho. La probabilidad de terminar en el camino grave depende de la edad del agente.

### **2.5 El paso de tiempo**

La simulación avanza **día por día**. En cada día:

1. Para cada capa de contacto, se identifica quién está infeccioso y con quién convive.  
2. Para cada par infeccioso–susceptible, se calcula la probabilidad de contagio. Depende de: la transmisibilidad base de la enfermedad, qué tan intensa es esa capa, si el infeccioso es asintomático, y qué intervenciones están activas.  
3. Se tira el dado. Los que se contagian pasan a *Expuesto*.  
4. Se avanza el reloj interno de todos los que ya están enfermos: los que terminan de incubar pasan a *Infeccioso*, los que terminan de ser infecciosos pasan a *Recuperado* o *Fallecido*.  
5. Se aplican las intervenciones programadas para ese día.  
6. Se registran los indicadores del día.

Un año simulado son 365 repeticiones de esto sobre un millón de agentes. Por eso necesitamos aceleración por GPU.

### **2.6 Intervenciones**

Una intervención es una **regla con fecha de activación** que modifica el comportamiento del modelo:

| Intervención | Qué hace en el modelo |
| ----- | ----- |
| Cierre de escuelas | Desactiva la capa escuela desde el día X |
| Reducción de aforo | Reduce el número de contactos en la capa comunidad en un % |
| Cubrebocas | Reduce la probabilidad de transmisión en todas las capas |
| Vacunación | Reduce la susceptibilidad de agentes seleccionados, con eficacia parcial y con criterio de prioridad (edad, zona) |
| Testeo y aislamiento | Detecta una fracción de los infecciosos y corta sus contactos fuera del hogar |

El **nivel de cumplimiento** de cada agente modula el efecto: una medida al 100% en el papel no da 100% en la realidad.

Un **escenario** es simplemente un conjunto de intervenciones con sus fechas y parámetros. Es lo que el analista arma y guarda desde la app de escritorio.

### **2.7 Por qué hay que correr cada escenario muchas veces**

El modelo es **estocástico**: usa números aleatorios. Dos corridas del mismo escenario dan resultados distintos, igual que dos brotes reales idénticos no evolucionarían igual.

Por eso cada escenario se corre entre 30 y 50 veces con semillas diferentes, y se reporta la **mediana con una banda de incertidumbre**, no un número solo. Un resultado de una sola corrida no significa nada.

Esto también explica por qué el sistema necesita una cola de trabajos: un escenario no es una simulación, son cincuenta.

### **2.8 Qué produce el simulador**

Por cada corrida:

* Curvas diarias: casos nuevos, casos activos, hospitalizados, fallecidos acumulados  
* Desglose por zona geográfica y por grupo de edad  
* Indicadores resumen: altura del pico, día del pico, tasa de ataque final, días-cama hospitalaria acumulados  
* Estimación de costo: días-persona de actividad económica perdida, más el costo directo de las intervenciones aplicadas

Los dos últimos son clave: **sin un eje económico no se puede comparar nada**, porque la política que salva más vidas siempre es "cerrar todo indefinidamente".

### **2.9 Calibración: hacer que el modelo se parezca a la realidad**

Un simulador sin calibrar es un videojuego. La calibración es lo que lo hace defendible.

El procedimiento:

1. Tomamos una ola epidémica histórica real de la zona metropolitana, con datos abiertos.  
2. Corremos el modelo variando los parámetros que no conocemos con certeza (principalmente la transmisibilidad base y el factor de subregistro de casos).  
3. Medimos qué tanto se parece cada curva simulada a la curva real.  
4. Nos quedamos con el conjunto de parámetros que mejor reproduce lo que efectivamente pasó.

A partir de ahí, ese modelo calibrado es el que se usa para explorar escenarios hipotéticos.

Los datos que capturen los brigadistas desde la app móvil sirven para recalibrar con información fresca, que es la parte que ninguna herramienta existente hace bien.

### **2.10 Comparación de escenarios**

Cada escenario, una vez corrido, se resume en dos números: **muertes** y **costo económico**.

Si graficamos todos los escenarios en un plano con esos dos ejes, se forma una nube de puntos. El borde inferior-izquierdo de esa nube es la **frontera de eficiencia**: son los escenarios donde no puedes mejorar en muertes sin empeorar en costo, ni al revés.

Todo lo que quede arriba y a la derecha de esa frontera es una política que **está siendo superada por otra en ambos criterios** — no hay razón para elegirla.

Esa gráfica es el entregable central del proyecto. No le dice al tomador de decisiones qué hacer: le muestra cuáles son sus opciones reales y qué está intercambiando en cada una.

## **Secciones pendientes de este documento**

* Módulo de microservicios, datos y nube  
* Reparto de trabajo y cronograma por sprints  
* Decisiones técnicas abiertas

