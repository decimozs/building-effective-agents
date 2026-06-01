# =============================================================================
# evaluator-optimizer/workflow.py
#
# Evaluator-Optimizer: Iterative Joke Generation
#
# Generates jokes on a given topic, evaluates them for funniness, and
# iteratively refines based on feedback until the evaluator accepts the
# result. The loop is bounded implicitly by the model's willingness to
# improve on each pass.
#
# Pattern: Evaluator-Optimizer
#   - Generator creates or refines a joke using prior feedback
#   - Evaluator judges the joke and returns structured feedback
#   - Loop continues until the evaluator signals acceptance
# =============================================================================

from typing import Literal, TypedDict
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from langfuse import propagate_attributes

load_dotenv()


class Feedback(BaseModel):
    """Structured output from the evaluator.

    Attributes:
        status: Whether the joke passed the funniness check.
        feedback: Free-text critique to guide the next generation.
    """
    status: Literal["funny", "not_funny"] = Field(description="Feedback status")
    feedback: str = Field(description="Feedback for the joke")


class State(TypedDict):
    """Graph state for the evaluator-optimizer workflow.

    Carries the topic, the current joke attempt, evaluator feedback,
    acceptance status, and iteration counter.

    Attributes:
        topic: The joke subject provided by the user.
        joke: Current joke text being evaluated.
        feedback: Feedback from the evaluator to guide improvements.
        status: Acceptance status: funny or not_funny.
        iter: Number of generation-evaluation cycles completed.
    """
    topic: str
    joke: str
    feedback: str
    status: str
    iter: int


# ---------------------------------------------------------------------------
# LLM Setup
# ---------------------------------------------------------------------------

llm = ChatOllama(model="lfm2.5-thinking", temperature=0)
evaluator_llm = llm.with_structured_output(Feedback)


def generator(state: State) -> dict:
    """Generate a joke, then refine it using prior feedback.

    The generator is the optimizer side of the loop. It stays focused on the
    current attempt while the evaluator provides the improvement signal.

    Args:
        state: Current graph state with topic and optional prior feedback.

    Returns:
        Dict with the joke string and incremented iteration counter.
    """
    current_iter = state.get("iter", 0) + 1
    if state.get("feedback"):
        msg = llm.invoke(
            f"Write a joke about {state.get('topic')} but make sure you polish that based on the feedback: {state.get('feedback')}"
        )
    else:
        msg = llm.invoke(f"Generate a joke based on this topic: {state.get('topic')}")
    return {"joke": msg.content, "iter": current_iter}


def evaluator(state: State) -> dict:
    """Judge the joke and produce feedback for the next iteration.

    The evaluator acts like a critic. The loop improves quality by repeatedly
    feeding critique back into generation.

    Args:
        state: Current graph state containing the joke text.

    Returns:
        Dict with status (funny/not_funny) and feedback string.
    """
    evaluation = evaluator_llm.invoke(
        [
            SystemMessage(content="Evaluate this joke if it is funny or not funny"),
            HumanMessage(content=f"The joke is {state.get('joke')}"),
        ]
    )
    return {
        "status": evaluation.status,
        "feedback": evaluation.feedback,
    }


def route(state: State):
    """Decide whether the joke is good enough to stop.

    Keeps the loop explicit: generate, evaluate, then either accept the
    result or send feedback back into another generation pass.

    Args:
        state: Current graph state containing the evaluator status.

    Returns:
        "accepted" if funny, "rejected + feedback" to continue the loop.
    """
    if state.get("status") == "funny":
        return "accepted"
    elif state.get("status") == "not_funny":
        return "rejected + feedback"


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

workflow = StateGraph(State)

workflow.add_node("generator", generator)
workflow.add_node("evaluator", evaluator)

workflow.add_edge(START, "generator")
workflow.add_edge("generator", "evaluator")
workflow.add_conditional_edges(
    "evaluator", route, {"accepted": END, "rejected + feedback": "generator"}
)

graph = workflow.compile()

langfuse_handler = CallbackHandler()

# ---------------------------------------------------------------------------
# Workflow Execution
# ---------------------------------------------------------------------------

with propagate_attributes(
    metadata={"type": "evaluator-optimizer"},
    tags=["workflow"],
):
    for step in graph.stream(
        {"topic": "Kalabaw", "joke": "", "feedback": "", "status": "", "iter": 0},
        config={"callbacks": [langfuse_handler]},
    ):
        for node_name, node_output in step.items():
            print(f"\n{'=' * 40}")
            print(f"Node: {node_name}")
            print(f"{'=' * 40}")
            for key, value in node_output.items():
                print(f"\n[{key}]:\n{value}")
