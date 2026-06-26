"""
Research Assistant Agent
Demonstrates ADK's Google Search built-in tool for real-time information.

Reference: https://google.github.io/adk-docs/tools/built-in-tools#google-search
"""

from google.adk.agents import LlmAgent
from google.adk.tools import google_search  # Import Google Search tool

from model_utils import resolve_model

# Create research assistant with Google Search
root_agent = LlmAgent(
    model=(resolve_model(provider="gemini")),  # Must use Gemini 2.0+ for google_search
    name="research_assistant",
    description="Helps users research topics using Google Search.",
    instruction="""
 You are a research assistant that helps users find accurate, up-to-date
information.
Your approach:

 1. When users ask questions requiring current information, use Google Search
 2. Base your answers on the search results
 3. Cite sources when providing information
 4. If search results are insufficient, acknowledge limitations

 Always prioritize accuracy over speculation. If you're unsure, say so.
 """,
    tools=[google_search],  # Enable Google Search grounding
)
