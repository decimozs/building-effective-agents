# =============================================================================
# prompt-chaining/workflow.py
#
# Prompt Chaining: Document Outline Generation
#
# Generates a document outline in sequential steps: first draft, quality check,
# improvement pass, then final polish. Each step feeds its output into the next,
# and a guardrail gate prevents low-quality drafts from advancing.
#
# Pattern: Prompt Chaining
#   - Sequential steps each perform a narrow transformation
#   - Guardrail step validates quality before continuing
#   - Failed drafts terminate early instead of wasting further LLM calls
# =============================================================================

from typing import TypedDict
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langfuse.langchain import CallbackHandler
from langfuse import propagate_attributes
from dotenv import load_dotenv

load_dotenv()


class State(TypedDict):
    """Graph state for the prompt-chaining workflow.

    Carries the topic and the outline through each sequential transformation
    step: generate, check, improve, and polish.

    Attributes:
        topic: The subject for the document outline.
        document_outline: First draft of the outline.
        improve_document_outline: Improved version after review.
        document_status: Validation result: passed or fail.
        final_document_outline: Polished final version of the outline.
    """
    topic: str
    document_outline: str
    improve_document_outline: str
    document_status: str
    final_document_outline: str


# ---------------------------------------------------------------------------
# LLM Setup
# ---------------------------------------------------------------------------

llm = ChatOllama(model="lfm2.5-thinking", temperature=0)


def generate_doucument_outline(state: State) -> dict:
    """Create the first draft of the outline from the topic.

    The first node in the chain establishes a rough draft that later nodes
    refine. Splitting one hard task into small steps is the core idea of
    prompt chaining.

    Args:
        state: Current graph state containing the topic string.

    Returns:
        Dict with the document_outline string.
    """
    msg = llm.invoke(f"Write document outline about {state.get('topic')}")
    return {"document_outline": msg.content}


def improve_doucument_outline(state: State) -> dict:
    """Improve the draft outline before the final pass.

    Each step in a chained workflow focuses on a narrow transformation
    instead of forcing one prompt to generate the final answer in a single
    shot.

    Args:
        state: Current graph state containing the initial document_outline.

    Returns:
        Dict with the improve_document_outline string.
    """
    msg = llm.invoke(f"Improve this document outline: {state.get('document_outline')}")
    return {"improve_document_outline": msg.content}


def final_document_outline(state: State) -> dict:
    """Polish the improved outline into the final version.

    The last step keeps the output clean and consistent after earlier nodes
    have already done the heavy lifting.

    Args:
        state: Current graph state containing the improve_document_outline.

    Returns:
        Dict with the final_document_outline string.
    """
    msg = llm.invoke(
        f"Polish this improve document outline: {state.get('improve_document_outline')}"
    )
    return {"final_document_outline": msg.content}


def check_document_outline(state: State) -> dict:
    """Validate the outline before allowing the workflow to continue.

    A guardrail step: check quality early, then branch only if the draft
    meets the intended criterion (science topic).

    Args:
        state: Current graph state containing the document_outline.

    Returns:
        Dict with document_status: "passed" or "fail".
    """
    msg = llm.invoke(
        f"Check this document outline: {state.get('document_outline')} "
        f"if the topic is for science, if it is return passed if not return fail."
        f"Reply with ONLY one word: 'passed' if it is science, 'fail' if it is not. "
        f"Do not explain. Do not add anything else. Just one word."
    )
    return {"document_status": msg.content}


def route_document(state: State) -> str:
    """Route based on the validation result.

    Keeps the workflow explicit: generate, verify, then continue only when
    the draft satisfies the rule.

    Args:
        state: Current graph state containing the document_status.

    Returns:
        "passed" to continue to improvement, "fail" to terminate.
    """
    document_status = state.get("document_status", "").lower()
    if "passed" in document_status:
        return "passed"
    return "fail"


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

workflow = StateGraph(State)

workflow.add_node("generate_doucument_outline", generate_doucument_outline)
workflow.add_node("improve_document_outline", improve_doucument_outline)
workflow.add_node("final_document_outline", final_document_outline)
workflow.add_node("check_document_outline", check_document_outline)

workflow.add_edge(START, "generate_doucument_outline")
workflow.add_edge("generate_doucument_outline", "check_document_outline")
workflow.add_conditional_edges(
    "check_document_outline",
    route_document,
    {"passed": "improve_document_outline", "fail": END},
)
workflow.add_edge("improve_document_outline", "final_document_outline")
workflow.add_edge("final_document_outline", END)

graph = workflow.compile()

langfuse_handler = CallbackHandler()

# ---------------------------------------------------------------------------
# Workflow Execution
# ---------------------------------------------------------------------------

with propagate_attributes(
    metadata={"type": "prompt-chaining"},
    tags=["workflow"],
):
    for step in graph.stream(
        {
            "topic": "Lebron James",
            "document_status": "",
            "document_outline": "",
            "final_document_outline": "",
            "improve_document_outline": "",
        },
        config={"callbacks": [langfuse_handler]},
    ):
        for node_name, node_output in step.items():
            print(f"\n{'=' * 40}")
            print(f"Node: {node_name}")
            print(f"{'=' * 40}")
            for key, value in node_output.items():
                print(f"\n[{key}]:\n{value}")
