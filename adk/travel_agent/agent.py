"""
Travel Agent with MCP Postgres Tools

Demonstrates McpToolset integration with a PostgreSQL database
for flight and hotel search, plus a local budget calculator.

Reference: https://google.github.io/adk-docs/tools-custom/mcp-tools/
"""

import os

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from model_utils import resolve_model

DATABASE_URL = os.getenv("DATABASE_URL", "")


# Tool: Calculate trip budget
def calculate_trip_budget(
    flight_price: float, hotel_price: float, num_nights: int
) -> dict:
    """Calculates total trip budget including flights and accommodation.

    Use this after finding flight and hotel prices to give the customer a total
    estimate.

    Args:
        flight_price (float): Round-trip flight cost in USD.
        hotel_price (float): Hotel cost per night in USD.
        num_nights (int): Number of nights staying.

    Returns:
        dict: Budget breakdown.
            Always returns: {'status': 'success', 'total_usd': X,
                             'breakdown': {...}}
    """
    hotel_total = hotel_price * num_nights
    total = flight_price + hotel_total

    return {
        "status": "success",
        "total_usd": round(total, 2),
        "breakdown": {
            "flight_cost": flight_price,
            "hotel_cost_per_night": hotel_price,
            "num_nights": num_nights,
            "hotel_total": round(hotel_total, 2),
        },
    }


# Create travel agent with MCP postgres tools and budget calculator
root_agent = LlmAgent(
    model=resolve_model(provider="openrouter"),
    name="travel_agent",
    description="Helps users plan trips by finding flights and hotels.",
    instruction="""You are a helpful travel agent assistant.

DATABASE SCHEMA:
- flights: id, flight_number, airline, origin (default 'EZE'), destination,
  departure_date, price_usd, duration_hours
- hotels: id, name, city, price_per_night_usd, rating, amenities (text[])

Example queries:
- Flights to Paris: SELECT * FROM flights WHERE destination ILIKE '%paris%'
- Hotels in Tokyo: SELECT * FROM hotels WHERE city ILIKE 'tokyo'
- Cheap flights: SELECT * FROM flights WHERE price_usd < 600

When helping users:
1. Use the query tool to search flights and hotels via SQL
2. Use calculate_trip_budget(flight_price, hotel_price, num_nights) for totals
3. Always present options clearly with prices

Be friendly and help users plan their perfect trip!""",
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=[
                        "-y",
                        "@modelcontextprotocol/server-postgres",
                        DATABASE_URL,
                    ],
                ),
            ),
            tool_filter=["query"],
        ),
        calculate_trip_budget,
    ],
)
