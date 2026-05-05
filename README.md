# Building Effective Agents with LangGraph

This repository is about building effective agents with LangGraph by exploring the core patterns from Anthropic's newsletter and seeing how they work in code.

The goal is to understand how to design agent workflows that stay simple, clear, and reliable. Instead of putting everything into one large prompt, LangGraph lets each part of the agent do one job well and makes the full flow easier to follow.

This project covers patterns like:
- prompt chaining
- routing
- parallelization
- orchestrator-workers
- evaluator-optimizer
- tool-using agents

Each example shows a different way to structure agent behavior so the system becomes easier to control, debug, and improve.

## Setup and Installation

### 1. Clone the repository

```bash
git clone https://github.com/decimozs/building-effective-agents.git
cd building-effective-agents
```

### 2. Install `uv`

If you do not have `uv` yet, install it from Astral:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Install dependencies

```bash
uv sync
```

### 4. Run an example

Use the Makefile targets:

```bash
make run-prompt-chaining
make run-routing
make run-parallelization
make run-orchestrator-workers
make run-evaluator-optimizer
make run-agent
```

If you prefer direct execution:

```bash
uv run prompt-chaining/workflow.py
```

## Tech Stack

This repository uses:
- **Python** for the workflow code
- **LangGraph** for graph-based agent orchestration
- **LangChain** for model and tool integration
- **Ollama** for local model execution
- **LFM2.5 Thinking** as the main model used in the examples
- **Langfuse** for tracing and run observability
- **Pydantic** for structured outputs
- **python-dotenv** for environment variable loading

## Makefile Targets

```bash
make help
```

Available targets:
- `make run-prompt-chaining`
- `make run-routing`
- `make run-parallelization`
- `make run-orchestrator-workers`
- `make run-evaluator-optimizer`
- `make run-agent`

## Core Concepts

A few educational ideas come up repeatedly in agent design:

- **Single responsibility**: each node should do one job well instead of handling everything at once.
- **Decomposition**: complex tasks become easier when you break them into smaller steps.
- **Routing**: different inputs may need different paths, prompts, or tools.
- **Parallelism**: independent subtasks can run at the same time to improve efficiency.
- **Iteration**: some tasks improve through feedback loops instead of one pass.
- **Tool use**: agents become more useful when they can act on the environment, not just generate text.
- **Control flow visibility**: explicit graphs make agent behavior easier to debug and trust.

These concepts are the foundation of building effective agents with LangGraph.

## Reference

Inspired by Anthropic's newsletter:

**Engineering at Anthropic - Building effective agents**
Published Dec 19, 2024

https://www.anthropic.com/engineering/building-effective-agents
