# Travel Agent Database

PostgreSQL 16 (Alpine) with hardcoded flights and hotels seed data. Accessed by the travel agent via MCP postgres server.

## Quick Start

```bash
# From repo root
docker compose -f adk/travel_agent/db/docker-compose.yml up -d
```

The database starts on `localhost:5432`. On first run, all `.sql` files in the init directory execute in alphabetical order.

### Re-seed from scratch

```bash
docker compose -f adk/travel_agent/db/docker-compose.yml down -v
docker compose -f adk/travel_agent/db/docker-compose.yml up -d
```

The `-v` flag drops the named volume, forcing init scripts to re-run.

### Manual connection

```bash
docker exec -it travel_agent_db psql -U travel_agent -d travel_agent_db
```

## Seed Files

Files are named with numeric prefixes for deterministic execution order:

| File | What it does |
|------|-------------|
| `01-schema.sql` | Creates tables + indexes |
| `02-flights-seed.sql` | Seeds 26 flights |
| `03-hotels-seed.sql` | Seeds 24 hotels |

## Schema

### `flights`

| Column | Type | Notes |
|--------|------|-------|
| `id` | `SERIAL PRIMARY KEY` | Auto-increment |
| `flight_number` | `TEXT NOT NULL` | e.g. `AF123` |
| `airline` | `TEXT NOT NULL` | e.g. `Air France` |
| `origin` | `TEXT NOT NULL DEFAULT 'EZE'` | Departure airport |
| `destination` | `TEXT NOT NULL` | e.g. `Paris`, `Tokyo` |
| `departure_date` | `DATE NOT NULL` | `YYYY-MM-DD` |
| `price_usd` | `NUMERIC(10,2) NOT NULL` | Round-trip price |
| `duration_hours` | `NUMERIC(4,1) NOT NULL` | Flight duration |

Index: `idx_flights_dest_date` on `(destination, departure_date)`.

### `hotels`

| Column | Type | Notes |
|--------|------|-------|
| `id` | `SERIAL PRIMARY KEY` | Auto-increment |
| `name` | `TEXT NOT NULL` | e.g. `Hotel Eiffel` |
| `city` | `TEXT NOT NULL` | e.g. `Paris`, `Tokyo` |
| `price_per_night_usd` | `NUMERIC(10,2) NOT NULL` | Per night |
| `rating` | `NUMERIC(2,1) NOT NULL` | 1.0–5.0 |
| `amenities` | `TEXT[] NOT NULL DEFAULT '{}'` | e.g. `{WiFi,Pool,Spa}` |

Index: `idx_hotels_city` on `(city)`.

## Seed Data Reference

### Flights (26 rows, 9 destinations)

All flights depart from **EZE** (Buenos Aires).

| Destination | Flights | Airlines | Price range | Duration |
|-------------|---------|----------|-------------|----------|
| Paris | 3 | Air France, British Airways | $450–520 | 7.5–8h |
| Tokyo | 3 | Japan Airlines, ANA | $790–850 | 12.5–13.5h |
| New York | 3 | American, Delta, United | $650–720 | 10–11h |
| London | 3 | British Airways, Virgin Atlantic, Iberia | $790–850 | 13–14h |
| Madrid | 3 | Iberia, Aerolíneas Argentinas, Air Europa | $650–720 | 12–12.5h |
| Miami | 3 | American, Aerolíneas Argentinas, LATAM | $490–550 | 9–9.5h |
| Barcelona | 3 | Iberia, Air Europa, Vueling | $690–780 | 13–13.5h |
| Rome | 3 | ITA Airways, Aerolíneas Argentinas | $730–810 | 13–14h |
| Sydney | 2 | Qantas, LATAM | $1380–1450 | 15.5–16h |

### Hotels (24 rows, 8 cities)

| City | Hotels | Price/night | Rating range |
|------|--------|-------------|--------------|
| Paris | 3 | $120–185 | 4.2–4.6 |
| Tokyo | 3 | $140–210 | 4.3–4.8 |
| New York | 3 | $160–280 | 4.3–4.6 |
| London | 3 | $130–250 | 4.1–4.7 |
| Madrid | 3 | $110–175 | 4.2–4.5 |
| Miami | 3 | $155–230 | 4.1–4.5 |
| Barcelona | 3 | $130–160 | 4.2–4.4 |
| Rome | 3 | $140–195 | 4.3–4.6 |

## Adding More Data

1. Create a new `.sql` file with a higher numeric prefix (e.g. `04-cancun-seed.sql`):

```sql
INSERT INTO flights (flight_number, airline, origin, destination, departure_date, price_usd, duration_hours)
VALUES
    ('AM450', 'Aeroméxico', 'EZE', 'Cancún', '2026-11-01', 620.00, 10.0),
    ('AR1350', 'Aerolíneas Argentinas', 'EZE', 'Cancún', '2026-11-01', 580.00, 10.5);

INSERT INTO hotels (name, city, price_per_night_usd, rating, amenities)
VALUES
    ('Cancún Beach Resort', 'Cancún', 175.00, 4.4, ARRAY['WiFi', 'Pool', 'Beach', 'Restaurant']);
```

2. Mount it in `docker-compose.yml`:

```yaml
- ./04-cancun-seed.sql:/docker-entrypoint-initdb.d/04-cancun-seed.sql
```

3. Re-seed: `docker compose down -v && docker compose up -d`

## Environment

Connection variables live in `adk/travel_agent/.env`:

```env
POSTGRES_USER=travel_agent
POSTGRES_PASSWORD=travel_agent_secret
POSTGRES_DB=travel_agent_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
DATABASE_URL=postgresql://travel_agent:travel_agent_secret@localhost:5432/travel_agent_db
```

## Architecture

```
User → LlmAgent (travel_agent)
         ├── McpToolset → npx → MCP postgres server → PostgreSQL (Docker)
         │      query(SQL)                     flights (26 rows)
         │                                     hotels  (24 rows)
         └── calculate_trip_budget (local function tool)
```
