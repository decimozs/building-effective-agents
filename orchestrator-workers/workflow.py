# =============================================================================
# orchestrator-workers/workflow.py
#
# Orchestrator-Workers: Report Generation
#
# An orchestrator decomposes a topic into sections, fan-out sends each section
# to an independent worker LLM call, and a synthesizer merges the results into
# a single report.
#
# Pattern: Orchestrator-Workers
#   - Orchestrator plans the work by breaking the topic into sections
#   - Workers execute each section independently (fan-out via Send)
#   - Synthesizer merges completed sections (fan-in)
# =============================================================================

import operator
from typing import Annotated, List, TypedDict
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import Send
from pydantic import BaseModel, Field
from langfuse import propagate_attributes

load_dotenv()


class Section(BaseModel):
    """Pydantic model for a single report section.

    Attributes:
        name: Title or heading for this section.
        description: Brief overview of what this section covers.
    """
    name: str = Field(description="Name for this section report")
    description: str = Field(description="Brief overview of this report")


class Sections(BaseModel):
    """Pydantic model containing a list of planned sections.

    Attributes:
        sections: Collection of Section objects for the report.
    """
    sections: List[Section] = Field(description="Sections of the report")


class State(TypedDict):
    """Graph state for the orchestrator-workers workflow.

    Carries the topic, the list of planned sections, completed worker
    outputs, and the final merged report.

    Attributes:
        topic: The report subject provided by the user.
        sections: List of Section objects produced by the orchestrator.
        completed_sections: Accumulated worker outputs (via operator.add).
        final_report: Merged result from the synthesizer node.
    """
    topic: str
    sections: list[Section]
    completed_sections: Annotated[list, operator.add]
    final_report: str


class WorkerState(TypedDict):
    """Per-worker state passed via Send to each llm_call invocation.

    Attributes:
        section: The Section object this worker should write.
        completed_sections: Output accumulator (via operator.add).
    """
    section: Section
    completed_sections: Annotated[list, operator.add]


# ---------------------------------------------------------------------------
# LLM Setup
# ---------------------------------------------------------------------------

llm = ChatOllama(model="lfm2.5-thinking", temperature=0)
planner = llm.with_structured_output(Sections)


def orchestrator(state: State) -> dict:
    """Break the topic into smaller sections before work is delegated.

    The orchestrator plans first, then hands off focused pieces to workers.
    That keeps each worker prompt narrow and predictable.

    Args:
        state: Current graph state containing the topic string.

    Returns:
        Dict with a list of Section objects under the sections key.
    """
    report_sections = planner.invoke(
        [
            SystemMessage(content="Generate a plan for the report."),
            HumanMessage(
                content=f"Here is the topic for the report '{state.get('topic')}'"
            ),
        ]
    )
    return {"sections": report_sections.sections}


def llm_call(state: WorkerState) -> dict:
    """Write one report section in isolation.

    Workers should only need the section they own. Narrow scope makes the
    system easier to scale, debug, and improve.

    Args:
        state: WorkerState containing the single Section to write.

    Returns:
        Dict with completed_sections list containing the section content.
    """
    section = llm.invoke(
        [
            SystemMessage(content="Write a report section."),
            HumanMessage(
                content=f"Here is the section name: {state.get('section').name} and description {state.get('section').description}"
            ),
        ]
    )
    return {"completed_sections": [section.content]}


def synthesizer(state: State) -> dict:
    """Merge all completed sections into the final report.

    Fan-in is the last step of the pattern. The orchestrator distributes work,
    workers produce pieces, and the synthesizer combines the outputs.

    Args:
        state: Current graph state with completed_sections populated.

    Returns:
        Dict with the final_report string containing all sections joined.
    """
    completed_sections = state.get("completed_sections")
    completed_report_sections = "\n\n---\n\n".join(completed_sections)
    return {"final_report": completed_report_sections}


def assign(state: State) -> list[Send]:
    """Create one worker task per planned section.

    This is the fan-out moment: the graph sends independent units of work to
    parallel workers instead of asking one node to write the whole report.

    Args:
        state: Current graph state containing the planned sections list.

    Returns:
        List of Send objects, one per section, each targeting the llm_call node.
    """
    return [Send("llm_call", {"section": s}) for s in state["sections"]]


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

workflow = StateGraph(State)

workflow.add_node("orchestrator", orchestrator)
workflow.add_node("llm_call", llm_call)
workflow.add_node("synthesizer", synthesizer)

workflow.add_edge(START, "orchestrator")
workflow.add_conditional_edges("orchestrator", assign, ["llm_call"])
workflow.add_edge("llm_call", "synthesizer")
workflow.add_edge("synthesizer", END)

graph = workflow.compile()

langfuse_handler = CallbackHandler()

# ---------------------------------------------------------------------------
# Workflow Execution
# ---------------------------------------------------------------------------

with propagate_attributes(
    metadata={"type": "orchestrator-workers"},
    tags=["workflow"],
):
    for step in graph.stream(
        {
            "topic": "Global Warming",
            "completed_sections": [],
            "sections": [],
            "final_report": "",
        },
        config={"callbacks": [langfuse_handler]},
    ):
        for node_name, node_output in step.items():
            print(f"\n{'=' * 40}")
            print(f"Node: {node_name}")
            print(f"{'=' * 40}")
            for key, value in node_output.items():
                print(f"\n[{key}]:\n{value}")
