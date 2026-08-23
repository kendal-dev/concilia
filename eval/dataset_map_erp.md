# dataset_map_erp.md - oraculo de la evaluacion contra el ERP

Generado por `scripts/gen_seed_erp.py`. **No se escribe a mano**: el veredicto
esperado se obtiene simulando el mismo `lookup_purchase_order` del backend
(busqueda por NIT, desempate por monto mas cercano). Decidirlo de memoria
produciria expectativas falsas, porque varios recibos comparten proveedor.

## Procedencia

- 4 facturas bolivianas reales (Pinturas Monopol Ltda., Santa Cruz).
- 27 tickets del corpus publico SROIE (comercios de Malasia, en MYR).
  Aportan la suciedad real que el track exige: termicos descoloridos, sombras
  de escaneo, sellos superpuestos, arrugas y anotaciones manuscritas.

## Distribucion esperada

| Veredicto | Recibos |
|---|---|
| `MATCH` | 13 |
| `MISMATCH` | 10 |
| `NO_PO_FOUND` | 3 |
| `UNCERTAIN` | 5 |

Total: 31 recibos, 21 ordenes sembradas.

## Detalle

| Recibo | Proveedor | NIT legible | Total factura | Orden | Total orden | Esperado | Por que |
|---|---|---|---|---|---|---|---|
| R001 | INDAH GIFT & HOME DECO | - | 60.3 | - | - | `UNCERTAIN` | sin NIT o sin total legible en la imagen |
| R002 | MR D.I.Y. (JOHOR) SDN BHD | 933109-X | 33.9 | OC-200 | 33.90 | `MATCH` | coincide con la orden sembrada |
| R003 | YONGFATT ENTERPRISE | 000849813504 | 80.9 | OC-201 | 80.90 | `MATCH` | coincide con la orden sembrada |
| R004 | MR D.I.Y. (M) SDN BHD | - | 30.9 | - | - | `UNCERTAIN` | sin NIT o sin total legible en la imagen |
| R005 | ABC HO TRADING | - | 31.0 | - | - | `UNCERTAIN` | sin NIT o sin total legible en la imagen |
| R006 | SOON HUAT MACHINERY ENTERPRISE | 002116837376 | 327.0 | OC-202 | 327.00 | `MATCH` | coincide con la orden sembrada |
| R007 | S.H.H. MOTOR (SUNGAI RENGIT) SDN. BHD. | 801580-T | 20.0 | OC-211 | 20.00 | `MATCH` | coincide con la orden sembrada |
| R008 | PERNIAGAAN ZHENG HUI | 000800589824 | 112.46 | OC-213 | 121.46 | `MISMATCH` | delta -9.00 contra OC-213 |
| R009 | GERBANG ALAF RESTAURANTS SDN BHD | 000504664064 | 26.6 | OC-214 | 30.06 | `MISMATCH` | delta -3.46 contra OC-214 |
| R010 | SAM SAM TRADING CO | 001006288896 | 14.1 | OC-212 | 14.10 | `MATCH` | coincide con la orden sembrada |
| R011 | AIK HUAT HARDWARE ENTERPRISE (SETIA ALAM) SDN BHD | 000394528768 | 15.0 | OC-203 | 15.00 | `MATCH` | coincide con la orden sembrada |
| R012 | HOME MASTER HARDWARE & ELECTRICAL | 001637511168 | 15.9 | OC-204 | 15.90 | `MATCH` | coincide con la orden sembrada |
| R013 | RESTORAN HASSANBISTRO | - | 15.0 | - | - | `UNCERTAIN` | sin NIT o sin total legible en la imagen |
| R014 | ASIA MART | 001609584640 | 32.7 | OC-215 | 3.27 | `MISMATCH` | delta +29.43 contra OC-215 |
| R015 | LIGHTROOM GALLERY SDN BHD | 000584089600 | 39.8 | - | - | `NO_PO_FOUND` | ninguna orden con el NIT 000584089600 |
| R016 | LIGHTROOM GALLERY SDN BHD | 000584089600 | 73.0 | - | - | `NO_PO_FOUND` | ninguna orden con el NIT 000584089600 |
| R017 | SHELL ISNI PETRO TRADING | 001090105344 | 86.0 | OC-216 | 68.00 | `MISMATCH` | delta +18.00 contra OC-216 |
| R018 | SYL ROASTED DELIGHTS SDN. BHD. | 002046390272 | 54.5 | OC-217 | 61.59 | `MISMATCH` | delta -7.09 contra OC-217 |
| R019 | TEO HENG STATIONERY & BOOKS | 000689913856 | 4.9 | OC-205 | 4.90 | `MATCH` | coincide con la orden sembrada |
| R020 | FUYI MINI MARKET | 001601310720 | 9.0 | OC-206 | 9.00 | `MATCH` | coincide con la orden sembrada |
| R021 | TEO HENG STATIONERY & BOOKS | 000689913856 | 27.55 | OC-207 | 27.55 | `MATCH` | coincide con la orden sembrada |
| R022 | TEO HENG STATIONERY & BOOKS | 000689913856 | 55.1 | OC-207 | 27.55 | `MISMATCH` | delta +27.55 contra OC-207 |
| R023 | TEO HENG STATIONERY & BOOKS | 000689913856 | 18.0 | OC-208 | 18.00 | `MATCH` | coincide con la orden sembrada |
| R024 | TEO HENG STATIONERY & BOOKS | 000689913856 | 153.35 | OC-219 | 135.35 | `MISMATCH` | delta +18.00 contra OC-219 |
| R025 | MR. D.I.Y. (M) SDN BHD | - | 37.1 | - | - | `UNCERTAIN` | sin NIT o sin total legible en la imagen |
| R026 | 99 SPEED MART S/B | 000181747712 | 2.5 | - | - | `NO_PO_FOUND` | ninguna orden con el NIT 000181747712 |
| R027 | C W KHOO HARDWARE SDN BHD | 000549584896 | 21.2 | OC-209 | 21.20 | `MATCH` | coincide con la orden sembrada |
| R028 | Pinturas Monopol Ltda. | 5900398 | 639.73 | OC-210 | 639.73 | `MATCH` | coincide con la orden sembrada |
| R029 | Pinturas Monopol Ltda. | 5900398 | 1630.2 | OC-220 | 1360.20 | `MISMATCH` | delta +270.00 contra OC-220 |
| R030 | Pinturas Monopol Ltda. | 5900398 | 817.95 | OC-210 | 639.73 | `MISMATCH` | delta +178.22 contra OC-210 |
| R031 | Pinturas Monopol Ltda. | 5900398 | 689.79 | OC-210 | 639.73 | `MISMATCH` | delta +50.06 contra OC-210 |

Sin orden sembrada por no tener NIT legible: R005, R013. Inventar un NIT que no esta en la imagen seria la clase de trampa que este proyecto dice no hacer.
