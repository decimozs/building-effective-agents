from typing import Literal, TypedDict
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

load_dotenv()


class Feedback(BaseModel):
    status: Literal["funny", "not_funny"] = Field(description="Feedback status")
    feedback: str = Field(description="Feedback for the joke")


class State(TypedDict):
    topic: str
    joke: str
    feedback: str
    status: str
    iter: int


llm = ChatOllama(model="lfm2.5-thinking", temperature=0)
evaluator_llm = llm.with_structured_output(Feedback)


def generator(state: State) -> dict:
    """Generate a joke, then refine it using prior feedback.

    This is the optimizer side of the loop. The generator stays focused on the
    current attempt, while the evaluator later provides the improvement signal.
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

    In an evaluator-optimizer loop, the evaluator acts like a critic. The loop
    improves quality by repeatedly feeding critique back into generation.
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

    This keeps the loop explicit for beginners: generate, evaluate, then either
    accept the result or send feedback back into another generation pass.
    """
    if state.get("status") == "funny":
        return "accepted"
    elif state.get("status") == "not_funny":
        return "rejected + feedback"


workflow = StateGraph(State)

# The loop alternates between generation and evaluation until the critic accepts.
workflow.add_node("generator", generator)
workflow.add_node("evaluator", evaluator)

workflow.add_edge(START, "generator")
workflow.add_edge("generator", "evaluator")
workflow.add_conditional_edges(
    "evaluator", route, {"accepted": END, "rejected + feedback": "generator"}
)
# Stop only when the evaluator says the joke is funny.

graph = workflow.compile()

langfuse_handler = CallbackHandler()

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
