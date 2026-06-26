-- Seed data: flights (origin: EZE Buenos Aires)
INSERT INTO flights (flight_number, airline, origin, destination, departure_date, price_usd, duration_hours)
VALUES
    -- Paris
    ('AF123', 'Air France', 'EZE', 'Paris', '2026-07-15', 450.00, 8.0),
    ('BA456', 'British Airways', 'EZE', 'Paris', '2026-07-15', 480.00, 7.5),
    ('AF229', 'Air France', 'EZE', 'Paris', '2026-09-10', 520.00, 8.0),
    -- Tokyo
    ('JL789', 'Japan Airlines', 'EZE', 'Tokyo', '2026-08-01', 850.00, 13.0),
    ('ANA101', 'All Nippon Airways', 'EZE', 'Tokyo', '2026-08-01', 820.00, 12.5),
    ('JL880', 'Japan Airlines', 'EZE', 'Tokyo', '2026-10-05', 790.00, 13.5),
    -- New York
    ('AA954', 'American Airlines', 'EZE', 'New York', '2026-07-20', 680.00, 10.5),
    ('DL302', 'Delta Airlines', 'EZE', 'New York', '2026-07-20', 720.00, 10.0),
    ('UA818', 'United Airlines', 'EZE', 'New York', '2026-08-15', 650.00, 11.0),
    -- London
    ('BA244', 'British Airways', 'EZE', 'London', '2026-07-25', 850.00, 13.5),
    ('VS442', 'Virgin Atlantic', 'EZE', 'London', '2026-07-25', 790.00, 13.0),
    ('IB770', 'Iberia', 'EZE', 'London', '2026-09-01', 820.00, 14.0),
    -- Madrid
    ('IB101', 'Iberia', 'EZE', 'Madrid', '2026-08-05', 720.00, 12.0),
    ('AR1132', 'Aerolíneas Argentinas', 'EZE', 'Madrid', '2026-08-05', 680.00, 12.5),
    ('UX042', 'Air Europa', 'EZE', 'Madrid', '2026-09-15', 650.00, 12.0),
    -- Miami
    ('AA908', 'American Airlines', 'EZE', 'Miami', '2026-07-30', 550.00, 9.0),
    ('AR1302', 'Aerolíneas Argentinas', 'EZE', 'Miami', '2026-07-30', 520.00, 9.5),
    ('LA530', 'LATAM Airlines', 'EZE', 'Miami', '2026-08-10', 490.00, 9.0),
    -- Barcelona
    ('IB685', 'Iberia', 'EZE', 'Barcelona', '2026-08-20', 780.00, 13.0),
    ('UX190', 'Air Europa', 'EZE', 'Barcelona', '2026-09-05', 710.00, 13.5),
    ('VY978', 'Vueling', 'EZE', 'Barcelona', '2026-09-25', 690.00, 13.0),
    -- Rome
    ('AZ680', 'ITA Airways', 'EZE', 'Rome', '2026-08-10', 810.00, 13.5),
    ('AR1140', 'Aerolíneas Argentinas', 'EZE', 'Rome', '2026-08-10', 760.00, 14.0),
    ('AZ682', 'ITA Airways', 'EZE', 'Rome', '2026-10-01', 730.00, 13.0),
    -- Sydney
    ('QF28', 'Qantas', 'EZE', 'Sydney', '2026-09-01', 1450.00, 15.5),
    ('LA800', 'LATAM Airlines', 'EZE', 'Sydney', '2026-09-01', 1380.00, 16.0);
