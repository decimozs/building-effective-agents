# Tool-Using Agent

<img width="2401" height="1000" alt="image" src="https://github.com/user-attachments/assets/5a5c4ff8-f575-4dcf-800a-010f91a65004" />

## What This Pattern Is
A tool-using agent lets the model choose and use tools as part of its workflow.

## Why It Matters
Tools let the agent do more than generate text. They let it act with external capabilities.

## When To Use It
Use it when the task needs actions, lookups, calculations, or other tool support.

## When Not To Use It
Do not use it when the model can answer safely and well without tools.

## Anthropic BEA Connection
This fits the BEA principle of clear tool design, explicit control flow, and small, focused responsibilities.

## How This Repo Demonstrates It
This folder shows an agent that classifies content, summarizes it, branches when needed, and uses tools explicitly.

## Run It
```bash
make run-agent
```

## Key Takeaway
Tool use is most effective when it is explicit, narrow, and easy to trace.
