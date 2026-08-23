-- Ordenes de compra de prueba (Bolivia: NIT sin guiones, montos en Bs, IVA 13%).
-- Elegidas para ejercitar los cuatro veredictos y todos los checks deterministas.
-- El caso NO_PO_FOUND se cubre con un NIT que deliberadamente NO esta aqui.

SET NAMES utf8mb4;

INSERT INTO purchase_orders (id, po_number, supplier_tax_id, supplier_name, currency, total_amount, status, issued_at) VALUES
    (1, 'OC-101', '4820156023', 'Importadora Santa Cruz SRL',   'BOB',  3390.00, 'OPEN',      '2026-07-02'),
    (2, 'OC-104', '1029384756', 'Papelera Andina SA',           'BOB',  1243.50, 'RECEIVED',  '2026-07-06'),
    (3, 'OC-107', '7788990011', 'Ferreteria El Constructor',    'BOB', 12600.00, 'OPEN',      '2026-07-11'),
    -- El caso del mockup: 20 cajas a Bs 85.00. La factura cobrara 24.
    (4, 'OC-113', '1023874015', 'Distribuidora del Oriente',    'BOB',  1700.00, 'OPEN',      '2026-07-15'),
    (5, 'OC-118', '3344556677', 'Transportes Chuquisaca SRL',   'BOB',  5882.50, 'RECEIVED',  '2026-07-19'),
    (6, 'OC-121', '9911223344', 'Cafe Illimani SRL',            'BOB',   452.00, 'CLOSED',    '2026-07-21'),
    (7, 'OC-125', '5566778899', 'Metalurgica Potosi SA',        'BOB', 18750.00, 'CANCELLED', '2026-07-24'),
    (8, 'OC-130', '2233445566', 'Servicios Integrales Beni SRL','BOB',  6400.00, 'OPEN',      '2026-08-03'),
    -- Segunda orden del mismo proveedor que OC-101: obliga a desambiguar.
    (9, 'OC-135', '4820156023', 'Importadora Santa Cruz SRL',   'BOB',  5200.00, 'OPEN',      '2026-08-10');

INSERT INTO po_line_items (po_id, description, quantity, unit_price, line_total) VALUES
    -- OC-101 -> 3390.00 (match exacto)
    (1, 'Resma papel bond A4',            30.000,   45.00,  1350.00),
    (1, 'Toner laser negro',               6.000,  340.00,  2040.00),
    -- OC-104 -> 1243.50 (la factura traera una suma de lineas descuadrada)
    (2, 'Cuaderno empastado A5',          45.000,   18.50,   832.50),
    (2, 'Boligrafo azul caja x50',         6.000,   68.50,   411.00),
    -- OC-107 -> 12600.00 (sobrecargo grande)
    (3, 'Taladro percutor 800W',          12.000, 1050.00, 12600.00),
    -- OC-113 -> 1700.00 (mockup: cantidad facturada 24 vs 20 autorizadas)
    (4, 'Aceite comestible caja x12',     20.000,   85.00,  1700.00),
    -- OC-118 -> 5882.50 (multi-linea; la factura agrega una linea que no figura)
    (5, 'Flete Santa Cruz - La Paz',       3.000, 1250.00,  3750.00),
    (5, 'Flete La Paz - Oruro',            2.000,  620.00,  1240.00),
    (5, 'Seguro de carga',                 1.000,  692.50,   692.50),
    (5, 'Gestion aduanera',                1.000,  200.00,   200.00),
    -- OC-121 -> 452.00 (la factura traera el IVA mal calculado)
    (6, 'Cafe en grano 1kg',               8.000,   56.50,   452.00),
    -- OC-125 -> 18750.00 (orden CANCELADA: cobrar contra ella es un problema)
    (7, 'Perfil de acero 6m',             25.000,  750.00, 18750.00),
    -- OC-130 -> 6400.00 (subcobro)
    (8, 'Mantenimiento HVAC mensual',      4.000, 1600.00,  6400.00),
    -- OC-135 -> 5200.00
    (9, 'Archivador metalico 4 gavetas',   8.000,  650.00,  5200.00);

-- === DATASET CONCILIA (generado por scripts/gen_seed_erp.py) ===
-- No editar a mano: regenerar con scripts/gen_seed_erp.py.
-- 21 ordenes contra los recibos reales de data/receipts/.
-- Sin orden a proposito (NO_PO_FOUND esperado): R015 (LIGHTROOM GALLERY SDN BHD), R016 (LIGHTROOM GALLERY SDN BHD), R025 (MR. D.I.Y. (M) SDN BHD), R026 (99 SPEED MART S/B), R030 (Pinturas Monopol Ltda.), R031 (Pinturas Monopol Ltda.).
-- Omitidos por no tener NIT legible en la imagen: R005, R013.

INSERT INTO purchase_orders
    (id, po_number, supplier_tax_id, supplier_name, currency, total_amount, status, issued_at) VALUES
    (100, 'OC-200', '933109-X', 'MR D.I.Y. (JOHOR) SDN BHD', 'MYR', 33.90, 'OPEN', '2019-01-12'),  -- R002 - par exacto
    (101, 'OC-201', '000849813504', 'YONGFATT ENTERPRISE', 'MYR', 80.90, 'OPEN', '2018-12-25'),  -- R003 - par exacto
    (102, 'OC-202', '002116837376', 'SOON HUAT MACHINERY ENTERPRISE', 'MYR', 327.00, 'OPEN', '2019-01-11'),  -- R006 - par exacto
    (103, 'OC-203', '000394528768', 'AIK HUAT HARDWARE ENTERPRISE (SETIA ALAM) SDN BHD', 'MYR', 15.00, 'OPEN', '2017-06-15'),  -- R011 - par exacto
    (104, 'OC-204', '001637511168', 'HOME MASTER HARDWARE & ELECTRICAL', 'MYR', 15.90, 'OPEN', '2017-12-22'),  -- R012 - par exacto
    (105, 'OC-205', '000689913856', 'TEO HENG STATIONERY & BOOKS', 'MYR', 4.90, 'OPEN', '2018-01-18'),  -- R019 - par exacto
    (106, 'OC-206', '001601310720', 'FUYI MINI MARKET', 'MYR', 9.00, 'OPEN', '2018-01-25'),  -- R020 - par exacto
    (107, 'OC-207', '000689913856', 'TEO HENG STATIONERY & BOOKS', 'MYR', 27.55, 'OPEN', '2018-01-17'),  -- R021 - par exacto
    (108, 'OC-208', '000689913856', 'TEO HENG STATIONERY & BOOKS', 'MYR', 18.00, 'OPEN', '2018-01-23'),  -- R023 - par exacto
    (109, 'OC-209', '000549584896', 'C W KHOO HARDWARE SDN BHD', 'MYR', 21.20, 'OPEN', '2018-03-01'),  -- R027 - par exacto
    (110, 'OC-210', '5900398', 'Pinturas Monopol Ltda.', 'BOB', 639.73, 'OPEN', '2026-02-11'),  -- R028 - par exacto
    (111, 'OC-211', '801580-T', 'S.H.H. MOTOR (SUNGAI RENGIT) SDN. BHD.', 'MYR', 20.00, 'OPEN', '2019-01-23'),  -- R007 - par exacto
    (112, 'OC-212', '001006288896', 'SAM SAM TRADING CO', 'MYR', 14.10, 'OPEN', '2017-12-29'),  -- R010 - par exacto
    (113, 'OC-213', '000800589824', 'PERNIAGAAN ZHENG HUI', 'MYR', 121.46, 'OPEN', '2018-02-12'),  -- R008 - total alterado (transposicion); factura cobra 112.46
    (114, 'OC-214', '000504664064', 'GERBANG ALAF RESTAURANTS SDN BHD', 'MYR', 30.06, 'OPEN', '2018-01-18'),  -- R009 - total alterado (iva_13); factura cobra 26.60
    (115, 'OC-215', '001609584640', 'ASIA MART', 'MYR', 3.27, 'OPEN', '2017-12-22'),  -- R014 - total alterado (decimal_corrido); factura cobra 32.70
    (116, 'OC-216', '001090105344', 'SHELL ISNI PETRO TRADING', 'MYR', 68.00, 'OPEN', '2018-03-18'),  -- R017 - total alterado (transposicion); factura cobra 86.00
    (117, 'OC-217', '002046390272', 'SYL ROASTED DELIGHTS SDN. BHD.', 'MYR', 61.59, 'OPEN', '2018-03-06'),  -- R018 - total alterado (iva_13); factura cobra 54.50
    (118, 'OC-218', '000689913856', 'TEO HENG STATIONERY & BOOKS', 'MYR', 551.00, 'OPEN', '2018-01-15'),  -- R022 - total alterado (decimal_corrido); factura cobra 55.10
    (119, 'OC-219', '000689913856', 'TEO HENG STATIONERY & BOOKS', 'MYR', 135.35, 'OPEN', '2018-02-12'),  -- R024 - total alterado (transposicion); factura cobra 153.35
    (120, 'OC-220', '5900398', 'Pinturas Monopol Ltda.', 'BOB', 1360.20, 'OPEN', '2026-05-22');  -- R029 - total alterado (transposicion); factura cobra 1630.20

INSERT INTO po_line_items (po_id, description, quantity, unit_price, line_total) VALUES
    (100, 'Compra segun comprobante R002', 1.000, 33.90, 33.90),
    (101, 'Compra segun comprobante R003', 1.000, 80.90, 80.90),
    (102, 'Compra segun comprobante R006', 1.000, 327.00, 327.00),
    (103, 'Compra segun comprobante R011', 1.000, 15.00, 15.00),
    (104, 'Compra segun comprobante R012', 1.000, 15.90, 15.90),
    (105, 'Compra segun comprobante R019', 1.000, 4.90, 4.90),
    (106, 'Compra segun comprobante R020', 1.000, 9.00, 9.00),
    (107, 'Compra segun comprobante R021', 1.000, 27.55, 27.55),
    (108, 'Compra segun comprobante R023', 1.000, 18.00, 18.00),
    (109, 'Compra segun comprobante R027', 1.000, 21.20, 21.20),
    (110, 'Compra segun comprobante R028', 1.000, 639.73, 639.73),
    (111, 'Compra segun comprobante R007', 1.000, 20.00, 20.00),
    (112, 'Compra segun comprobante R010', 1.000, 14.10, 14.10),
    (113, 'Compra segun comprobante R008', 1.000, 121.46, 121.46),
    (114, 'Compra segun comprobante R009', 1.000, 30.06, 30.06),
    (115, 'Compra segun comprobante R014', 1.000, 3.27, 3.27),
    (116, 'Compra segun comprobante R017', 1.000, 68.00, 68.00),
    (117, 'Compra segun comprobante R018', 1.000, 61.59, 61.59),
    (118, 'Compra segun comprobante R022', 1.000, 551.00, 551.00),
    (119, 'Compra segun comprobante R024', 1.000, 135.35, 135.35),
    (120, 'Compra segun comprobante R029', 1.000, 1360.20, 1360.20);

-- === FIN DATASET CONCILIA ===
