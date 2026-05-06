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
    name: str = Field(description="Name for this section report")
    description: str = Field(description="Brief overview of this report")


class Sections(BaseModel):
    sections: List[Section] = Field(description="Sections of the report")


class State(TypedDict):
    topic: str
    sections: list[Section]
    completed_sections: Annotated[list, operator.add]
    final_report: str


class WorkerState(TypedDict):
    section: Section
    completed_sections: Annotated[list, operator.add]


llm = ChatOllama(model="lfm2.5-thinking", temperature=0)
planner = llm.with_structured_output(Sections)


def orchestrator(state: State) -> dict:
    """Break the topic into smaller sections before work is delegated.

    This is the orchestrator step from BEA: plan first, then hand off focused
    pieces to workers. That keeps each worker prompt narrow and predictable.
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
    """
    completed_sections = state.get("completed_sections")
    completed_report_sections = "\n\n---\n\n".join(completed_sections)
    return {"final_report": completed_report_sections}


def assign(state: State) -> list[Send]:
    """Create one worker task per planned section.

    This is the fan-out moment: the graph sends independent units of work to
    parallel workers instead of asking one node to write the whole report.
    """
    return [Send("llm_call", {"section": s}) for s in state["sections"]]


workflow = StateGraph(State)

# Plan, fan out to workers, then synthesize the result.
workflow.add_node("orchestrator", orchestrator)
workflow.add_node("llm_call", llm_call)
workflow.add_node("synthesizer", synthesizer)

workflow.add_edge(START, "orchestrator")
workflow.add_conditional_edges("orchestrator", assign, ["llm_call"])
workflow.add_edge("llm_call", "synthesizer")
# One final merge keeps the output deterministic and easy to inspect.
workflow.add_edge("synthesizer", END)

graph = workflow.compile()

langfuse_handler = CallbackHandler()

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
