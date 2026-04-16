# CAPÍTULO 1: INTRODUCCIÓN, OBJETIVOS Y PREGUNTAS DE INVESTIGACIÓN

## 1.1 Contexto y Motivación

Barcelona, como una de las principales ciudades europeas, genera una cantidad masiva de datos económicos, sociales y urbanísticos que se encuentran dispersos en múltiples fuentes oficiales: el Instituto Nacional de Estadística (INE), el Institut d'Estadística de Catalunya (Idescat), Red Eléctrica de España (REE), el Ministerio de Transportes (MITMA), el Servicio Público de Empleo Estatal (SEPE) y el portal Open Data Barcelona.

El ciudadano, el emprendedor o el analista que quiere entender la salud económica de la ciudad se enfrenta a un problema de fragmentación: los datos existen, pero no están integrados ni presentados de forma que permitan responder preguntas cotidianas como "¿está subiendo el coste de vida?", "¿hay más empleo que hace un año?" o "¿cuánto cuesta la electricidad en hora punta?".

**ISEU+** (Índice de Salud Económica Urbana) nace para resolver este problema. Es una plataforma que integra datos de múltiples APIs oficiales mediante conectores REST automatizados, los normaliza en un modelo de datos coherente y los presenta a través de una interfaz conversacional (chatbot) y visual que permite a cualquier usuario obtener respuestas claras, trazables y actualizadas sobre la situación económica de Barcelona.


## 1.2 Metodología de Extracción de Datos

A diferencia de los web scrapers tradicionales que extraen información parseando HTML de páginas web, **ISEU+ utiliza APIs REST oficiales** proporcionadas por las instituciones estadísticas. Este enfoque ofrece ventajas significativas:

- **Estabilidad:** Las APIs oficiales tienen contratos de interfaz estables, mientras que el HTML de las webs puede cambiar sin previo aviso.
- **Eficiencia:** Los endpoints JSON devuelven directamente los datos estructurados, sin necesidad de parsing HTML.
- **Legalidad:** Las APIs están diseñadas para ser consumidas por terceros, evitando problemas de términos de servicio.
- **Documentación:** Cada API cuenta con documentación oficial que garantiza la interpretación correcta de los datos.

### APIs Utilizadas

| Fuente | Método | Endpoint API | Formato |
|--------|--------|--------------|---------|
| INE | API REST | servicios.ine.es/wstempus/js/ES | JSON |
| Idescat | API EMEX | api.idescat.cat/emex/v1/dades.json | JSON |
| REE | API REST | apidatos.ree.es/es/datos | JSON |
| MITMA | API REST | apps.fomento.gob.es | JSON |
| Open Data BCN | CKAN API | opendata-ajuntament.barcelona.cat | JSON/CSV |


## 1.3 Objetivos

### Objetivo General

Diseñar, desarrollar y validar una plataforma de inteligencia urbana (ISEU+) que integre datos económicos de fuentes oficiales para Barcelona, permitiendo responder preguntas ciudadanas y de negocio sobre la salud económica de la ciudad con trazabilidad de fuentes y actualización automatizada.

### Objetivos Específicos

**OE1 - Diseño del modelo de datos:** Definir un esquema de datos que integre variables de coste de vida (IPC), mercado laboral (paro, empleo), energía (precios eléctricos), estructura económica (VAB por sectores), demografía y turismo.

**OE2 - Desarrollo de conectores API:** Implementar clientes de API REST automatizados para consumir datos de INE, Idescat, REE, MITMA, SEPE y Open Data Barcelona, con gestión de errores y logs de ejecución.

**OE3 - Construcción de la plataforma web:** Desarrollar una interfaz web con chatbot conversacional que permita realizar consultas en lenguaje natural y visualizar respuestas con gráficos y tablas.

**OE4 - Validación con preguntas reales:** Demostrar que la plataforma puede responder 30 preguntas verificables utilizando exclusivamente los datos recopilados por los conectores API.

**OE5 - Documentación y reproducibilidad:** Documentar la arquitectura, el modelo de datos y los procedimientos de extracción para garantizar la reproducibilidad del proyecto.


## 1.4 Estado de las Fuentes de Datos

| Fuente | Variables | Frecuencia | Estado |
|--------|-----------|------------|--------|
| INE | IPC general, IPC alimentos, tasa paro, tasa empleo | Mensual / Trimestral | ✓ Operativo |
| Idescat | Población, VAB sectores, hoteles, viviendas, IBI | Anual | ✓ Operativo |
| REE | Precio electricidad PVPC, mercado spot, demanda | Horaria | ✓ Operativo |
| MITMA | Precio vivienda m² | Trimestral | ⚠ Pendiente |
| SEPE | Paro registrado | Mensual | ⚠ Manual |
| Open Data BCN | Datos municipales diversos | Variable | ⚠ En desarrollo |


## 1.5 Las 30 Preguntas de Investigación

A continuación se presentan las 30 preguntas que el proyecto ISEU+ debe ser capaz de responder utilizando los datos reales extraídos por los conectores API. Cada pregunta está diseñada para ser verificable con los datos disponibles.

### Bloque A: Inflación y Coste de Vida (IPC)

1. ¿Cómo ha evolucionado el IPC general en Barcelona durante el último año? [INE]
2. ¿En qué meses del año 2024-2025 la inflación alcanzó sus valores máximos? [INE]
3. ¿El IPC de alimentos ha subido más rápido que el IPC general? [INE]
4. ¿Cuál fue la mayor subida mensual del IPC en el período analizado? [INE]
5. ¿El coste de vida actual es más alto que hace exactamente un año? [INE]

### Bloque B: Mercado Laboral

6. ¿Cuál es la tasa de paro actual en Cataluña según los últimos datos? [INE]
7. ¿Ha mejorado o empeorado el empleo en Cataluña respecto al año anterior? [INE]
8. ¿La tasa de empleo supera el 50% de la población en edad de trabajar? [INE]
9. ¿Cuál es la tendencia del mercado laboral en los últimos 18 meses? [INE]
10. ¿La mejora del empleo es consistente trimestre a trimestre? [INE]

### Bloque C: Energía y Electricidad

11. ¿Cuál es el precio medio de la electricidad PVPC en el período analizado? [REE]
12. ¿A qué hora del día es más cara la electricidad (hora punta)? [REE]
13. ¿A qué hora del día es más barata la electricidad (hora valle)? [REE]
14. ¿Cuál es la diferencia de precio entre hora punta y hora valle? [REE]
15. ¿El precio PVPC es consistentemente mayor que el precio del mercado spot? [REE]

### Bloque D: Estructura Económica (VAB)

16. ¿Qué sector económico genera más Valor Añadido Bruto en Barcelona? [Idescat]
17. ¿Qué porcentaje del VAB total representa la hostelería/turismo? [Idescat]
18. ¿La industria tiene un peso relevante en la economía barcelonesa? [Idescat]
19. ¿El comercio supera a la construcción en generación de valor económico? [Idescat]
20. ¿Barcelona depende excesivamente del sector servicios? [Idescat]

### Bloque E: Demografía y Vivienda

21. ¿Cuántas personas viven actualmente en Barcelona según el último censo? [Idescat]
22. ¿La población de Barcelona está creciendo o decreciendo? [Idescat]
23. ¿Cuántas viviendas principales hay por cada 1.000 habitantes? [Idescat]
24. ¿Cuál es la recaudación total por IBI en Barcelona? [Idescat]
25. ¿Cuál es la cuota media de IBI por recibo en la ciudad? [Idescat]

### Bloque F: Turismo e Infraestructura Hotelera

26. ¿Cuántos hoteles hay actualmente en Barcelona? [Idescat]
27. ¿Cuántas plazas hoteleras ofrece la ciudad? [Idescat]
28. ¿Barcelona concentra la mayoría de plazas hoteleras de Cataluña? [Idescat]
29. ¿Cuál es la ratio de plazas hoteleras por cada 1.000 habitantes? [Idescat]
30. ¿El VAB de hostelería es mayor que el VAB de construcción en Barcelona? [Idescat]


## 1.6 Metodología de Validación

Para validar que el proyecto cumple sus objetivos, se seguirá la siguiente metodología:

1. **Extracción automatizada:** Los conectores API recopilan datos de las fuentes oficiales mediante peticiones REST y los almacenan en formato JSON/CSV con metadatos de trazabilidad (fecha de extracción, fuente, estado).

2. **Verificación de cobertura:** Cada una de las 30 preguntas debe poder responderse con los datos disponibles. Se documentará qué variables se utilizan para cada respuesta.

3. **Respuesta cuantitativa:** Las respuestas deben incluir valores numéricos específicos, no generalidades. Por ejemplo: "El IPC general subió de 113.4 a 119.9 puntos", no "El IPC subió".

4. **Trazabilidad:** Cada respuesta debe indicar la fuente de datos, la fecha de actualización y el nivel de confianza.


## 1.7 Estructura del Documento

El resto de este Trabajo de Fin de Máster se organiza de la siguiente manera:

- **Capítulo 2 - Estado del Arte:** Revisión de plataformas de datos urbanos, índices económicos existentes y tecnologías de consumo de APIs.
- **Capítulo 3 - Arquitectura y Diseño:** Modelo de datos, arquitectura de conectores API y diseño de la interfaz web.
- **Capítulo 4 - Implementación:** Desarrollo técnico de clientes API, backend y frontend conversacional.
- **Capítulo 5 - Resultados:** Respuestas a las 30 preguntas de investigación con datos reales.
- **Capítulo 6 - Conclusiones:** Evaluación del proyecto, limitaciones y trabajo futuro.
