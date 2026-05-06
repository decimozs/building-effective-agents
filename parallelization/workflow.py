from typing import Annotated, List, TypedDict
from dotenv import load_dotenv
from langfuse.langchain import CallbackHandler
from langchain_ollama import ChatOllama
import operator
from langfuse import propagate_attributes

from langgraph.graph import END, START, StateGraph

load_dotenv()


class State(TypedDict):
    query: str
    tagalog: str
    french: str
    japanese: str
    results: Annotated[List, operator.add]


llm = ChatOllama(model="lfm2.5-thinking", temperature=0)


def translate_to_tagalog(state: State) -> dict:
    """Translate the same input independently into Tagalog.

    Parallelization works when one input can be split into independent subtasks
    without one branch depending on another.
    """
    msg = llm.invoke(
        f"""Translate this to tagalog '{state.get("query")}'.
        Dont provide any explaination just return only the translation.
        """
    )
    return {"tagalog": msg.content}


def translate_to_french(state: State) -> dict:
    """Translate the same input independently into French.

    Each branch does one small job. That keeps the graph simple and lets the
    workflow run more than one model call at the same time.
    """
    msg = llm.invoke(
        f"""Translate this to french '{state.get("query")}'.
        Dont provide any explaination just return only the translation.
        """
    )
    return {"french": msg.content}


def translate_to_japanese(state: State) -> dict:
    """Translate the same input independently into Japanese.

    This is a textbook parallel pattern: same source, separate outputs, then a
    merge step at the end.
    """
    msg = llm.invoke(
        f"""Translate this to japanese '{state.get("query")}'.
        Dont provide any explaination just return only the translation.
        """
    )
    return {"japanese": msg.content}


def aggregate(state: State) -> dict:
    """Collect the parallel outputs into a single result bundle.

    Fan-out/fan-in design makes the orchestration easy to follow: branch first,
    then gather all completed work in one place.
    """
    tagalog = f"Translation to tagalog: {state.get('tagalog')}"
    french = f"Translation to french: {state.get('french')}"
    japanese = f"Translation to japanese: {state.get('japanese')}"
    return {"results": [tagalog, french, japanese]}


langfuse_handler = CallbackHandler()

workflow = StateGraph(State)

# Fan out from one input to three independent translation nodes.
workflow.add_node("translate_to_tagalog", translate_to_tagalog)
workflow.add_node("translate_to_japanese", translate_to_japanese)
workflow.add_node("translate_to_french", translate_to_french)
workflow.add_node("aggregate", aggregate)

workflow.add_edge(START, "translate_to_tagalog")
workflow.add_edge(START, "translate_to_french")
workflow.add_edge(START, "translate_to_japanese")
workflow.add_edge("translate_to_tagalog", "aggregate")
workflow.add_edge("translate_to_french", "aggregate")
workflow.add_edge("translate_to_japanese", "aggregate")
# Merge after all branches finish so the final output is complete.
workflow.add_edge("aggregate", END)

graph = workflow.compile()


with propagate_attributes(
    metadata={"type": "parallelization"},
    tags=["workflow"],
):
    for step in graph.stream(
        {
            "query": "Hello world",
            "tagalog": "",
            "french": "",
            "japanese": "",
            "results": [],
        },
        config={"callbacks": [langfuse_handler]},
    ):
        for node_name, node_output in step.items():
            print(f"\n{'=' * 40}")
            print(f"Node: {node_name}")
            print(f"{'=' * 40}")
            for key, value in node_output.items():
                print(f"\n[{key}]:\n{value}")
