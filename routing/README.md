# Routing

## What This Pattern Is
Routing classifies an input first, then sends it to the right specialist path.

## Why It Matters
It keeps prompts focused and reduces confusion by separating different kinds of requests.

## When To Use It
Use it when inputs fall into distinct categories that need different handling.

## When Not To Use It
Do not use it when every request should follow the same path.

## Anthropic BEA Connection
This follows the BEA idea of separation of concerns through explicit control flow.

## How This Repo Demonstrates It
This folder shows customer support routing for general questions, refund requests, and technical support.

## Run It
```bash
make run-routing
```

## Key Takeaway
Routing makes one system behave like several focused specialists.
