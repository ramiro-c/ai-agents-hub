"""
Math Assistant Agent
Demonstrates ADK's Code Execution built-in tool for calculations.
Reference: https://google.github.io/adk-docs/tools/built-in-tools#code-execution
"""

from google.adk.agents import LlmAgent
from google.adk.code_executors import BuiltInCodeExecutor  # Import code executor

# Create math assistant with code execution

root_agent = LlmAgent(
    model="gemini-2.5-flash",  # Must use Gemini 2.0+ for code execution
    name="math_assistant",
    description="Helps users with mathematical calculations and analysis.",
    instruction="""
 You are a math assistant that helps users with calculations and mathematical
analysis.

 Your capabilities:
 1. When users ask for calculations, use code execution for precision
 2. Show your work by explaining the calculation steps
 3. Verify results by running the code
 4. Handle complex mathematical operations (statistics, algebra, etc.)

 Always use code execution for numerical calculations to ensure accuracy.

 """,
    code_executor=BuiltInCodeExecutor(),  # Enable code execution
)
