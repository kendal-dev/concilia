CREATE TABLE proveedores (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  nombre        VARCHAR(120) NOT NULL,
  nombre_norm   VARCHAR(120) NOT NULL,   -- minúsculas, sin tildes, para fuzzy
  nit           VARCHAR(20),
  INDEX idx_norm (nombre_norm)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE gastos_esperados (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  proveedor_id  INT NOT NULL,
  fecha         DATE NOT NULL,
  monto         DECIMAL(12,2) NOT NULL,
  categoria     VARCHAR(60),
  descripcion   VARCHAR(255),
  conciliado    BOOLEAN DEFAULT FALSE,
  FOREIGN KEY (proveedor_id) REFERENCES proveedores(id),
  INDEX idx_fecha_monto (fecha, monto),
  INDEX idx_prov_fecha (proveedor_id, fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE conciliaciones (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  receipt_id        VARCHAR(40) NOT NULL,
  gasto_id          INT NULL,
  veredicto         ENUM('MATCH','MISMATCH','NO_MATCH','UNCERTAIN') NOT NULL,
  delta             DECIMAL(12,2),
  confianza         DECIMAL(4,3),
  explicacion       VARCHAR(255),
  revision_humana   BOOLEAN DEFAULT FALSE,
  contrato_json     JSON,
  creado_en         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (gasto_id) REFERENCES gastos_esperados(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;