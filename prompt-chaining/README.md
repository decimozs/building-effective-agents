# Prompt Chaining

## What This Pattern Is
Prompt chaining breaks one task into a sequence of smaller steps. Each step uses the output of the previous step.

## Why It Matters
This pattern makes complex work easier to control. Smaller prompts are often more reliable than one large prompt.

## When To Use It
Use it when a task can be cleanly split into ordered subtasks, such as drafting, checking, and refining.

## When Not To Use It
Do not use it when a single prompt already solves the task well.

## Anthropic BEA Connection
This matches the idea of starting simple and composing small steps only when they improve the result.

## How This Repo Demonstrates It
This folder shows a workflow where an outline is generated, checked, improved, and then finalized.

## Run It
```bash
make run-prompt-chaining
```

## Key Takeaway
Prompt chaining helps when the task is easier to solve step by step than all at once.
