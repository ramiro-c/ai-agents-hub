"""
Problem-solving agent with structured planning.
Uses ADK's PlanReActPlanner for non-Gemini models.
"""

import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.planners import PlanReActPlanner

root_agent = LlmAgent(
    model=LiteLlm(
        model="openrouter/owl-alpha",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        api_base=os.getenv("OPENROUTER_BASE_URL"),
    ),
    name="strategic_problem_solver",
    description="Solves complex problems using multi-step reasoning and planning",
    instruction="""You are a Strategic Problem Solver.


Your approach to complex problems:
1. **Understand** - Break down the problem into components
2. **Analyze** - Consider multiple approaches and trade-offs
3. **Plan** - Develop a step-by-step solution strategy
4. **Execute** - Provide clear, actionable recommendations

For complex problems:
- Think through implications and edge cases
- Consider short-term vs long-term consequences
- Identify potential risks and mitigation strategies
- Provide reasoning for your recommendations

Be thorough, analytical, and systematic in your approach.""",
    planner=PlanReActPlanner(),
)
