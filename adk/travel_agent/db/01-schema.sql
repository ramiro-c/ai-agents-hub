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
