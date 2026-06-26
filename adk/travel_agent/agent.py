"""
Travel Agent with MCP Postgres Tools

Demonstrates McpToolset integration with a PostgreSQL database
for flight and hotel search, plus a local budget calculator.

Reference: https://google.github.io/adk-docs/tools-custom/mcp-tools/
"""

import logging
import os
import re
import sys
import time

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from model_utils import resolve_model

logger = logging.getLogger("travel_agent")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s")
    )
    logger.addHandler(handler)

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _redact_url(url: str) -> str:
    """Replace :password@ with :***@ in connection URLs."""
    return re.sub(r":([^:@]+)@", r":***@", url)


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


def before_tool_callback(tool, args, tool_context):
    try:
        ctx_state = (
            getattr(tool_context, "state", {}) if tool_context is not None else {}
        )
        ctx_state["_t0"] = time.perf_counter()
        sess = (
            getattr(tool_context, "session_id", "unknown")
            if tool_context is not None
            else "unknown"
        )
        safe_args = {
            k: _redact_url(str(v)) if isinstance(v, str) else v for k, v in args.items()
        }
        logger.info("tool=%s args=%s session_id=%s", tool.name, safe_args, sess)
    except Exception:
        logger.exception("before_tool_callback failed")
    return None


def after_tool_callback(tool, args, tool_context, result):
    try:
        ctx_state = (
            getattr(tool_context, "state", {}) if tool_context is not None else {}
        )
        t0 = ctx_state.get("_t0", time.perf_counter())
        duration_ms = (time.perf_counter() - t0) * 1000
        if isinstance(result, dict) and "rows" in result:
            summary = f"rows={len(result['rows'])}"
        else:
            summary = str(result)[:200]
        logger.info(
            "tool=%s duration_ms=%.1f result=%s",
            tool.name,
            duration_ms,
            summary,
        )
    except Exception:
        logger.exception("after_tool_callback failed")
    return None


# Create travel agent with MCP postgres tools and budget calculator
try:
    mcp_toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-postgres", DATABASE_URL],
            ),
        ),
        tool_filter=["query"],
    )
    logger.info("MCP server started with URL=%s", _redact_url(DATABASE_URL))
except Exception:
    logger.exception("MCP server startup failed with URL=%s", _redact_url(DATABASE_URL))
    mcp_toolset = None

tools = [calculate_trip_budget]
if mcp_toolset is not None:
    tools.insert(0, mcp_toolset)

root_agent = LlmAgent(
    model=resolve_model(provider="openrouter"),
    name="travel_agent",
    description="Helps users plan trips by finding flights and hotels.",
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    instruction="""You are a helpful travel agent assistant.

DATABASE SCHEMA:
- flights: id, flight_number, airline, origin (default 'EZE'), destination,
  departure_date, price_usd, duration_hours
- hotels: id, name, city, price_per_night_usd, rating, amenities (text[])

Available destinations for flights (9): Paris, Tokyo, New York, London, Madrid,
Miami, Barcelona, Rome, Sydney.

Available cities for hotels (8): Paris, Tokyo, New York, London, Madrid, Miami,
Barcelona, Rome.

Example queries:
- Flights to Paris: SELECT * FROM flights WHERE destination ILIKE '%paris%'
- Hotels in Tokyo: SELECT * FROM hotels WHERE city ILIKE 'tokyo'
- Cheap flights under $600: SELECT * FROM flights WHERE price_usd < 600
- Hotels with pool: SELECT * FROM hotels WHERE 'Pool' = ANY(amenities)
- Top hotels in Rome: SELECT * FROM hotels WHERE city ILIKE 'rome' ORDER BY rating DESC

When helping users:
1. Use the query tool to search flights and hotels via SQL
2. Use calculate_trip_budget(flight_price, hotel_price, num_nights) for totals
3. Always present options clearly with prices
4. If a user asks for a destination not in the available list, be honest about it
   and suggest similar destinations that are available

If the database is unavailable, tell the user clearly and suggest they try again later.

Be friendly and help users plan their perfect trip!""",
    tools=tools,
)
