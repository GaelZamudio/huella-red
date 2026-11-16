-- Datos mínimos y ficticios para que la demo funcione. Repetible.
INSERT INTO zona (id_zona, colonia, municipio, entidad) VALUES
  (1, 'Roma Norte', 'Cuauhtémoc', 'Ciudad de México'),
  (2, 'Del Valle', 'Benito Juárez', 'Ciudad de México'),
  (3, 'Santa Úrsula Coapa', 'Coyoacán', 'Ciudad de México')
ON CONFLICT DO NOTHING;

INSERT INTO persona (id_persona, nombres, ap_paterno, ap_materno, telefono, correo) VALUES
  (1, 'Ana', 'Torres', 'Luna', '5512345678', 'ana.torres@example.com'),
  (2, 'Luis', 'Ramírez', NULL, '5587654321', 'luis.ramirez@example.com')
ON CONFLICT DO NOTHING;

INSERT INTO rescatista (id_persona, vehiculo_propio, disponibilidad) VALUES
  (1, TRUE, 'fines de semana'),
  (2, FALSE, 'tardes')
ON CONFLICT DO NOTHING;