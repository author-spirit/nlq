-- Small fictional UK automobile garage (Postgres-flavored) for NLQ import tests.

CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY,
  full_name VARCHAR(120) NOT NULL,
  phone VARCHAR(40),
  city VARCHAR(80),
  preferred_mechanic_id INTEGER
);

CREATE TABLE mechanics (
  mechanic_id INTEGER PRIMARY KEY,
  full_name VARCHAR(120) NOT NULL,
  specialty VARCHAR(80)
);

CREATE TABLE services (
  service_id INTEGER PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  base_price DOUBLE PRECISION NOT NULL
);

CREATE TABLE parts (
  part_id INTEGER PRIMARY KEY,
  sku VARCHAR(40) NOT NULL,
  name VARCHAR(120) NOT NULL,
  unit_cost DOUBLE PRECISION NOT NULL
);

CREATE TABLE vehicles (
  vehicle_id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
  make VARCHAR(60) NOT NULL,
  model VARCHAR(60) NOT NULL,
  year INTEGER NOT NULL,
  plate VARCHAR(20) NOT NULL
);

CREATE TABLE work_orders (
  work_order_id INTEGER PRIMARY KEY,
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
  mechanic_id INTEGER NOT NULL REFERENCES mechanics(mechanic_id),
  opened_at TIMESTAMP NOT NULL,
  status VARCHAR(40) NOT NULL,
  notes VARCHAR(255)
);

CREATE TABLE work_order_items (
  item_id INTEGER PRIMARY KEY,
  work_order_id INTEGER NOT NULL REFERENCES work_orders(work_order_id),
  service_id INTEGER NOT NULL REFERENCES services(service_id),
  quantity INTEGER NOT NULL,
  line_total DOUBLE PRECISION NOT NULL
);

CREATE TABLE work_order_parts (
  id INTEGER PRIMARY KEY,
  work_order_id INTEGER NOT NULL REFERENCES work_orders(work_order_id),
  part_id INTEGER NOT NULL REFERENCES parts(part_id),
  quantity INTEGER NOT NULL
);

INSERT INTO customers (customer_id, full_name, phone, city, preferred_mechanic_id) VALUES
  (1, 'Amelia Hartley', '07700 900101', 'Manchester', 1),
  (2, 'Owen Bridger', '07700 900102', 'Leeds', 2),
  (3, 'Priya Iyer', '07700 900103', 'Bristol', 1),
  (4, 'Callum Rees', '07700 900104', 'Cardiff', 99),
  (5, 'Nina Farley', '07700 900105', 'Edinburgh', 3);

INSERT INTO mechanics (mechanic_id, full_name, specialty) VALUES
  (1, 'James Whitaker', 'engine'),
  (2, 'Sophie Lang', 'brakes'),
  (3, 'Marcus Doyle', 'electrical');

INSERT INTO services (service_id, name, base_price) VALUES
  (1, 'Oil change', 45.0),
  (2, 'Brake pad replacement', 180.0),
  (3, 'Battery check', 35.0),
  (4, 'Wheel alignment', 70.0);

INSERT INTO parts (part_id, sku, name, unit_cost) VALUES
  (1, 'OIL-5W30', 'Engine oil 5W-30', 28.0),
  (2, 'PAD-FR', 'Front brake pads', 65.0),
  (3, 'BAT-12V', '12V battery', 120.0),
  (4, 'FIL-AIR', 'Air filter', 18.0);

INSERT INTO vehicles (vehicle_id, customer_id, make, model, year, plate) VALUES
  (1, 1, 'Ford', 'Fiesta', 2019, 'AB19 CDE'),
  (2, 1, 'Vauxhall', 'Corsa', 2021, 'FG21 HIJ'),
  (3, 2, 'Volkswagen', 'Golf', 2018, 'KL18 MNO'),
  (4, 3, 'Toyota', 'Yaris', 2020, 'PQ20 RST'),
  (5, 4, 'BMW', '118i', 2022, 'UV22 WXY'),
  (6, 5, 'Mini', 'Cooper', 2023, 'ZA23 BCD');

INSERT INTO work_orders (work_order_id, vehicle_id, mechanic_id, opened_at, status, notes) VALUES
  (1, 1, 1, '2025-01-10 09:00:00', 'closed', 'Routine service'),
  (2, 2, 2, '2025-02-01 11:30:00', 'closed', 'Front brakes squeal'),
  (3, 3, 3, '2025-02-15 14:00:00', 'open', 'Battery drain'),
  (4, 4, 1, '2025-03-03 10:15:00', 'closed', 'Oil + filter'),
  (5, 5, 2, '2025-03-20 16:45:00', 'in_progress', 'Alignment after tyre change'),
  (6, 6, 3, '2025-04-02 08:50:00', 'open', 'Check electrics');

INSERT INTO work_order_items (item_id, work_order_id, service_id, quantity, line_total) VALUES
  (1, 1, 1, 1, 45.0),
  (2, 2, 2, 1, 180.0),
  (3, 3, 3, 1, 35.0),
  (4, 4, 1, 1, 45.0),
  (5, 5, 4, 1, 70.0),
  (6, 6, 3, 1, 35.0);

INSERT INTO work_order_parts (id, work_order_id, part_id, quantity) VALUES
  (1, 1, 1, 1),
  (2, 1, 4, 1),
  (3, 2, 2, 1),
  (4, 3, 3, 1),
  (5, 4, 1, 1),
  (6, 4, 4, 1);
