import operator
from typing import Annotated, Literal, TypedDict

from langchain.tools import tool
from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from langchain_ollama import ChatOllama
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph
from langfuse import propagate_attributes

from dotenv import load_dotenv

load_dotenv()


@tool
def word_count(text: str) -> int:
    """Count the number of words in the given text."""
    return len(text.split())


@tool
def reading_time(text: str) -> float:
    """Estimate reading time in minutes. Assumes 200 words per minute."""
    words = len(text.split())
    return round(words / 200, 2)


@tool
def sentiment_score(text: str) -> float:
    """
    Return a polarity score for the text from -1.0 (very negative)
    to +1.0 (very positive). Uses a simple keyword heuristic.
    """
    positive_words = {
        "breakthrough",
        "success",
        "growth",
        "improved",
        "great",
        "innovative",
        "benefit",
    }
    negative_words = {
        "breach",
        "fraud",
        "theft",
        "dropped",
        "hack",
        "vulnerability",
        "risk",
        "exposed",
    }

    words = set(text.lower().split())
    pos = len(words & positive_words)
    neg = len(words & negative_words)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 2)


tools = [word_count, reading_time, sentiment_score]
tools_by_name = {t.name: t for t in tools}


llm = ChatOllama(model="lfm2.5-thinking", temperature=0)
llm_tools = llm.bind_tools(tools)


class State(TypedDict):
    article: str

    sentiment: str  # "POSITIVE" | "NEGATIVE" | "NEUTRAL"

    summary: str

    tags: list[str]

    escalation_note: str

    tool_used: str  # name of the tool that was called
    tool_result: str  # stringified result from the tool

    llm_calls: Annotated[int, operator.add]

    messages: Annotated[list[AnyMessage], operator.add]


def classify_node(state: State) -> dict:
    """
    Classify the article into one routing label.

    Small prompts keep the route reliable and the workflow easy to inspect.
    """
    prompt = f"""
You are a sentiment classifier. Read the article below and reply with
EXACTLY one word — either POSITIVE, NEGATIVE, or NEUTRAL. Nothing else.

Article:
{state["article"]}
""".strip()

    response = llm.invoke([HumanMessage(content=prompt)])
    sentiment = response.content.strip().upper()

    if sentiment not in ("POSITIVE", "NEGATIVE", "NEUTRAL"):
        sentiment = "NEUTRAL"

    return {"sentiment": sentiment, "llm_calls": 1, "messages": [response]}


def summarize_node(state: State) -> dict:
    """
    Summarize the article as one independent branch.

    Parallel branches let the workflow do separate work at the same time, then
    combine the results later.
    """
    prompt = f"""
Summarise the following article in exactly 2 sentences.

Article:
{state["article"]}
""".strip()

    response = llm.invoke([HumanMessage(content=prompt)])
    return {"summary": response.content.strip(), "llm_calls": 1, "messages": [response]}


def tag_node(state: State) -> dict:
    """
    Extract tags as a second independent branch.

    Narrow prompts keep each subtask predictable and easy to debug.
    """
    prompt = f"""
Extract up to 5 keywords from the article below.
Reply ONLY with a comma-separated list of keywords. No numbering. No extra text.

Article:
{state["article"]}
""".strip()

    response = llm.invoke([HumanMessage(content=prompt)])
    tags = [t.strip() for t in response.content.strip().split(",") if t.strip()]

    return {"tags": tags, "llm_calls": 1, "messages": [response]}


def escalate_node(state: State) -> dict:
    """
    Draft an escalation note for negative articles.

    Branching keeps unnecessary work out of the positive path.
    """
    prompt = f"""
You are an editorial assistant. The following article has been flagged as NEGATIVE.
Write a one-sentence internal note explaining why it should be reviewed by a human editor.

Summary: {state["summary"]}
""".strip()

    response = llm.invoke([HumanMessage(content=prompt)])
    return {
        "escalation_note": response.content.strip(),
        "llm_calls": 1,
        "messages": [response],
    }


def enrich_node(state: State) -> dict:
    """
    Ask the model which tool to use.

    Tool selection stays separate from tool execution so the agent stays
    modular and easier to reason about.
    """
    prompt = f"""
You have access to tools that can enrich a news article report.
Use exactly ONE tool on the article below to add a useful metric.

Article:
{state["article"]}
""".strip()

    response = llm_tools.invoke([HumanMessage(content=prompt)])
    return {"messages": [response], "llm_calls": 1}


def tool_node(state: State) -> dict:
    """
    Execute the tool the model requested.

    This keeps tool use explicit instead of hiding it inside the model call.
    """
    result_messages = []
    tool_used = ""
    tool_result = ""

    last_message = state["messages"][-1]
    for tool_call in getattr(last_message, "tool_calls", []):
        tool_fn = tools_by_name[tool_call["name"]]
        observation = tool_fn.invoke(tool_call["args"])
        tool_used = tool_call["name"]
        tool_result = str(observation)

        result_messages.append(
            ToolMessage(content=tool_result, tool_call_id=tool_call["id"])
        )

    return {
        "tool_used": tool_used,
        "tool_result": tool_result,
        "messages": result_messages,
    }


def output_node(state: State) -> dict:
    """
    Print the final report in one place.

    One output node keeps the end of the workflow obvious.
    """
    print(f"Sentiment: {state.get('sentiment', 'N/A')}")
    print(f"Tags: {', '.join(state.get('tags', []))}")
    print(f"Summary: {state.get('summary', 'N/A')}")

    if state.get("escalation_note"):
        print(f"Escalation: {state['escalation_note']}")

    if state.get("tool_used"):
        print(f"Tool used: {state['tool_used']}()")
        print(f"Tool result: {state['tool_result']}")

    print(f"Total LLM calls: {state.get('llm_calls', 0)}")
    return {}


def route_after_tag(state: State) -> Literal["escalate", "enrich"]:
    """
    Route the flow after tagging.

    Explicit routing keeps the workflow readable for beginners: classify,
    branch, then continue with the right path.
    """
    if state.get("sentiment") == "NEGATIVE":
        return "escalate"
    return "enrich"


workflow = StateGraph(State)

workflow.add_node("classify", classify_node)
workflow.add_node("summarize", summarize_node)
workflow.add_node("tag", tag_node)
workflow.add_node("escalate", escalate_node)
workflow.add_node("enrich", enrich_node)
workflow.add_node("tool_node", tool_node)
workflow.add_node("output", output_node)

workflow.add_edge(START, "classify")
workflow.add_edge("classify", "summarize")
workflow.add_edge("classify", "tag")
workflow.add_edge("summarize", "output")
workflow.add_conditional_edges("tag", route_after_tag, ["escalate", "enrich"])
workflow.add_edge("escalate", "enrich")
workflow.add_edge("enrich", "tool_node")
workflow.add_edge("tool_node", "output")
workflow.add_edge("output", END)

graph = workflow.compile()


POSITIVE_ARTICLE = """
Scientists at MIT announced a breakthrough in renewable energy storage today.
The new solid-state battery technology can hold three times the charge of current
lithium-ion cells at half the cost. Researchers say commercial production could
begin within two years, potentially transforming the electric vehicle industry
and making solar power viable even in cloudy regions.
"""

NEGATIVE_ARTICLE = """
A major data breach exposed the personal records of over 50 million users from
a popular social media platform. Hackers gained access through an unpatched
vulnerability that had been reported to the company six months ago but left
unaddressed. Affected users are now at risk of identity theft and financial fraud.
The company's stock dropped 18% following the announcement.
"""


langfuse_handler = CallbackHandler()

if __name__ == "__main__":
    for label, article in [
        ("POSITIVE", POSITIVE_ARTICLE),
        ("NEGATIVE", NEGATIVE_ARTICLE),
    ]:
        print(f"Running pipeline on a {label} article...")

        with propagate_attributes(
            metadata={"type": "agent-using-tools"},
            tags=["agent"],
        ):
            for step in graph.stream(
                {
                    "article": article,
                    "sentiment": "",
                    "summary": "",
                    "tags": [],
                    "escalation_note": "",
                    "tool_used": "",
                    "tool_result": "",
                    "llm_calls": 0,
                    "messages": [],
                },
                config={"callbacks": [langfuse_handler]},
            ):
                for node_name in step:
                    print(f"Node finished: {node_name}")
