# Limites conocidos

Este documento existe porque un agente que marca lo que no puede hacer vale mas que
uno que devuelve un numero con confianza injustificada. Todos los casos de abajo son
reales, salieron de la corrida sobre los 31 documentos del dataset, y se pueden
reproducir: cada uno cita su archivo en `logs/runs/`, con el texto crudo del OCR.

---

## 1. El OCR pierde caracteres en papel termico descolorido

**El limite mas duro del sistema, y el que mas veredictos cuesta.**

`R012` — el registro tributario del emisor:

```
OCR:       GST Reg No. .0016375t116
Real:      001637511168
Extraido:  0016375t116
```

El OCR leyo un `1` como `t` y perdio digitos del final. El modelo **copio literalmente
lo que vio**, que es exactamente lo que se le pidio: el prompt dice "no completes lo
que no ves", y no completo. El error nacio en la imagen, no en el razonamiento.

`R011` — el mismo problema, mas severo:

```
OCR:       Gst #o; 0u0g4528768
Real:      000394528768
```

`R007` — un solo caracter:

```
OCR:       801580-7
Real:      801580-T
```

**Consecuencia:** el ERP se consulta por identificador tributario. Un identificador
mal leido no encuentra su orden de compra, y el sistema responde `NO_PO_FOUND` cuando
la orden existe. Es un falso negativo, no una alucinacion: el agente nunca invento un
numero, simplemente no pudo leer el correcto.

**Que se intento:** bajar `magRatio` y `canvasSize` mejoro la velocidad seis veces sin
degradar la lectura, pero no recupera caracteres que el papel ya no tiene. Un
reconocedor mas grande del registry (`latin_g2` es el mas capaz de la familia easyocr
disponible) podria ayudar; no se probo por tiempo.

**Que NO se hizo, a proposito:** no se agrego un emparejamiento difuso de
identificadores contra el ERP. Un fuzzy sobre NITs cerraria estos casos, pero
convertiria un falso negativo visible en un falso positivo silencioso: el sistema
diria "esta factura corresponde a esta orden" sin que sea cierto. En conciliacion de
pagos, ese error es mucho peor.

---

## 2. El modelo puede pegar dos numeros vecinos

`R024`:

```
OCR:       GST Ne.
           000689913856
Extraido:  9481000689913856
```

El identificador correcto esta ahi, pero el modelo lo concateno con digitos de una
linea contigua. Es un error de transcripcion del modelo, no del OCR — un 4B
cuantizado leyendo una lista de codigos de barras en columnas.

Se detecta pero no se corrige: el verificador confirma que `000689913856` aparece en
el texto, y aun asi el valor extraido no sirve para buscar.

---

## 3. `source_span` prueba procedencia, no correccion

El verificador busca cada valor extraido dentro del texto crudo del OCR. Si no
aparece, el valor fue inventado. **Eso descarta la alucinacion, no el error de
interpretacion.**

`R002` es el ejemplo claro. El modelo devolvio:

```
invoice_number: "1851-A"
```

y el verificador lo marco correcto con similitud 1.0 — porque `1851-A` **si** esta en
el texto del OCR. Solo que esta en la linea de la direccion (`Lot 1851-A`), no en el
numero de factura.

El detector hace lo que promete y nada mas. Vale la pena decirlo en voz alta porque es
facil confundir "verificado contra la fuente" con "correcto".

---

## 4. Documentos girados: se rescatan, pero se pagan

Las cuatro facturas bolivianas del dataset estan fotografiadas de costado y **no traen
etiqueta EXIF de orientacion**, asi que no hay forma de saberlo sin mirar el
resultado.

La primera lectura de `R028` devolvio texto ilegible y el sistema respondio
`UNCERTAIN`. Correcto, pero incompleto: el problema era la orientacion. La escalada
automatica detecta que la lectura no dio ni identificador ni total, prueba 0/90/180/270
grados y se queda con la mejor. Con eso `R028` pasa a leerse entero:

```
Pinturas Monopol Ltda
Factura No.  03784
NIT/CI  5900398
Fecha  11/02/2026
Total Bs  639.73
```

**El costo:** cuatro pasadas de OCR mas una segunda extraccion. Un documento derecho
tarda ~15 s; uno que escala, ~50 s. Por eso la escalada no corre de entrada.

---

## 5. Las facturas de Monopol no imprimen el NIT del emisor

En los cuatro documentos bolivianos, el unico identificador tributario impreso es el
**del cliente** (`NIT/CI 5900398`). El del proveedor viaja dentro del codigo QR, que
el OCR no decodifica.

El ERP se sembro contra el identificador que si es legible, y queda declarado aca.
Inventar un NIT que no esta en la imagen habria sido exactamente la clase de trampa
que este proyecto dice no hacer.

**Efecto lateral, visible en los resultados:** las cuatro facturas comparten ese
identificador, asi que el lookup encuentra varias ordenes candidatas y desempata por
monto mas cercano. Para `R030` y `R031` elige una orden que no es la suya y reporta
`MISMATCH` con un delta que no significa nada. El sistema hace lo correcto con los
datos que tiene; los datos no alcanzan.

**Y algo mas interesante.** Al agregar al prompt la regla que distingue el registro de
empresa del identificador tributario (seccion 2), el modelo dejo de usar ese NIT en
`R028`: reconoce que esta bajo "Nombre SILVER FUENTES NUNEZ" y que por lo tanto es del
cliente, no del emisor. Devuelve `null` y el sistema responde `UNCERTAIN`.

Contra el oraculo eso cuenta como error, y sin embargo **el modelo tiene razon y el
oraculo esta mal**: la orden se sembro contra un identificador que no es del proveedor
porque no hay otro legible. Se deja asi, contado como fallo, en vez de ajustar la
expectativa para que el numero quede mejor.

Lo que si es un limite real: `R029`, `R030` y `R031` tienen el mismo layout y ahi el
modelo si uso el NIT del cliente. Cuatro documentos identicos, dos comportamientos.
Esa inconsistencia es propia de un modelo de 4B cuantizado y no se resolvio.

---

## 6. Los items de linea se leen mal en tickets de supermercado

En `R002` el modelo devolvio `quantity: 24` para una tabla de picar. El `24` del
ticket es parte del codigo de producto, no la cantidad. La suma de las lineas dio 725
contra un total de 33,90.

La verificacion aritmetica determinista marca la incoherencia, que es para lo que
existe. Pero significa que **el desglose por linea no es confiable en tickets de
punto de venta**, donde codigos, cantidades y precios comparten columnas estrechas.
Los totales, en cambio, se leen bien en 26 de 31 documentos.

---

## 7. Procedencia del dataset

De los 31 documentos:

- **4 son facturas bolivianas reales** (Pinturas Monopol Ltda., Santa Cruz).
- **27 son del corpus publico SROIE**, tickets escaneados de comercios de Malasia,
  en ringgit.

Los del corpus aportan la suciedad que el track pide — termicos descoloridos, sombras
de escaneo, sellos superpuestos, arrugas, anotaciones manuscritas — pero **no fueron
recolectados por este equipo**, y el sistema no afirma lo contrario en ningun lado.

Consecuencia practica: los importes estan en MYR y los identificadores son GST
malayos, no NITs bolivianos. El pipeline es agnostico a eso (el prompt acepta ambos
formatos y las comparaciones son numericas), pero la demo se ve menos "local" de lo
que el caso de uso sugiere.

---

## 8. La auto-aprobacion no se disparo ni una vez

En los 31 documentos, `auto_approved` es **false en los 31**. No es un bug: es la
politica funcionando como se diseno.

`all_clear()` exige que **todos** los checks esten en `PASS`, y un `SKIPPED` no
cuenta como aprobado. En tickets de punto de venta el desglose por linea no se lee
de forma confiable (seccion 6), asi que `suma de lineas` e `impuestos` quedan en
`SKIPPED` casi siempre. Con eso la puerta nunca se abre.

La alternativa habria sido tratar `SKIPPED` como aprobado. Eso auto-aprobaria
facturas cuya aritmetica interna nunca se verifico, que es exactamente el pago que
esta funcion existe para no dejar pasar. **No verificar no es lo mismo que verificar
con exito**, y en conciliacion de pagos esa distincion es la funcion entera.

Lo que si significa en la practica: sobre este dataset, el agente triajea y ordena
la cola, pero no descarga trabajo automaticamente. Para que lo haga harian falta
facturas con desglose legible — que es el caso de las bolivianas de proveedor
formal, no el de los tickets de comercio.

---

## 9. Lo que no se probo

- **Backend Vulkan.** Toda la corrida es en CPU. El addon soporta `vulkan` y la
  maquina tiene una RTX 4070, pero no se midio el efecto en latencia ni se verifico
  que el detector y el modelo de texto convivan en 8 GB de VRAM.
- **El pipeline docTR** (`db_mobilenet_v3_large` + `crnn_mobilenet_v3_small`). Se
  eligio easyocr porque `latin_g2` cubre espanol; docTR podria leer mejor los
  termicos y no se comparo.
- **Modelos de texto mas grandes.** Todo con `Qwen3.5-4B-Q4_K_M`. No se midio si un
  8B o 9B corrige los errores de transcripcion de la seccion 2.
- **Documentos multipagina y PDFs.** El pipeline recibe una imagen por documento.
