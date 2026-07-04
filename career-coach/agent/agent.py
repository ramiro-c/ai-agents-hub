"""Career coach agent: planes de carrera a N meses con Gemini + tools.

Usa Gemini 2.5 Flash con function calling nativo (tools reales) y thinking
nativo (para exponer el proceso de razonamiento). En local corre contra Vertex
via ADC; deployado en Agent Engine usa Vertex nativo sin secretos.
"""

from datetime import date, timedelta

from google.adk.agents import LlmAgent
from google.adk.planners import BuiltInPlanner
from google.genai import types


def build_career_timeline(total_months: int, phases: list[str]) -> dict:
    """Reparte un total de meses en fases consecutivas de duracion pareja.

    Args:
        total_months: Cantidad total de meses del plan.
        phases: Nombres de las fases, en orden.

    Returns:
        dict con la lista de fases y su rango de meses (ej. "1-3").
    """
    n = max(len(phases), 1)
    base, extra = divmod(total_months, n)
    timeline = []
    cursor = 1
    for i, phase in enumerate(phases):
        length = base + (1 if i < extra else 0)
        end = cursor + max(length, 1) - 1
        timeline.append({"phase": phase, "months": f"{cursor}-{end}"})
        cursor = end + 1
    return {"total_months": total_months, "timeline": timeline}


def estimate_learning_effort(total_hours: float, hours_per_week: float) -> dict:
    """Estima semanas/meses y fecha de fin dado el tiempo semanal disponible.

    Args:
        total_hours: Horas totales estimadas para alcanzar el objetivo.
        hours_per_week: Horas por semana que la persona puede dedicar.

    Returns:
        dict con weeks, months y estimated_finish (ISO date).
    """
    weeks = total_hours / hours_per_week if hours_per_week else 0.0
    finish = date.today() + timedelta(weeks=weeks)
    return {
        "weeks": round(weeks, 1),
        "months": round(weeks / 4.345, 1),
        "estimated_finish": finish.isoformat(),
    }


def skill_gap_analysis(current_skills: list[str], required_skills: list[str]) -> dict:
    """Compara skills actuales vs requeridas para un rol objetivo.

    Args:
        current_skills: Skills que la persona ya tiene.
        required_skills: Skills requeridas por el rol objetivo.

    Returns:
        dict con have, missing y coverage_pct.
    """
    current = {s.lower().strip() for s in current_skills}
    required = [s.strip() for s in required_skills]
    have = [s for s in required if s.lower() in current]
    missing = [s for s in required if s.lower() not in current]
    coverage = round(100 * len(have) / len(required), 1) if required else 0.0
    return {"have": have, "missing": missing, "coverage_pct": coverage}


root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="career_coach",
    description="Arma planes de carrera a N meses usando planificacion y tools",
    instruction="""Sos un coach de carrera experto. Tu trabajo es armar planes de
carrera accionables a N meses.

Metodologia:
1. Entende el objetivo: rol/meta, horizonte en meses y tiempo semanal disponible.
2. Detecta gaps: primero inferi con tu propio conocimiento las
   required_skills del rol objetivo (segun el rol, seniority y dominio). No le
   pidas al usuario que te las liste.
   Luego usa skill_gap_analysis(current_skills, required_skills) para comparar
   las skills actuales de la persona con las que requiere el rol objetivo.
3. Estructura el plan: usa build_career_timeline(total_months, phases) para
   repartir el horizonte en fases con rangos de meses concretos.
4. Estima esfuerzo: usa estimate_learning_effort(total_hours, hours_per_week) para
   traducir la carga de estudio en semanas/meses y una fecha estimada de fin.

Reglas:
- Siempre que tengas los datos, USA las tools en vez de inventar numeros.
- Si falta informacion clave (rol objetivo, meses, horas semanales, skills
  actuales), pedila antes de armar el plan.
- Si el rol es ambiguo, proponé una interpretacion razonable y aclara que es una
  inferencia del rol objetivo.
- Entrega recomendaciones claras, priorizadas y con el razonamiento detras.
Responde en el idioma del usuario.""",
    planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=True,
            thinking_budget=2048,
        ),
    ),
    tools=[
        build_career_timeline,
        estimate_learning_effort,
        skill_gap_analysis,
    ],
)
