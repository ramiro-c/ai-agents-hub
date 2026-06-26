-- Seed data: hotels
INSERT INTO hotels (name, city, price_per_night_usd, rating, amenities)
VALUES
    -- Paris
    ('Hotel Eiffel', 'Paris', 150.00, 4.5, ARRAY['WiFi', 'Gym', 'Restaurant', 'Bar']),
    ('Louvre Inn', 'Paris', 120.00, 4.2, ARRAY['WiFi', 'Breakfast']),
    ('Le Marais Boutique', 'Paris', 185.00, 4.6, ARRAY['WiFi', 'Spa', 'Restaurant', 'Concierge']),
    -- Tokyo
    ('Shibuya Grand', 'Tokyo', 180.00, 4.7, ARRAY['WiFi', 'Pool', 'Spa', 'Concierge']),
    ('Tokyo Bay Hotel', 'Tokyo', 140.00, 4.3, ARRAY['WiFi', 'Restaurant', 'Parking']),
    ('Shinjuku Zen Hotel', 'Tokyo', 210.00, 4.8, ARRAY['WiFi', 'Onsen', 'Restaurant', 'Gym', 'Concierge']),
    -- New York
    ('Midtown Manhattan Hotel', 'New York', 220.00, 4.4, ARRAY['WiFi', 'Gym', 'Restaurant', 'Bar']),
    ('Brooklyn Boutique Inn', 'New York', 160.00, 4.3, ARRAY['WiFi', 'Breakfast', 'Rooftop']),
    ('Times Square Grand', 'New York', 280.00, 4.6, ARRAY['WiFi', 'Pool', 'Spa', 'Restaurant', 'Concierge']),
    -- London
    ('The Westminster Hotel', 'London', 200.00, 4.5, ARRAY['WiFi', 'Restaurant', 'Bar', 'Concierge']),
    ('Camden Town Lodge', 'London', 130.00, 4.1, ARRAY['WiFi', 'Breakfast']),
    ('Kensington Grand', 'London', 250.00, 4.7, ARRAY['WiFi', 'Pool', 'Spa', 'Gym', 'Restaurant']),
    -- Madrid
    ('Gran Vía Palace', 'Madrid', 140.00, 4.4, ARRAY['WiFi', 'Restaurant', 'Bar', 'Rooftop']),
    ('Sol Boutique Hotel', 'Madrid', 110.00, 4.2, ARRAY['WiFi', 'Breakfast']),
    ('Retiro Park Suites', 'Madrid', 175.00, 4.5, ARRAY['WiFi', 'Pool', 'Gym', 'Restaurant', 'Parking']),
    -- Miami
    ('South Beach Resort', 'Miami', 190.00, 4.3, ARRAY['WiFi', 'Pool', 'Beach', 'Bar', 'Restaurant']),
    ('Downtown Miami Hotel', 'Miami', 155.00, 4.1, ARRAY['WiFi', 'Gym', 'Restaurant', 'Parking']),
    ('Coral Gables Inn', 'Miami', 230.00, 4.5, ARRAY['WiFi', 'Pool', 'Spa', 'Restaurant', 'Concierge']),
    -- Barcelona
    ('Gothic Quarter Hotel', 'Barcelona', 130.00, 4.3, ARRAY['WiFi', 'Breakfast', 'Rooftop']),
    ('Barceloneta Beach Inn', 'Barcelona', 160.00, 4.4, ARRAY['WiFi', 'Pool', 'Beach', 'Restaurant']),
    ('Sagrada Familia Suites', 'Barcelona', 145.00, 4.2, ARRAY['WiFi', 'Restaurant', 'Parking']),
    -- Rome
    ('Trastevere Boutique', 'Rome', 140.00, 4.4, ARRAY['WiFi', 'Breakfast', 'Rooftop']),
    ('Colosseum View Hotel', 'Rome', 195.00, 4.6, ARRAY['WiFi', 'Restaurant', 'Bar', 'Concierge']),
    ('Piazza Navona Suites', 'Rome', 165.00, 4.3, ARRAY['WiFi', 'Gym', 'Restaurant', 'Parking']);
