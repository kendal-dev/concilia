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
| `subtotal` | 22 | 2 |
| `supplier_tax_id` | 23 | 2 |
| `tax_amount` | 17 | 3 |
| `total_amount` | 28 | 3 |

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
| Mediana por documento | 19.81 s |
| P95 | 49.53 s |
| Maxima | 51.90 s |
| Mediana solo OCR | 9.83 s |
| Reintentos de extraccion | 0 |

## Detalle por documento

| Recibo | Origen | Esperado | Obtenido | OC | Delta | NIT | Total | Reint. | s |
|---|---|---|---|---|---|---|---|---|---|
| R001 | sroie | `UNCERTAIN` | `UNCERTAIN` | - | - | null | MAL | 0 | 37.24 |
| R002 | sroie | `MATCH` | `MATCH` | OC-200 | 0.00 | ok | ok | 0 | 16.98 |
| R003 | sroie | `MATCH` | `MATCH` | OC-201 | 0.01 | ok | ok | 0 | 16.55 |
| R004 | sroie | `UNCERTAIN` | `UNCERTAIN` | - | - | null | ok | 0 | 49.26 |
| R005 | sroie | `UNCERTAIN` | `UNCERTAIN` | - | - | null | MAL | 0 | 25.27 |
| R006 | sroie | `MATCH` | `MATCH` | OC-202 | 0.00 | ok | ok | 0 | 19.81 |
| R007 | sroie | `MATCH` | `UNCERTAIN` ⟵ | - | - | null | ok | 0 | 26.91 |
| R008 | sroie | `MISMATCH` | `MISMATCH` | OC-213 | -9.00 | ok | ok | 0 | 24.73 |
| R009 | sroie | `MISMATCH` | `MISMATCH` | OC-214 | -3.46 | ok | ok | 0 | 14.94 |
| R010 | sroie | `MATCH` | `MATCH` | OC-212 | 0.00 | ok | ok | 0 | 15.73 |
| R011 | sroie | `MATCH` | `NO_PO_FOUND` ⟵ | - | - | MAL | MAL | 0 | 11.94 |
| R012 | sroie | `MATCH` | `NO_PO_FOUND` ⟵ | - | - | MAL | ok | 0 | 13.77 |
| R013 | sroie | `UNCERTAIN` | `UNCERTAIN` | - | - | null | ok | 0 | 47.39 |
| R014 | sroie | `MISMATCH` | `MISMATCH` | OC-215 | 29.43 | ok | ok | 0 | 21.48 |
| R015 | sroie | `NO_PO_FOUND` | `NO_PO_FOUND` | - | - | ok | ok | 0 | 14.49 |
| R016 | sroie | `NO_PO_FOUND` | `NO_PO_FOUND` | - | - | ok | ok | 0 | 15.48 |
| R017 | sroie | `MISMATCH` | `NO_PO_FOUND` ⟵ | - | - | MAL | ok | 0 | 9.78 |
| R018 | sroie | `MISMATCH` | `MISMATCH` | OC-217 | 2.91 | ok | MAL | 0 | 20.85 |
| R019 | sroie | `MATCH` | `MATCH` | OC-205 | 0.00 | ok | ok | 0 | 15.62 |
| R020 | sroie | `MATCH` | `MATCH` | OC-206 | 0.00 | ok | ok | 0 | 15.21 |
| R021 | sroie | `MATCH` | `MATCH` | OC-207 | 0.00 | ok | ok | 0 | 19.9 |
| R022 | sroie | `MISMATCH` | `MISMATCH` | OC-207 | 27.55 | ok | ok | 0 | 22.57 |
| R023 | sroie | `MATCH` | `MATCH` | OC-208 | 0.00 | ok | ok | 0 | 19.09 |
| R024 | sroie | `MISMATCH` | `NO_PO_FOUND` ⟵ | - | - | MAL | ok | 0 | 21.74 |
| R025 | sroie | `UNCERTAIN` | `NO_PO_FOUND` ⟵ | - | - | MAL | ok | 0 | 16.47 |
| R026 | sroie | `NO_PO_FOUND` | `NO_PO_FOUND` | - | - | MAL | MAL | 0 | 14.66 |
| R027 | sroie | `MATCH` | `MATCH` | OC-209 | 0.00 | ok | ok | 0 | 15.4 |
| R028 | boliviano_real | `MATCH` | `UNCERTAIN` ⟵ | - | - | null | ok | 0 | 48.92 |
| R029 | boliviano_real | `MISMATCH` | `MISMATCH` | OC-220 | 270.00 | ok | ok | 0 | 51.9 |
| R030 | boliviano_real | `MISMATCH` | `MISMATCH` | OC-210 | 178.22 | ok | ok | 0 | 49.53 |
| R031 | boliviano_real | `MISMATCH` | `MISMATCH` | OC-210 | 50.06 | ok | ok | 0 | 49.89 |

Cada corrida deja su contrato completo, con el texto crudo del OCR y la
traza por fases, en `logs/runs/<recibo>.json`.
