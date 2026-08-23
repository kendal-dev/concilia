# CONTEXTO DEL PROYECTO — Hackathon QVAC (Tether)

> Archivo de contexto base. Cargar como referencia / system prompt en el entorno de desarrollo.
> Evento: sábado 12:00 (ARG) → domingo 12:00 (ARG).

---

## 1. El SDK: QVAC

QVAC de Tether es un SDK de IA **100% local**. Ejecuta modelos completamente en el dispositivo del usuario: sin nube, sin claves API, sin datos que salgan de la máquina. Interfaz unificada en:

- **JS/TS**: `@qvac/sdk`
- **Python**: `tetherto-qvac-sdk`

Mismo código en Linux, macOS, Windows, Android e iOS. Licencia Apache 2.0.

Cubre: generación de texto, embeddings, RAG, fine-tuning (LoRA), multimodal, OCR, transcripción, TTS, traducción, batch processing e inferencia delegada P2P.

También incluye un **servidor HTTP con endpoint compatible con OpenAI**: apuntas cualquier herramienta de IA existente a `localhost` y funciona out of the box.

**Por qué importa:** local = privado (documentos financieros, datos de salud, registros personales nunca salen del dispositivo), barato (sin factura de inferencia) y offline-capable. La restricción interesante: se trabaja con **modelos pequeños**; el reto real es lograr que un modelo de **1–4B** haga trabajo útil de forma **confiable**.

---

## 2. Premios

Pool total: hasta **$2,000 USDt** — $1,500 en los dos premios de proyecto + $500 del pool Vault Guardian. Distribuido a discreción de los jueces según mérito, calidad, originalidad e impacto.

| Puesto | Monto | Tema |
|---|---|---|
| 🥇 1º | $1,000 USDt | **Agentes locales que reemplazan trabajo de operaciones** — automatización de back-office: trabajo que hoy requiere un equipo de personas leyendo documentos y haciendo juicios. Construir un agente que corra on-device. |
| 🥈 2º | $500 USDt | **Modelos pequeños, tareas difíciles: uso de herramientas y confiabilidad** — lograr que un modelo local pequeño encadene herramientas correctamente (sin olvidar pasos, ignorar resultados o inventar respuestas). |
| 🛡️ Extra | $500 USDt | **Vault Guardian** — no juzgado, no ligado al proyecto. Se reparte entre todos los que lo superen. |

---

## 3. Las dos pistas

### 🥇 Pista 1 — Agentes locales para trabajo de operaciones

Una categoría entera de back-office es gente leyendo documentos, detectando discrepancias y escalando lo que importa. Alto volumen, alto valor, y toca datos que las empresas realmente **no pueden** mandar a una API de terceros. Hogar natural de la IA local.

Ideas propuestas por el track:

- **Reconciliación de facturas.** Ingerir facturas (PDF, fotos, escaneos) con OCR, extraer line items, cruzar contra órdenes de compra o extractos bancarios, y marcar desajustes con una explicación que un humano verifica en cinco segundos. *Es el caso de uso emblemático; si lo clavas, eres competitivo.*
- **Flujo post-trigger de riesgo crediticio.** No el scoring en sí, sino las operaciones alrededor: un umbral se dispara → recuperar documentos relevantes, resumir exposición, redactar la nota interna, proponer siguientes acciones, rutear a la persona correcta.
- **Análisis de pagos y transacciones.** Triaje de anomalías sobre logs de transacciones, categorización de comercios, detección de cargos duplicados, resúmenes en lenguaje natural de "qué cambió este mes y por qué".
- **NLP-a-finanzas, en general.** Cualquier cosa que convierta texto o documentos no estructurados en producto financiero estructurado: términos de contrato → cronograma de pagos, recibos de gastos → libro mayor, hilo de email → tarea de conciliación.
- **Comprensión multimodal de documentos.** Foto de un recibo con mala iluminación → datos estructurados. Albarán de entrega manuscrito → line items. Combinar OCR con un modelo multimodal en un solo pipeline.

**Qué hace fuerte una entrega aquí:** funciona sobre entradas reales y desordenadas, no sobre un PDF limpio elegido a mano. Muestra su razonamiento para que un humano lo audite. Y es honesta sobre lo que no puede hacer — **un agente que marca incertidumbre gana a uno que alucina un número con confianza**.

### 🥈 Pista 2 — Uso de herramientas y fiabilidad de modelo pequeño

Los modelos pequeños fallan de formas específicas y reconocibles: olvidan un paso a mitad de cadena, ignoran lo que la herramienta realmente devolvió y responden de memoria, o inventan un resultado cuando la llamada falla. Hacer que un modelo 1–4B encadene herramientas limpiamente es un problema de ingeniería real, y esa es la totalidad de esta pista.

- **Encadenamiento multi-paso.** Un agente que llama búsqueda externa, calculadora, base de datos local y lector de archivos en secuencia, y **usa genuinamente** lo que sale, sin perder contexto a mitad de camino.
- **Respuestas fundamentadas en fuentes vivas.** Conectar el modelo local a búsqueda o API externa para anclar la salida en lo recuperado, y demostrar que **se niega a responder** en lugar de confabular cuando la herramienta no devuelve nada útil.
- **Ingeniería de fiabilidad.** Capas de validación, reintentos, salida estructurada, pases de auto-verificación. Mostrar los modos de fallo encontrados y cómo se diseñó alrededor de ellos.

**Qué hace fuerte una entrega aquí:** evidencia, no vibras. Ejecutar la misma tarea N veces y mostrar la tasa de éxito. Mostrar los fallos que **no** pudiste arreglar tanto como los que sí — un proyecto que mapea honestamente dónde se rompe un modelo pequeño vale más que uno que demuestra una sola corrida limpia.

### 🛡️ Vault Guardian (desafío extra)

Abierto a todos, independiente del proyecto. $500 USDt repartidos entre todos los que lo superen (cuantos más lo logren, más chica cada tajada — conviene ser temprano).

Es un juego de **prompt injection** local: un defensor IA guarda un secreto, chateas con él y tratas de que lo filtre. Toda la inferencia corre localmente vía `@qvac/sdk` sobre el runtime **Bare** (sin nube, sin llamadas API). Para el hackathon, el Guardian tiene una wallet WDK con **fondos reales**. Convéncelo de liberarlos. La implementación de referencia se comparte durante el hackathon.

---

## 4. Requisitos técnicos (reglas de oro)

### Obligatorio

- **QVAC como capa de inferencia**: `@qvac/sdk` (JS/TS) o `tetherto-qvac-sdk` (Python). Toda la inferencia del modelo debe correr localmente.
- Usar el **servidor HTTP OpenAI-compatible de QVAC** cuenta como proveedor de modelo local. Llamar a una API de modelo en la nube **no** cuenta.
- El desafío Vault Guardian es **separado** de la entrega del proyecto; se puede entrar compitiendo o no por un premio.

### Hardware y modelos

- Revisar primero los requisitos del sistema: plataformas soportadas, runtimes y matriz de compatibilidad.
- **Presupuestar la RAM.** Un modelo 4B en Q4 necesita ~4 GB y es el techo práctico en una laptop normal; 8B quiere ~8 GB. Los modelos se descargan una vez en la primera ejecución (~2.5 GB para un 4B).
- Modelos en Hugging Face (`huggingface.co/qvac`), pero se puede usar cualquier modelo abierto de preferencia.

### Dos advertencias antes de planificar la build

- ⚠️ **VisionPsy NO está soportado aún por el SDK.** La visión en QVAC es buena, pero no vía VisionPsy por ahora. Usar las capacidades **multimodal y OCR** del SDK en su lugar.
- ⚠️ **Evitar generación de imagen y video.** Existen en el SDK y son divertidas, pero la calidad de salida no está donde debería para una entrega juzgada. Proyectos apoyados en eso no puntúan bien.

### Reutilización de código

- Se puede reutilizar código existente; solo se juzga lo construido durante el hackathon.
- **La integración de QVAC debe ser nueva**, escrita este fin de semana.
- **No atornillar QVAC en paralelo.** Un proyecto que ya tiene su propia capa de IA en la nube y simplemente agrega QVAC al lado por el premio queda descartado. La inferencia local tiene que hacer **trabajo real** en el producto.

### Codificación asistida por IA

Permitida y alentada — QVAC trae un servidor OpenAI-compatible precisamente para que lo conectes a tus herramientas existentes. **Pero revisa lo que escribe tu modelo.** La orquestación de modelos pequeños es fácil de falsificar y difícil de hacer bien. Se descartan sin más revisión:

- métodos del SDK alucinados,
- rutas de código muerto,
- un README que describe capacidades que no existen,
- una demo que solo funciona sobre una entrada seleccionada.

Ejecuta la cosa sobre entradas que **no** elegiste de antemano antes de enviarla.

---

## 5. Qué debe incluir la entrega

- [ ] **Repo público** con README que explique qué construiste y qué capacidades y modelos de QVAC usaste.
- [ ] **Permalinks a la integración de QVAC** — links directos de GitHub a los archivos/líneas donde ocurre la inferencia. *Es lo primero que miran los jueces, hazlo fácil.*
- [ ] **Video demo grabado** (async) mostrándolo funcionando localmente, de extremo a extremo.
- [ ] **Detalles de modelo y hardware**: qué modelo, qué cuantización, en qué máquina lo corriste, latencia aproximada.
- [ ] **Instrucciones de setup** que funcionen desde un clon limpio.

---

## 6. Recursos

### Documentación
- Home: https://docs.qvac.tether.io/
- Introducción y conceptos: https://docs.qvac.tether.io/introduction/
- Requisitos del sistema / matriz de compatibilidad: https://docs.qvac.tether.io/system-requirements/
- Quickstart JS/TS: https://docs.qvac.tether.io/js-ts-sdk/
- Quickstart Python: https://docs.qvac.tether.io/python-sdk/
- Referencia API: https://docs.qvac.tether.io/reference/api/
- Troubleshooting: https://docs.qvac.tether.io/troubleshooting/

### Capacidades más relevantes para estas pistas
- Generación de texto: https://docs.qvac.tether.io/ai-capabilities/text-generation/
- OCR: https://docs.qvac.tether.io/ai-capabilities/ocr/
- Multimodal: https://docs.qvac.tether.io/ai-capabilities/multimodal/
- RAG: https://docs.qvac.tether.io/ai-capabilities/rag/
- Text embeddings: https://docs.qvac.tether.io/ai-capabilities/text-embeddings/
- Fine-tuning (LoRA): https://docs.qvac.tether.io/ai-capabilities/fine-tuning/
- Batch processing: https://docs.qvac.tether.io/ai-capabilities/batch-processing/
- Transcripción: https://docs.qvac.tether.io/ai-capabilities/transcription/
- Voice assistant: https://docs.qvac.tether.io/ai-capabilities/voice-assistant/
- Inferencia delegada (P2P): https://docs.qvac.tether.io/p2p-capabilities/delegated-inference/

### Herramientas
- CLI: https://docs.qvac.tether.io/cli/
- Servidor HTTP OpenAI-compatible: https://docs.qvac.tether.io/cli/http-server/
- Configuración y plugins: https://docs.qvac.tether.io/configuration/
- Ciclo de vida de descarga de modelos: https://docs.qvac.tether.io/models/download-lifecycle/
- Tutorial Electron: https://docs.qvac.tether.io/tutorials/electron/
- Tutorial Expo: https://docs.qvac.tether.io/tutorials/expo/

### Modelos e investigación
- Overview de modelos: https://qvac.tether.io/models/
- Hugging Face: https://huggingface.co/qvac
- LLM Fabric (motor de fine-tuning): https://qvac.tether.io/dev/fabric
- Genesis (dataset sintético de pre-entrenamiento): https://qvac.tether.io/dev/genesis

### Vault Guardian
- Implementación de referencia: se comparte durante el hackathon
- Runtime Bare: https://bare.pears.com

### Comunidad y soporte
- GitHub: https://github.com/tetherto/qvac
- Discord: https://discord.com/invite/tetherdev
- Blog: https://qvac.tether.io/blog
- X / Twitter: https://x.com/QVAC
- QV.AC (ver QVAC en acción): https://qv.ac

---

## 7. Logística del evento

**Mentoría** — Raquel, DevRel · Telegram `@rraigal`. IRL y online; tema dedicado en el grupo de Telegram del hackathon, los hackers hacen ping a los mentores cuando los necesitan. Para preguntas técnicas más profundas, los mentores derivan a los canales donde vive el equipo de QVAC: Discord (`discord.com/invite/tetherdev`) y Keet. Los mentores están especialmente disponibles el **sábado** (día pico de soporte y orientación).

**Jueces** — Raquel, DevRel. El juicio arranca el **domingo 23 a las 13:00 ARG**, durante ~4 h. Todo online. La demo es **async**: se graba y se adjunta a la entrega del proyecto.

**Workshop** — *"IA local que realmente se envía: QVAC Essentials y buenas prácticas de codificación con IA"* · **sábado 9:30 ARG**, en vivo en el venue y transmitido online.

Cubre todo lo necesario para construir en QVAC este fin de semana: instalar el SDK, cargar y correr un modelo localmente, elegir el modelo adecuado para la RAM que realmente tienes, y configurar las capacidades que más recompensan estas pistas — OCR, comprensión multimodal de documentos, RAG y tool calling. También: dónde se rompen los modelos pequeños, y los patrones de validación y salida estructurada que los mantienen honestos.

Segunda mitad: codificar con asistentes de IA sin enviar slop — cómo aterrizar tu asistente en el SDK real, por qué los métodos alucinados son el fallo más común en entregas de hackathon, y cómo probar sobre entradas que no elegiste. Llevar laptop: se sale con un modelo corriendo localmente y un esqueleto de proyecto sobre el que construir.

---
---

# DOCUMENTO DE DISEÑO ARQUITECTÓNICO Y ESTRATÉGICO

## Proyecto: Sistema de Reconciliación Automática de Facturas (Local-First)

**Tracks objetivo:** Pista 1 (agentes locales para operaciones) **y** Pista 2 (uso de herramientas y fiabilidad de modelo pequeño).

### 1. Visión general del proyecto

Este proyecto se enmarca en un hackathon competitivo cuyo objetivo central es demostrar la viabilidad y fiabilidad de la IA de ejecución 100% local.

La meta es construir un **Agente de Reconciliación de Facturas** que resuelva un problema crítico del back-office corporativo: la necesidad de humanos leyendo documentos sucios, extrayendo datos y comparándolos manualmente contra un ERP.

El sistema automatiza el proceso de ingesta → extracción → validación cruzada → emisión de juicios preliminares (triaje), permitiendo que un humano audite la decisión final en **menos de cinco segundos**.

### 2. Restricciones críticas del entorno

Violar cualquiera de estas resulta en descalificación inmediata:

- **Privacidad absoluta (zero-cloud).** Toda la inferencia del modelo debe ocurrir localmente a través de QVAC — vía su SDK en Python `tetherto-qvac-sdk`, o vía su servidor HTTP local compatible con OpenAI apuntando a `localhost`. Bajo ninguna circunstancia el código puede llamar a APIs externas de modelos comerciales (OpenAI en la nube, Anthropic, Gemini, etc.).
- **Limitaciones de hardware y modelo.** El entorno de ejecución es una laptop estándar. El límite práctico de RAM dicta un modelo pequeño de **1B–4B**, típicamente cuantizado Q4 para ocupar ~4 GB.
- **Restricción multimodal específica.** El proyecto requiere extraer texto de imágenes de facturas (OCR y comprensión visual), pero **QVAC no soporta VisionPsy** actualmente. Toda la capacidad de visión debe gestionarse exclusivamente con las capacidades **multimodal y OCR nativas del SDK de QVAC**.
- **El desafío de la fiabilidad (Pista 2).** Los modelos 1B–4B son intrínsecamente propensos a fallar en tareas lógicas complejas: olvidan pasos, ignoran resultados de herramientas, alucinan formatos y confabulan respuestas. El éxito de este proyecto **no** se mide por crear un *happy path* irreal, sino por la **ingeniería de fiabilidad**: el sistema debe anticipar estos fallos, atrapar errores de formato y orquestar reintentos automáticos.

### 3. Stack tecnológico seleccionado

| Capa | Tecnología | Rol |
|---|---|---|
| Lógica y orquestación | **Python** | El cerebro del sistema. No solo lenguaje de backend: es el *orquestador de herramientas*. Coordina las llamadas al modelo de IA, interpreta las respuestas y gestiona el flujo de datos. |
| Datos / simulación de ERP | **MariaDB** | Simula el sistema de registros de la empresa. Almacena una tabla de Órdenes de Compra con la verdad absoluta sobre lo que la empresa espera pagar. |
| Interfaz y demostración | **Streamlit** | "Dashboard del Operador", construido ultra rápido. Visualiza no solo el resultado final, sino que expone a los jueces el flujo de pensamiento del agente, el uso de herramientas en tiempo real y el manejo de errores. |

### 4. Arquitectura conceptual — el flujo de valor

El sistema está diseñado para evitar la **amnesia de contexto**: si se le pide a un modelo pequeño que extraiga datos y analice la base de datos simultáneamente, fracasará. Por eso el flujo se divide en pasos discretos orquestados por Python.

**Fase 1 — Ingesta y visión (el mundo real)**
El operador sube la fotografía de una factura o recibo. La calidad del documento será intencionalmente baja (arrugas, mala iluminación) para demostrar robustez. Esta imagen se envía al agente.

**Fase 2 — Extracción estricta (OCR y parseo)**
El orquestador de Python solicita al modelo local (vía QVAC) que analice la imagen. El objetivo en esta fase **no es razonar**, sino actuar como transcriptor inteligente. El modelo tiene instrucción estricta de extraer identificadores clave (ej. NIT/CUIT del proveedor) y el monto total cobrado, y devolver esta información **exclusivamente en JSON estructurado**. Aquí reside la primera capa de fiabilidad: si el modelo devuelve texto no válido, Python lo intercepta y fuerza un reintento (*self-correction loop*).

**Fase 3 — Uso de herramientas y retrieval (RAG causal)**
Una vez que Python tiene el JSON limpio de la Fase 2, **el modelo de IA se detiene**. Python toma el identificador extraído (NIT) y ejecuta una consulta SQL contra MariaDB (la herramienta externa). La base de datos devuelve el registro oficial de la Orden de Compra asociada, indicando cuánto esperaba pagar la empresa realmente.

**Fase 4 — Razonamiento y triaje (fundamentación)**
Python inicia una segunda llamada al modelo local. Esta vez le entrega dos bloques de datos limpios: *"datos extraídos de la factura física"* y *"datos recuperados del ERP (MariaDB)"*. La tarea del modelo ahora es actuar como auditor: comparar ambos registros, detectar si existe una discrepancia, y redactar una nota interna concisa explicando la situación.

> Ej.: *"Discrepancia detectada: la factura cobra $150, pero la orden de compra autorizada es por $140. Verificar sobrecargo con el proveedor."*

**Fase 5 — Presentación auditable**
El resultado se presenta en la interfaz de Streamlit. El operador humano ve el dictamen del agente (la nota interna) y, fundamentalmente, puede ver lado a lado los datos que generaron esa decisión — logrando una auditoría completa en segundos y demostrando que la respuesta de la IA está **fundamentada en fuentes vivas** y no en alucinaciones.

### 5. Meta de desarrollo

Construir este motor de herramientas de forma **modular**. El código debe evidenciar que:

1. **Python está al mando** (el LLM es una herramienta, no el orquestador).
2. Las responsabilidades están **separadas**: Visión → Base de datos → Razonamiento.
3. El sistema **sobrevive a la volatilidad** inherente de trabajar con un LLM de 4B ejecutado en una laptop.
