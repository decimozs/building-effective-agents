# Orchestrator-Workers

## What This Pattern Is
An orchestrator breaks a task into parts and delegates those parts to worker nodes.

## Why It Matters
It helps with tasks where the needed subtasks are not known ahead of time.

## When To Use It
Use it for complex work that needs planning, delegation, and later synthesis.

## When Not To Use It
Do not use it when the task is already small and fixed.

## Anthropic BEA Connection
This reflects the BEA idea of using a central planner with focused subworkers.

## How This Repo Demonstrates It
This folder shows a report workflow where sections are planned, assigned to workers, and merged into one final report.

## Run It
```bash
make run-orchestrator-workers
```

## Key Takeaway
Orchestrator-workers works best when the task needs dynamic decomposition.
