# Evaluator-Optimizer

## What This Pattern Is
This pattern loops between generating output and evaluating it.

## Why It Matters
It improves quality by using feedback to guide the next attempt.

## When To Use It
Use it when the output can be judged and refined over multiple rounds.

## When Not To Use It
Do not use it when one pass is already good enough.

## Anthropic BEA Connection
This follows the BEA idea that iterative refinement can produce better results than a single model call.

## How This Repo Demonstrates It
This folder shows a joke generator that keeps improving based on evaluator feedback until the result is accepted.

## Run It
```bash
make run-evaluator-optimizer
```

## Key Takeaway
Evaluator-optimizer is useful when feedback can clearly improve the result.
