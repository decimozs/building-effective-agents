from typing import TypedDict
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langfuse.langchain import CallbackHandler
from dotenv import load_dotenv

load_dotenv()


class State(TypedDict):
    topic: str
    document_outline: str
    improve_document_outline: str
    document_status: str
    final_document_outline: str


llm = ChatOllama(model="lfm2.5-thinking", temperature=0)


def generate_doucument_outline(state: State) -> dict:
    msg = llm.invoke(f"Write document outline about {state.get('topic')}")
    return {"document_outline": msg.content}


def improve_doucument_outline(state: State) -> dict:
    msg = llm.invoke(f"Improve this document outline: {state.get('document_outline')}")
    return {"improve_document_outline": msg.content}


def final_document_outline(state: State) -> dict:
    msg = llm.invoke(
        f"Polish this improve document outline: {state.get('improve_document_outline')}"
    )
    return {"final_document_outline": msg.content}


def check_document_outline(state: State) -> dict:
    msg = llm.invoke(
        f"Check this document outline: {state.get('document_outline')} "
        f"if the topic is for science, if it is return passed if not return fail."
        f"Reply with ONLY one word: 'passed' if it is science, 'fail' if it is not. "
        f"Do not explain. Do not add anything else. Just one word."
    )
    return {"document_status": msg.content}


def route_document(state: State) -> str:
    document_status = state.get("document_status", "").lower()
    if "passed" in document_status:
        return "passed"
    return "fail"


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
