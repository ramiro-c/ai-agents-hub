-- Flights table
CREATE TABLE IF NOT EXISTS flights (
    id SERIAL PRIMARY KEY,
    flight_number TEXT NOT NULL,
    airline TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'EZE',
    destination TEXT NOT NULL,
    departure_date DATE NOT NULL,
    price_usd NUMERIC(10,2) NOT NULL,
    duration_hours NUMERIC(4,1) NOT NULL
);

-- Hotels table
CREATE TABLE IF NOT EXISTS hotels (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    price_per_night_usd NUMERIC(10,2) NOT NULL,
    rating NUMERIC(2,1) NOT NULL,
    amenities TEXT[] NOT NULL DEFAULT '{}'
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_flights_dest_date ON flights (destination, departure_date);
CREATE INDEX IF NOT EXISTS idx_hotels_city ON hotels (city);

-- Seed data: flights (matching previously hardcoded search_flights results)
INSERT INTO flights (flight_number, airline, origin, destination, departure_date, price_usd, duration_hours)
VALUES
    ('AF123', 'Air France', 'EZE', 'Paris', '2026-07-15', 450.00, 8.0),
    ('BA456', 'British Airways', 'EZE', 'Paris', '2026-07-15', 480.00, 7.5),
    ('JL789', 'Japan Airlines', 'EZE', 'Tokyo', '2026-08-01', 850.00, 13.0),
    ('ANA101', 'All Nippon Airways', 'EZE', 'Tokyo', '2026-08-01', 820.00, 12.5);

-- Seed data: hotels (matching previously hardcoded search_hotels results)
INSERT INTO hotels (name, city, price_per_night_usd, rating, amenities)
VALUES
    ('Hotel Eiffel', 'Paris', 150.00, 4.5, ARRAY['WiFi', 'Gym', 'Restaurant', 'Bar']),
    ('Louvre Inn', 'Paris', 120.00, 4.2, ARRAY['WiFi', 'Breakfast']),
    ('Shibuya Grand', 'Tokyo', 180.00, 4.7, ARRAY['WiFi', 'Pool', 'Spa', 'Concierge']),
    ('Tokyo Bay Hotel', 'Tokyo', 140.00, 4.3, ARRAY['WiFi', 'Restaurant', 'Parking']);
