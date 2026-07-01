# How I Built G-Code

A short write-up of how I built **G-Code** — a local AI coding agent that runs
entirely on my own machine (no API keys, no cloud), inspired by tools like
Claude Code.

The goal wasn't just "call an LLM." It was to build a real **agent**: something
that reasons, decides to use tools, does actual work on my computer, and knows
when it's finished. Here's how it came together.

---

## The core idea: an agent is a loop, not a prompt

A chatbot answers once. An **agent** thinks in a loop — decide, act, look at the
result, decide again — until the job is done. I built G-Code around the classic
**ReAct** pattern (Reason + Act), turned into an explicit 5-step state machine:

```
START   → restate what the user wants
PLAN    → reason about how to do it
TOOL    → call a tool (run a command / write a file)
OBSERVE → read the tool's result
OUTPUT  → give the final answer (ends the turn)
```

The model loops `PLAN → TOOL → OBSERVE` as many times as needed, then finishes
with `OUTPUT`. My Python code is just the engine that runs this loop, executes
the tools the model asks for, and feeds results back in.

---

## Making the model output something I can trust

The hard part of any agent is: **how do you reliably know what the model wants
to do?** Free-form text is a nightmare to parse. So every single step the model
produces is a **structured JSON object** with a fixed shape:

```json
{"step": "TOOL", "tool_name": "runCommand", "input": "mkdir Todo",
 "content": "", "output": ""}
```

I defined that shape once with a **Pydantic** model (`MyoutputFormat`) and handed
its JSON schema straight to Ollama as a `format=` constraint. That means the model
is *forced* to reply in valid JSON matching my schema — and I validate it with
Pydantic before acting. No regex, no guessing.

---

## The tools

Tools are just plain Python functions registered in a dictionary. When the model
says `"tool_name": "writeFile"`, my loop looks it up and calls it:

```python
Available_Tools = {
    "runCommand": runCommand,   # run a Windows shell command
    "writeFile":  writeFile,    # create a file (path + content)
    "get_weather": get_weather, # live weather from wttr.in
}
```

Adding a new capability is literally: write a function, add one line to the dict.
That was a deliberate design choice — I wanted extending the agent to be trivial.

---

## The problem that taught me the most: stopping the model from lying

Early on, the agent would happily say *"Done! I created your folder"* — without
ever actually creating it. LLMs love to *describe* success instead of *doing* it.

My fix was a **guard rail**: the loop refuses to accept an `OUTPUT` step unless a
tool has actually run for that task. If the model tries to finish early, I inject
a message telling it to actually do the work, and the loop continues. That single
rule is what makes the agent *trustworthy* — it can't claim credit for work it
didn't do.

---

## Evolving it: from "code only" to "general assistant"

At first G-Code only did coding/system tasks. I wanted it to also answer normal
questions ("explain recursion", "capital of France?"). But that broke my guard
rail — general questions need **zero** tools, yet the guard demanded one.

The naive fix (remove the guard) had an ugly side effect: the agent went back to
stopping and *chatting* mid-task ("Shall I create that? yes? okay next?") instead
of just building the thing.

So I added an **intent classifier**: before the main loop, a quick second LLM call
labels each message as **`task`** or **`chat`**.

- **`chat`** → answer directly, no tools, guard off.
- **`task`** → guard on: don't stop, don't ask permission, run every tool step
  until the whole thing is built, *then* output.

That gave me the best of both worlds — a conversational assistant that still
executes real multi-step projects autonomously in one shot.

---

## Making it feel good to use

The raw loop dumped JSON to the terminal, which looked awful. I switched the whole
front-end to the **`rich`** library:

- A **spinner** while the model thinks.
- A dim, quiet trace of the reasoning steps.
- Clean tool-call lines (`⚙ writeFile …  ↳ created`).
- The final answer rendered as **formatted Markdown** in a panel — bold, bullet
  lists, and code blocks all display properly, like a real assistant.

Small thing, big difference. It went from "a script" to "a tool I enjoy using."

---

## Windows gotchas I ran into

Running real commands on a real OS surfaced real bugs:

- The model wrote `mkdir a; mkdir b` — but `cmd.exe` doesn't chain with `;`.
- It used `mkdir Todo/html` — forward slashes make cmd throw *"syntax of the
  command is incorrect."*

I fixed these in the **system prompt** by teaching the model the Windows rules:
one command per step, backslashes, and `mkdir` can create nested folders in one go.
A good chunk of "agent building" turned out to be *prompt engineering* — writing
precise rules and worked examples so a 7B model behaves reliably.

---

## The stack

| Piece | Why |
|-------|-----|
| **Ollama + `qwen2.5:7b`** | Runs the LLM locally — private, free, offline |
| **Pydantic** | Forces + validates structured JSON output |
| **`rich`** | The clean terminal UI |
| **`requests`** | The weather tool |
| **Plain Python loop** | The agent engine itself — no framework |

Notably, I **didn't** use LangChain or any agent framework. Building the loop by
hand is what actually taught me how agents work under the hood.

---

## What I'd tell someone building their own

1. **An agent is a loop with tools and a stopping condition** — that's the whole
   secret.
2. **Structured output is non-negotiable.** Constrain the model to JSON and
   validate it; everything downstream gets easier.
3. **Guard rails matter more than the model.** The rule "you must actually run a
   tool before claiming success" is what makes it honest.
4. **Most of the magic is in the prompt.** Clear rules + concrete examples beat a
   bigger model.

---

*Built by Gagan Singh — a local, transparent, hackable coding agent.*
