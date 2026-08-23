# Resultados — 31 recibos reales

Modelo de extraccion: **Qwen3.5-4B-Q4_K_M** (contexto 4096 tokens)  
OCR: **latin_g2** + **craft_mlt_25k** (pipeline `easyocr`, backend `cpu`)  
Toda la inferencia corre en el dispositivo. Cero llamadas de red.

**Veredicto correcto en 24 de 31 recibos (77%).**

## Veredictos

| Esperado | Recibos | Correctos | Errores |
|---|---|---|---|
| `MATCH` | 13 | 9 | 4 |
| `MISMATCH` | 10 | 8 | 2 |
| `NO_PO_FOUND` | 3 | 3 | 0 |
| `UNCERTAIN` | 5 | 4 | 1 |

## Extraccion por campo

Devolver `null` no cuenta como error: el sistema prefiere abstenerse antes
que inventar un numero, y esa es la conducta que el track premia.

| Campo | Correcto | Incorrecto | No leido |
|---|---|---|---|
| NIT del proveedor | 19/31 | 6 | 6 |
| Total | 26/31 | 5 | 0 |

## Verificacion contra el texto del OCR

Cada valor extraido se busca en el texto crudo que produjo el OCR. Un valor
que no aparece ahi es un valor inventado.

| Campo | Verificados | No hallados |
|---|---|---|
| `invoice_number` | 30 | 0 |
| `subtotal` | 23 | 2 |
| `supplier_tax_id` | 23 | 2 |
| `tax_amount` | 19 | 2 |
| `total_amount` | 27 | 4 |

## Por condicion fisica del documento

| Condicion | Aciertos |
|---|---|
| limpio | 11/13 (85%) |
| sombra | 6/8 (75%) |
| termico_descolorido | 5/6 (83%) |
| torcido | 5/6 (83%) |
| borroso | 2/3 (67%) |
| manuscrito | 2/2 (100%) |
| recortado | 0/1 (0%) |
| arrugado | 1/1 (100%) |

## Latencia

| Metrica | Valor |
|---|---|
| Mediana por documento | 19.58 s |
| P95 | 51.31 s |
| Maxima | 52.31 s |
| Mediana solo OCR | 10.00 s |
| Reintentos de extraccion | 0 |

## Detalle por documento

| Recibo | Origen | Esperado | Obtenido | OC | Delta | NIT | Total | Reint. | s |
|---|---|---|---|---|---|---|---|---|---|
| R001 | sroie | `UNCERTAIN` | `UNCERTAIN` | - | - | null | MAL | 0 | 34.4 |
| R002 | sroie | `MATCH` | `MATCH` | OC-200 | 0.00 | ok | ok | 0 | 16.19 |
| R003 | sroie | `MATCH` | `MATCH` | OC-201 | 0.01 | ok | ok | 0 | 14.12 |
| R004 | sroie | `UNCERTAIN` | `UNCERTAIN` | - | - | null | ok | 0 | 47.32 |
| R005 | sroie | `UNCERTAIN` | `UNCERTAIN` | - | - | null | MAL | 0 | 24.94 |
| R006 | sroie | `MATCH` | `MATCH` | OC-202 | 0.00 | ok | ok | 0 | 19.58 |
| R007 | sroie | `MATCH` | `UNCERTAIN` ⟵ | - | - | null | ok | 0 | 29.82 |
| R008 | sroie | `MISMATCH` | `MISMATCH` | OC-213 | -9.00 | ok | ok | 0 | 24.49 |
| R009 | sroie | `MISMATCH` | `MISMATCH` | OC-214 | -3.46 | ok | ok | 0 | 17.94 |
| R010 | sroie | `MATCH` | `MATCH` | OC-212 | 0.00 | ok | ok | 0 | 18.79 |
| R011 | sroie | `MATCH` | `NO_PO_FOUND` ⟵ | - | - | MAL | MAL | 0 | 13.25 |
| R012 | sroie | `MATCH` | `NO_PO_FOUND` ⟵ | - | - | MAL | ok | 0 | 13.71 |
| R013 | sroie | `UNCERTAIN` | `UNCERTAIN` | - | - | null | ok | 0 | 52.31 |
| R014 | sroie | `MISMATCH` | `MISMATCH` | OC-215 | 29.43 | ok | ok | 0 | 22.71 |
| R015 | sroie | `NO_PO_FOUND` | `NO_PO_FOUND` | - | - | ok | ok | 0 | 15.02 |
| R016 | sroie | `NO_PO_FOUND` | `NO_PO_FOUND` | - | - | ok | ok | 0 | 15.64 |
| R017 | sroie | `MISMATCH` | `NO_PO_FOUND` ⟵ | - | - | MAL | ok | 0 | 10.7 |
| R018 | sroie | `MISMATCH` | `MISMATCH` | OC-217 | 2.91 | ok | MAL | 0 | 23.24 |
| R019 | sroie | `MATCH` | `MATCH` | OC-205 | 0.00 | ok | ok | 0 | 16.42 |
| R020 | sroie | `MATCH` | `MATCH` | OC-206 | 0.00 | ok | ok | 0 | 17.45 |
| R021 | sroie | `MATCH` | `MATCH` | OC-207 | 0.00 | ok | ok | 0 | 20.61 |
| R022 | sroie | `MISMATCH` | `MISMATCH` | OC-207 | 27.55 | ok | ok | 0 | 20.58 |
| R023 | sroie | `MATCH` | `MATCH` | OC-208 | 0.00 | ok | ok | 0 | 19.53 |
| R024 | sroie | `MISMATCH` | `NO_PO_FOUND` ⟵ | - | - | MAL | ok | 0 | 26.28 |
| R025 | sroie | `UNCERTAIN` | `NO_PO_FOUND` ⟵ | - | - | MAL | ok | 0 | 17.08 |
| R026 | sroie | `NO_PO_FOUND` | `NO_PO_FOUND` | - | - | MAL | MAL | 0 | 15.52 |
| R027 | sroie | `MATCH` | `MATCH` | OC-209 | 0.00 | ok | ok | 0 | 16.84 |
| R028 | boliviano_real | `MATCH` | `UNCERTAIN` ⟵ | - | - | null | ok | 0 | 51.62 |
| R029 | boliviano_real | `MISMATCH` | `MISMATCH` | OC-220 | 270.00 | ok | ok | 0 | 50.56 |
| R030 | boliviano_real | `MISMATCH` | `MISMATCH` | OC-210 | 178.22 | ok | ok | 0 | 50.06 |
| R031 | boliviano_real | `MISMATCH` | `MISMATCH` | OC-210 | 50.06 | ok | ok | 0 | 51.31 |

Cada corrida deja su contrato completo, con el texto crudo del OCR y la
traza por fases, en `logs/runs/<recibo>.json`.
