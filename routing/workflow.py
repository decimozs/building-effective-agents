from typing import TypedDict
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from langfuse.langchain import CallbackHandler

load_dotenv()


class State(TypedDict):
    query: str
    intent: str
    answer: str


llm = ChatOllama(model="lfm2.5-thinking", temperature=0)


def general_questions(state: State) -> dict:
    """Handle open-ended customer questions.

    One node, one job. Small specialist prompts are easier to control, debug,
    and improve than one large prompt that tries to answer everything.
    """
    msg = llm.invoke(
        [
            SystemMessage(
                content="You are a customer service agent. Answer general questions clearly, politely, and briefly. Ask a direct follow-up question if needed."
            ),
            HumanMessage(content=state.get("query")),
        ]
    )
    return {"answer": msg.content}


def request_refund(state: State) -> dict:
    """Handle refund requests as a dedicated path.

    Routing refunds into their own node keeps policy-heavy behavior isolated
    from general support. That makes the agent simpler for beginners to reason
    about and safer to extend later.
    """
    msg = llm.invoke(
        [
            SystemMessage(
                content="You are a customer service agent handling refund requests. Ask for order details if needed, explain the refund process clearly, and give the next step."
            ),
            HumanMessage(content=state.get("query")),
        ]
    )
    return {"answer": msg.content}


def technical_support(state: State) -> dict:
    """Handle technical support as a separate specialist path.

    Troubleshooting needs different questions and steps than refunds or general
    questions. Separate routing prevents one prompt from becoming too broad.
    """
    msg = llm.invoke(
        [
            SystemMessage(
                content="You are a customer service agent handling technical support. Troubleshoot step by step, ask for missing details, and provide clear fixes or next actions."
            ),
            HumanMessage(content=state.get("query")),
        ]
    )
    return {"answer": msg.content}


def check_intent(state: State) -> dict:
    """Classify the user request before answering.

    This is the routing step. The workflow decides what the user wants first,
    then sends the request to the right specialist node. That is the core
    Building Effective Agents pattern: route first, answer second.
    """
    msg = llm.invoke(
        [
            SystemMessage(
                content=f"""Check the intent of this user query: {state.get("query")}
                        Reply with ONLY one word if the user query intent is for technical support return 'technical_support', if for requesting request_refund return 'request_refund' else return 'general_questions'
                        Do not explain. Do not add anything else. Just one word."""
            ),
            HumanMessage(content=state.get("query")),
        ]
    )
    return {"intent": msg.content}


def route_intent(state: State) -> str:
    """Map the classifier output to a graph branch.

    Explicit routing keeps the flow easy to inspect: classify, branch, answer.
    Beginners can test each path independently instead of debugging one large
    prompt that handles every support case.
    """
    intent = (state.get("intent") or "").lower().strip()

    if not intent:
        return "fail"

    if "request_refund" in intent:
        return "request_refund"
    if "technical_support" in intent:
        return "technical_support"
    return "general_questions"


workflow = StateGraph(State)

# Explicit routing keeps the agent modular: one classifier, three specialist nodes, one clear path per intent.
workflow.add_node("general_questions", general_questions)
workflow.add_node("request_refund", request_refund)
workflow.add_node("technical_support", technical_support)
workflow.add_node("check_intent", check_intent)

workflow.add_edge(START, "check_intent")
workflow.add_conditional_edges(
    "check_intent",
    route_intent,
    {
        "general_questions": "general_questions",
        "technical_support": "technical_support",
        "request_refund": "request_refund",
        "fail": END,
    },
)
# End after one specialist response. Keep the workflow simple unless a real use case needs multi-turn refinement.
workflow.add_edge("general_questions", END)
workflow.add_edge("request_refund", END)
workflow.add_edge("technical_support", END)

graph = workflow.compile()

langfuse_handler = CallbackHandler()

for step in graph.stream(
    {"query": "What is programming?", "intent": "", "answer": ""},
    config={"callbacks": [langfuse_handler]},
):
    for node_name, node_output in step.items():
        print(f"\n{'=' * 40}")
        print(f"Node: {node_name}")
        print(f"{'=' * 40}")
        for key, value in node_output.items():
            print(f"\n[{key}]:\n{value}")
