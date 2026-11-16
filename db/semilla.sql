-- Datos ficticios de demostracion. Repetible (ON CONFLICT DO NOTHING).
INSERT INTO zona (id_zona, colonia, municipio, entidad) VALUES
 (1,'Roma Norte','Cuauhtémoc','Ciudad de México'),(2,'Del Valle','Benito Juárez','Ciudad de México'),
 (3,'Santa Úrsula Coapa','Coyoacán','Ciudad de México') ON CONFLICT DO NOTHING;
INSERT INTO persona (id_persona, nombres, ap_paterno, ap_materno, telefono, correo) VALUES
 (1,'Ana','Torres','Luna','5512345678','ana.torres@example.com'),(2,'Luis','Ramírez',NULL,'5587654321','luis.ramirez@example.com'),
 (3,'Mariana','Soto','Vega','5511223344','mariana.soto@example.com'),(4,'Diego','Herrera',NULL,'5599887766','diego.herrera@example.com')
 ON CONFLICT DO NOTHING;
INSERT INTO rescatista (id_persona, vehiculo_propio, disponibilidad) VALUES (1,TRUE,'fines de semana'),(2,FALSE,'tardes') ON CONFLICT DO NOTHING;
INSERT INTO adoptante (id_persona, tipo_vivienda, tiene_patio, otras_mascotas) VALUES (3,'casa',TRUE,FALSE),(4,'departamento',FALSE,TRUE) ON CONFLICT DO NOTHING;
INSERT INTO hogar_temporal (id_hogar, alias, calle, numero, cp, capacidad_max, id_persona, id_zona) VALUES
 (1,'Casa Ana','Av. Coyoacán','120','03100',4,1,2) ON CONFLICT DO NOTHING;
INSERT INTO rescate (id_rescate, descripcion_lugar, fecha_hora, condicion_inicial, tipo_ingreso, id_zona) VALUES
 (1,'Debajo de un puente peatonal','2026-10-20 09:30','Desnutrida y con heridas leves','rescate_en_calle',1),
 (2,'Estacionamiento de un supermercado','2026-10-28 18:10','Con frío y sin vacunas','reporte_ciudadano',2),
 (3,'Entrega de una familia','2026-11-05 12:00','Buen estado general','entrega_voluntaria',3) ON CONFLICT DO NOTHING;
INSERT INTO rescate_rescatista (id_rescate, id_persona) VALUES (1,1),(2,2),(3,1) ON CONFLICT DO NOTHING;
INSERT INTO animal (id_animal, nombre, especie, sexo, fecha_nacimiento_aprox, color, senas, estado_actual, id_rescate) VALUES
 (1,'Canela','perro','hembra','2024-03-01','Café','Mancha blanca en el pecho','disponible_adopcion',1),
 (2,'Max','perro','macho','2025-06-15','Negro',NULL,'en_hogar_temporal',1),
 (3,'Luna','gato','hembra','2025-09-01','Gris','Ojos verdes','disponible_adopcion',2),
 (4,'Michi','gato','macho','2026-05-10','Naranja',NULL,'en_atencion',2),
 (5,'Kiwi','otro','macho','2025-11-20','Blanco','Orejas caídas','rescatado',3),
 (6,'Rocky','perro','macho','2023-01-10','Dorado',NULL,'disponible_adopcion',3) ON CONFLICT DO NOTHING;
INSERT INTO perro (id_animal, tamano, nivel_energia, apto_con_ninos) VALUES (1,'mediano','medio',TRUE),(2,'grande','alto',TRUE),(6,'grande','alto',FALSE) ON CONFLICT DO NOTHING;
INSERT INTO gato (id_animal, resultado_fiv, resultado_felv) VALUES (3,FALSE,FALSE),(4,NULL,NULL) ON CONFLICT DO NOTHING;
INSERT INTO otro (id_animal, descripcion_especie, cuidados_especiales) VALUES (5,'Conejo','Heno y jaula amplia') ON CONFLICT DO NOTHING;
INSERT INTO estancia (id_animal, id_hogar, id_persona, fecha_inicio) VALUES (2,1,1,'2026-10-22') ON CONFLICT DO NOTHING;
INSERT INTO solicitud_adopcion (id_animal, id_persona, fecha_solicitud, estado, observaciones) VALUES
 (1,3,'2026-11-10','pendiente','Tiene patio y experiencia con perros'),(3,4,'2026-11-12','pendiente',NULL),
 (6,3,'2026-11-14','pendiente','Busca un perro activo') ON CONFLICT DO NOTHING;
