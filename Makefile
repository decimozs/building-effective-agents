.PHONY: help run-prompt-chaining run-routing run-parallelization run-orchestrator-workers run-evaluator-optimizer run-agent

help:
	@echo "Available targets:"
	@echo "  make run-prompt-chaining"
	@echo "  make run-routing"
	@echo "  make run-parallelization"
	@echo "  make run-orchestrator-workers"
	@echo "  make run-evaluator-optimizer"
	@echo "  make run-agent"

run-prompt-chaining:
	uv run prompt-chaining/workflow.py

run-routing:
	uv run routing/workflow.py

run-parallelization:
	uv run parallelization/workflow.py

run-orchestrator-workers:
	uv run orchestrator-workers/workflow.py

run-evaluator-optimizer:
	uv run evaluator-optimizer/workflow.py

run-agent:
	uv run agent/agent.py
