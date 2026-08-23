-- ERP simulado + traza de auditoria del agente de reconciliacion.
-- Se carga automaticamente por /docker-entrypoint-initdb.d en el primer arranque.
-- OJO: solo corre sobre un volumen vacio. Para recrear: docker compose down -v

SET NAMES utf8mb4;

-- ---------------------------------------------------------------
-- Fuente de verdad: lo que la empresa autorizo pagar.
-- ---------------------------------------------------------------
CREATE TABLE purchase_orders (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    po_number       VARCHAR(32)  NOT NULL UNIQUE,
    supplier_tax_id VARCHAR(32)  NOT NULL,
    supplier_name   VARCHAR(160) NOT NULL,
    currency        CHAR(3)      NOT NULL DEFAULT 'BOB',
    total_amount    DECIMAL(12,2) NOT NULL,
    status          ENUM('OPEN','RECEIVED','CLOSED','CANCELLED') NOT NULL DEFAULT 'OPEN',
    issued_at       DATE         NOT NULL,
    -- El agente busca por NIT, asi que ese es el indice que importa.
    INDEX idx_supplier_tax_id (supplier_tax_id)
) ENGINE=InnoDB;

CREATE TABLE po_line_items (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    po_id       INT           NOT NULL,
    description VARCHAR(255)  NOT NULL,
    quantity    DECIMAL(12,3) NOT NULL,
    unit_price  DECIMAL(12,2) NOT NULL,
    line_total  DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_line_po FOREIGN KEY (po_id)
        REFERENCES purchase_orders(id) ON DELETE CASCADE,
    INDEX idx_po_id (po_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- Lo que el agente extrajo del documento fisico.
-- ---------------------------------------------------------------
CREATE TABLE invoices (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    source_filename VARCHAR(255) NOT NULL,
    supplier_tax_id VARCHAR(32)  NULL,
    invoice_number  VARCHAR(64)  NULL,
    subtotal        DECIMAL(12,2) NULL,
    tax_amount      DECIMAL(12,2) NULL,
    total_amount    DECIMAL(12,2) NULL,
    -- JSON crudo de la fase de extraccion, tal como lo valido Pydantic.
    raw_extraction  JSON         NULL,
    -- El documento original queda en disco; aca solo la ruta para poder servirlo.
    document_path   VARCHAR(512) NULL,
    content_type    VARCHAR(128) NULL,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_inv_supplier (supplier_tax_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- El dictamen + la traza completa que lo justifica.
-- ---------------------------------------------------------------
CREATE TABLE reconciliations (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    invoice_id   INT NOT NULL,
    po_id        INT NULL,
    verdict      ENUM('MATCH','MISMATCH','NO_PO_FOUND','UNCERTAIN') NOT NULL,
    -- Politica de auto-aprobacion resuelta en codigo, guardada para el dashboard.
    auto_approved BOOLEAN NOT NULL DEFAULT FALSE,
    amount_delta DECIMAL(12,2) NULL,
    note         TEXT NULL,
    -- Resultado de las verificaciones deterministas (calculadas por Python).
    checks       JSON NULL,
    -- AgentTrace serializado: cada fase con entrada, salida, duracion y reintentos.
    trace        JSON NULL,
    -- El agente triajea; el humano decide. Queda registrado quien y cuando.
    human_decision ENUM('PENDING','APPROVED','ESCALATED') NOT NULL DEFAULT 'PENDING',
    decided_by   VARCHAR(120) NULL,
    decided_at   TIMESTAMP NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_rec_invoice FOREIGN KEY (invoice_id)
        REFERENCES invoices(id) ON DELETE CASCADE,
    CONSTRAINT fk_rec_po FOREIGN KEY (po_id)
        REFERENCES purchase_orders(id) ON DELETE SET NULL,
    INDEX idx_rec_verdict (verdict),
    INDEX idx_rec_decision (human_decision)
) ENGINE=InnoDB;
