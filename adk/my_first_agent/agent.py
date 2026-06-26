from google.adk.agents import LlmAgent

from model_utils import resolve_model

root_agent = LlmAgent(
    model=resolve_model(),
    name="math_tutor_agent",
    # This description is primarily used by other
    # LLM agents to determine if they should route
    # a task to this agent. Make it specific enough
    # to differentiate it from peers.
    description=(
        "Helps students learn algebra by guiding them through problem solving steps."
    ),
    # The instruction parameter is arguably the most
    # critical for shaping an LlmAgent’s behavior. It tells the
    # agent its core task or goal, its personality or persona,
    # constraints on its behavior, and how and when to use
    # its tools.
    instruction="You are a patient math tutor. Help students with algebra problems.",
)
