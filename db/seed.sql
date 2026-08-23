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
