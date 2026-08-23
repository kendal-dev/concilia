# dataset_map.md - contrato entre el dataset y el libro de gastos

Fuente unica de verdad para el runner de evaluacion (`eval/runner.py`).
Generado por `scripts/gen_dataset.py`. Si cambia el dataset, se regenera todo junto:
`ground_truth.json`, `seed.sql` y esta tabla.

## Procedencia del dataset

- **4 facturas bolivianas reales** (Pinturas Monopol Ltda., Santa Cruz, Bs, fotos giradas 90 grados).
- **27 tickets del corpus publico SROIE** (recibos escaneados de comercios de Malasia, en MYR).
  Aportan suciedad real: termicos descoloridos, sombras de escaneo, sellos superpuestos,
  arrugas y anotaciones manuscritas. **Esta procedencia se declara en el README y en
  `docs/limitations.md`** - el sistema no afirma haberlos recolectado en Bolivia.

## Reparto de veredictos

| Recibos | Cantidad | Veredicto esperado | Como se planta |
|---|---|---|---|
| R002, R003, R005, R006, R011, R012, R013, R016, R019, R020, R021, R023, R027, R028 | 14 | `MATCH` | par exacto proveedor+fecha+monto |
| R008, R009, R014, R017, R018, R022, R024, R029 | 8 | `MISMATCH` | monto alterado en el libro |
| R015, R025, R026, R030, R031 | 5 | `NO_MATCH` | sin registro en el libro |
| R001, R004, R007, R010 | 4 | `MATCH` o `UNCERTAIN` | par exacto, pero imagen degradada: si el OCR no lee, `UNCERTAIN` cuenta como acierto |

Total: 31 recibos. Libro (`gastos_esperados`): 42 registros, 26 proveedores.

## Alteraciones plantadas en los MISMATCH

| Recibo | Real | Libro | Patron | Explicacion que debe generar |
|---|---|---|---|---|
| R008 | 112.46 | 121.46 | `transposicion` | digitos transpuestos |
| R009 | 26.60 | 30.06 | `iva_13` | diferencia de ~13% (IVA no registrado) |
| R014 | 32.70 | 3.27 | `decimal_corrido` | corrimiento de decimal (~10x) |
| R017 | 86.00 | 68.00 | `transposicion` | digitos transpuestos |
| R018 | 54.50 | 61.59 | `iva_13` | diferencia de ~13% (IVA no registrado) |
| R022 | 55.10 | 551.00 | `decimal_corrido` | corrimiento de decimal (~10x) |
| R024 | 153.35 | 135.35 | `transposicion` | digitos transpuestos |
| R029 | 1630.20 | 1360.20 | `transposicion` | digitos transpuestos |

## Casos extra plantados en el libro

- **2 duplicados**: copia exacta (proveedor+fecha+monto) de los registros de R003 y R020
  -> debe dispararse la deteccion de cargo duplicado.
- **14 registros de ruido**: gastos legitimos sin recibo asociado. Evitan que
  `NO_MATCH` sea trivial y obligan al fuzzy de proveedor a discriminar de verdad.

## Tabla completa recibo -> esperado

| Recibo | Proveedor | Fecha | Total | Moneda | Condicion | Origen | Esperado |
|---|---|---|---|---|---|---|---|
| R001 | INDAH GIFT & HOME DECO | 2018-10-19 | 60.30 | MYR | termico_descolorido | sroie | `MATCH|UNCERTAIN` |
| R002 | MR D.I.Y. (JOHOR) SDN BHD | 2019-01-12 | 33.90 | MYR | limpio | sroie | `MATCH` |
| R003 | YONGFATT ENTERPRISE | 2018-12-25 | 80.90 | MYR | limpio | sroie | `MATCH` |
| R004 | MR D.I.Y. (M) SDN BHD | 2018-11-18 | 30.90 | MYR | termico_descolorido, sombra | sroie | `MATCH|UNCERTAIN` |
| R005 | ABC HO TRADING | 2019-01-09 | 31.00 | MYR | limpio | sroie | `MATCH` |
| R006 | SOON HUAT MACHINERY ENTERPRISE | 2019-01-11 | 327.00 | MYR | limpio | sroie | `MATCH` |
| R007 | S.H.H. MOTOR (SUNGAI RENGIT) SDN. BHD. | 2019-01-23 | 20.00 | MYR | termico_descolorido | sroie | `MATCH|UNCERTAIN` |
| R008 | PERNIAGAAN ZHENG HUI | 2018-02-12 | 112.46 | MYR | borroso, torcido | sroie | `MISMATCH` |
| R009 | GERBANG ALAF RESTAURANTS SDN BHD | 2018-01-18 | 26.60 | MYR | manuscrito, sombra | sroie | `MISMATCH` |
| R010 | SAM SAM TRADING CO | 2017-12-29 | 14.10 | MYR | termico_descolorido, sombra | sroie | `MATCH|UNCERTAIN` |
| R011 | AIK HUAT HARDWARE ENTERPRISE (SETIA ALAM) SDN BHD | 2017-06-15 | 15.00 | MYR | recortado, sombra | sroie | `MATCH` |
| R012 | HOME MASTER HARDWARE & ELECTRICAL | 2017-12-22 | 15.90 | MYR | borroso | sroie | `MATCH` |
| R013 | RESTORAN HASSANBISTRO | 2017-12-28 | 15.00 | MYR | borroso | sroie | `MATCH` |
| R014 | ASIA MART | 2017-12-22 | 32.70 | MYR | sombra, termico_descolorido | sroie | `MISMATCH` |
| R015 | LIGHTROOM GALLERY SDN BHD | 2017-11-20 | 39.80 | MYR | torcido, sombra | sroie | `NO_MATCH` |
| R016 | LIGHTROOM GALLERY SDN BHD | 2017-12-20 | 73.00 | MYR | sombra | sroie | `MATCH` |
| R017 | SHELL ISNI PETRO TRADING | 2018-03-18 | 86.00 | MYR | limpio | sroie | `MISMATCH` |
| R018 | SYL ROASTED DELIGHTS SDN. BHD. | 2018-03-06 | 54.50 | MYR | limpio, manuscrito | sroie | `MISMATCH` |
| R019 | TEO HENG STATIONERY & BOOKS | 2018-01-18 | 4.90 | MYR | limpio | sroie | `MATCH` |
| R020 | FUYI MINI MARKET | 2018-01-25 | 9.00 | MYR | limpio | sroie | `MATCH` |
| R021 | TEO HENG STATIONERY & BOOKS | 2018-01-17 | 27.55 | MYR | limpio | sroie | `MATCH` |
| R022 | TEO HENG STATIONERY & BOOKS | 2018-01-15 | 55.10 | MYR | arrugado | sroie | `MISMATCH` |
| R023 | TEO HENG STATIONERY & BOOKS | 2018-01-23 | 18.00 | MYR | limpio | sroie | `MATCH` |
| R024 | TEO HENG STATIONERY & BOOKS | 2018-02-12 | 153.35 | MYR | sombra | sroie | `MISMATCH` |
| R025 | MR. D.I.Y. (M) SDN BHD | 2018-03-14 | 37.10 | MYR | limpio | sroie | `NO_MATCH` |
| R026 | 99 SPEED MART S/B | 2018-01-24 | 2.50 | MYR | limpio | sroie | `NO_MATCH` |
| R027 | C W KHOO HARDWARE SDN BHD | 2018-03-01 | 21.20 | MYR | limpio | sroie | `MATCH` |
| R028 | Pinturas Monopol Ltda. | 2026-02-11 | 639.73 | BOB | torcido | boliviano_real | `MATCH` |
| R029 | Pinturas Monopol Ltda. | 2026-05-22 | 1630.20 | BOB | torcido | boliviano_real | `MISMATCH` |
| R030 | Pinturas Monopol Ltda. | 2026-07-30 | 817.95 | BOB | torcido, termico_descolorido | boliviano_real | `NO_MATCH` |
| R031 | Pinturas Monopol Ltda. | 2026-01-07 | 689.79 | BOB | torcido | boliviano_real | `NO_MATCH` |
