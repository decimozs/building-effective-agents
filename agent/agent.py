# =============================================================================
# agent/agent.py
#
# Agent: Tool-Using Workflow
#
# Classifies news articles by sentiment, summarizes content, extracts tags,
# escalates negative articles, and enriches reports using LLM-powered tools.
# Built on LangGraph as a state machine with parallel branches and conditional
# routing.
#
# Pattern: Agent (tool-using)
#   - Model decides which tool to call based on the task
#   - Tools are defined explicitly and registered by name
#   - Tool execution is separated from model inference for debuggability
# =============================================================================

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

# ---------------------------------------------------------------------------
# Tool Definitions
# ---------------------------------------------------------------------------


@tool
def word_count(text: str) -> int:
    """Count the number of words in the given text.

    Tokenises the input by splitting on whitespace. Punctuation attached
    to a word is counted as part of that word.

    Args:
        text: The input text to count words in.

    Returns:
        Total word count as an integer.
    """
    return len(text.split())


@tool
def reading_time(text: str) -> float:
    """Estimate reading time in minutes.

    Uses the standard 200 words-per-minute average reading speed.

    Args:
        text: The input text to estimate reading time for.

    Returns:
        Estimated reading time in minutes, rounded to 2 decimal places.
    """
    words = len(text.split())
    return round(words / 200, 2)


@tool
def sentiment_score(text: str) -> float:
    """Score the sentiment polarity of the input text.

    Returns a value in [-1.0, 1.0] where -1.0 is very negative and +1.0
    is very positive. Uses a simple keyword-matching heuristic against
    predefined positive and negative word lists.

    Args:
        text: The input text to analyse for sentiment.

    Returns:
        Polarity score rounded to 2 decimal places. Returns 0.0 when no
        sentiment keywords are found.
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

# ---------------------------------------------------------------------------
# LLM Setup
# ---------------------------------------------------------------------------

llm = ChatOllama(model="lfm2.5-thinking", temperature=0)
llm_tools = llm.bind_tools(tools)


class State(TypedDict):
    """Graph state for the agent workflow.

    Carries all data produced and consumed by nodes as the article flows
    through classification, summarization, tagging, enrichment, and output.

    Attributes:
        article: Raw input article text.
        sentiment: One of POSITIVE, NEGATIVE, or NEUTRAL.
        summary: Two-sentence summary of the article.
        tags: Up to 5 extracted keywords.
        escalation_note: Internal note for human review (negative articles only).
        tool_used: Name of the tool called during enrichment.
        tool_result: Stringified result returned by the tool.
        llm_calls: Running count of LLM invocations (accumulated via operator.add).
        messages: Message history maintained by LangGraph for state tracking.
    """
    article: str

    sentiment: str

    summary: str

    tags: list[str]

    escalation_note: str

    tool_used: str
    tool_result: str

    llm_calls: Annotated[int, operator.add]

    messages: Annotated[list[AnyMessage], operator.add]


def classify_node(state: State) -> dict:
    """Classify the article sentiment into a routing label.

    Reads the raw article and returns one of POSITIVE, NEGATIVE, or NEUTRAL.
    A fallback ensures the classifier always returns a valid label even when
    the model produces unexpected output.

    Args:
        state: Current graph state containing the article text.

    Returns:
        Dict with sentiment label, llm_calls counter, and the response message.
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
    """Summarise the article as one independent branch.

    Runs in parallel with tagging so the workflow does separate work
    concurrently before aggregating results.

    Args:
        state: Current graph state containing the article text.

    Returns:
        Dict with summary string, llm_calls counter, and the response message.
    """
    prompt = f"""
Summarise the following article in exactly 2 sentences.

Article:
{state["article"]}
""".strip()

    response = llm.invoke([HumanMessage(content=prompt)])
    return {"summary": response.content.strip(), "llm_calls": 1, "messages": [response]}


def tag_node(state: State) -> dict:
    """Extract keywords from the article as a second independent branch.

    Runs in parallel with summarization. A narrow prompt keeps extraction
    predictable and easy to debug.

    Args:
        state: Current graph state containing the article text.

    Returns:
        Dict with a list of tag strings, llm_calls counter, and the response message.
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
    """Draft an escalation note for negative articles.

    Only reached via the conditional edge from tag_node when sentiment is
    NEGATIVE. Branching keeps unnecessary LLM calls out of the positive path.

    Args:
        state: Current graph state containing the summary text.

    Returns:
        Dict with escalation_note string, llm_calls counter, and the response message.
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
    """Ask the model which tool to use on the article.

    Tool selection is separated from tool execution so the agent stays modular
    and each concern can be reasoned about independently.

    Args:
        state: Current graph state containing the article text.

    Returns:
        Dict with the model response message and llm_calls counter.
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
    """Execute the tool the model requested.

    Reads tool_calls from the last message in state and dispatches each call
    to the appropriate tool function. Keeps tool use explicit instead of hiding
    it inside the model call.

    Args:
        state: Current graph state containing the message history.

    Returns:
        Dict with tool_used name, tool_result string, and tool response messages.
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
    """Print the final report to stdout.

    Aggregates all workflow outputs into a single printed summary. A single
    output node keeps the end of the workflow obvious and easy to modify.

    Args:
        state: Completed graph state with all node outputs populated.

    Returns:
        Empty dict (terminal node, no state mutations).
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
    """Route the flow after tagging based on sentiment.

    Negative articles are sent to escalation before enrichment; positive and
    neutral articles skip escalation entirely. Explicit routing keeps the
    workflow readable for beginners.

    Args:
        state: Current graph state containing the sentiment label.

    Returns:
        Literal "escalate" if sentiment is NEGATIVE, otherwise "enrich".
    """
    if state.get("sentiment") == "NEGATIVE":
        return "escalate"
    return "enrich"


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Sample Articles
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Workflow Execution
# ---------------------------------------------------------------------------

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
