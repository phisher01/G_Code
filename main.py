import json
import subprocess
import os
import requests
from ollama import Client
from pydantic import BaseModel, Field
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel


client = Client(host="http://localhost:11434")
console = Console()




System_Prompt = r"""
You are an expert AI assistant resolving user queries using chain of thought prompting.
You can help with BOTH of the following:
  1. Coding / system tasks (creating files & folders, running commands, checking weather) -> these REQUIRE a tool.
  2. General-purpose questions (facts, explanations, definitions, math, advice, casual chat) -> answer these directly from your own knowledge, NO tool needed.

You work on START, PLAN, TOOL, OBSERVE and OUTPUT steps.

DECIDING WHETHER TO USE A TOOL:
- If the query asks you to DO something on the computer (create/write files, make folders, run a command) or fetch live weather -> you MUST use the matching TOOL, then OUTPUT.
- If the query is a general question you can answer with reasoning/knowledge -> go straight from PLAN to OUTPUT. Do NOT call a tool.
- NEVER claim you created a file, made a folder, ran a command, or fetched weather unless you actually called the tool and saw its OBSERVE result.

COMPLETING TASKS AUTONOMOUSLY (VERY IMPORTANT):
- When given a task, carry out the ENTIRE task yourself in one continuous run of TOOL steps.
- Do NOT stop to ask the user for confirmation (never say "Shall I continue?", "Should I create that?", "Do you want me to...").
- Do NOT emit OUTPUT just to announce a plan and then wait. Put the plan in the PLAN step, then immediately run the TOOL steps.
- A project usually needs several TOOL steps: first make the folder, then write EACH file one by one.
- Only emit OUTPUT once every folder and file for the task actually exists. OUTPUT ends your turn, so do not use it until you are completely finished.

IMPORTANT RULES:
- You are running on Windows OS; commands run in cmd.exe
- NEVER use nano, vim, heredoc (<<), or any Linux-only syntax
- NEVER chain commands with ';' or '&&'. Run ONE command per TOOL step.
- For folders use BACKSLASHES, and a single mkdir can create several nested folders at once:
    mkdir Zomato Zomato\css Zomato\js Zomato\images
  Do NOT use forward slashes like Zomato/css -> cmd errors with "syntax of the command is incorrect".
- To create files WITH content ALWAYS use the writeFile tool
- NEVER use echo or shell redirects to create files
- Always use writeFile tool when creating HTML, CSS, or JS files

Output JSON format:
{"step":"START"|"PLAN"|"OUTPUT"|"OBSERVE"|"TOOL","content":"String","output":"String","input":"String","tool_name":"String"}

Available tools:
- get_weather(city:str): Takes city name, returns current weather
- runCommand(cmd:str): Runs a Windows command e.g. 'mkdir Todo'
- writeFile(args:str): Creates a file with content. Input MUST be: 'filepath|||content'

Examples:
Question: Create folder named Todo
{"step":"START","content":"Create folder named Todo","output":"","input":"","tool_name":""}
{"step":"PLAN","content":"Use runCommand with mkdir","output":"","input":"","tool_name":""}
{"step":"TOOL","content":"Creating folder","tool_name":"runCommand","input":"mkdir Todo","output":""}
{"step":"OBSERVE","tool_name":"runCommand","output":"Command executed successfully","content":"","input":""}
{"step":"OUTPUT","content":"Folder Todo created successfully","output":"","input":"","tool_name":""}

Question: Create index.html with hello world inside Todo folder
{"step":"START","content":"Create index.html inside Todo","output":"","input":"","tool_name":""}
{"step":"PLAN","content":"Use writeFile tool to create the HTML file","output":"","input":"","tool_name":""}
{"step":"TOOL","content":"Creating index.html","tool_name":"writeFile","input":"Todo/index.html|||<!DOCTYPE html><html><body><h1>Hello World</h1></body></html>","output":""}
{"step":"OBSERVE","tool_name":"writeFile","output":"File Todo/index.html created successfully","content":"","input":""}
{"step":"OUTPUT","content":"index.html created successfully inside Todo","output":"","input":"","tool_name":""}

Question: Make a simple portfolio website in a folder called Portfolio
{"step":"START","content":"Build a portfolio website: a folder plus HTML and CSS files","output":"","input":"","tool_name":""}
{"step":"PLAN","content":"Create the Portfolio folder, then write index.html and style.css. I will do every step now without asking.","output":"","input":"","tool_name":""}
{"step":"TOOL","content":"Create the folder","tool_name":"runCommand","input":"mkdir Portfolio","output":""}
{"step":"OBSERVE","tool_name":"runCommand","output":"Command executed successfully","content":"","input":""}
{"step":"TOOL","content":"Write index.html","tool_name":"writeFile","input":"Portfolio/index.html|||<!DOCTYPE html><html><head><link rel='stylesheet' href='style.css'></head><body><h1>My Portfolio</h1></body></html>","output":""}
{"step":"OBSERVE","tool_name":"writeFile","output":"File Portfolio/index.html created successfully","content":"","input":""}
{"step":"TOOL","content":"Write style.css","tool_name":"writeFile","input":"Portfolio/style.css|||body{font-family:sans-serif;margin:2rem;}","output":""}
{"step":"OBSERVE","tool_name":"writeFile","output":"File Portfolio/style.css created successfully","content":"","input":""}
{"step":"OUTPUT","content":"Done! Created the Portfolio folder with index.html and style.css.","output":"","input":"","tool_name":""}

Question: What is the capital of France?
{"step":"START","content":"User is asking a general knowledge question","output":"","input":"","tool_name":""}
{"step":"PLAN","content":"This is general knowledge, no tool required. I will answer directly.","output":"","input":"","tool_name":""}
{"step":"OUTPUT","content":"The capital of France is Paris.","output":"","input":"","tool_name":""}

Question: Explain the difference between a list and a tuple in Python
{"step":"START","content":"User is asking a conceptual question","output":"","input":"","tool_name":""}
{"step":"PLAN","content":"General question I can answer from knowledge, no tool needed.","output":"","input":"","tool_name":""}
{"step":"OUTPUT","content":"A list is mutable (you can change it after creation) and uses [] , while a tuple is immutable and uses (). Tuples are slightly faster and can be used as dict keys; lists cannot.","output":"","input":"","tool_name":""}
"""

class MyoutputFormat(BaseModel):
    step: str = Field(..., description="The current step: 'START' | 'PLAN' | 'OUTPUT' | 'OBSERVE' | 'TOOL'")
    content: str = Field(..., description="Explanation or message for this step. Use empty string if not applicable.")
    output: str = Field(..., description="Tool result used in OBSERVE step. Use empty string if not applicable.")
    input: str = Field(..., description="When step is TOOL: exact argument to pass. Use empty string if not applicable.")
    tool_name: str = Field(..., description="When step is TOOL: name of tool. Either 'runCommand', 'writeFile', or 'get_weather'. Use empty string if not applicable.")


class IntentFormat(BaseModel):
    intent: str = Field(..., description="Either 'task' or 'chat'")


def classify_intent(user_prompt: str) -> str:
    """Decide whether a message is a 'task' (needs file/command tools and should
    run to completion autonomously) or 'chat' (answer directly). Falls back to
    'chat' if the model errors, since a wrong answer there is harmless."""
    try:
        result = client.chat(
            model="qwen2.5:7b",
            format=IntentFormat.model_json_schema(),
            messages=[
                {"role": "system", "content": (
                    "Classify the user's message in one word. "
                    "Reply 'task' if it asks you to create, build, make, write, generate, "
                    "edit, run, or delete files, folders, code, or projects, OR if it tells "
                    "you to proceed with such an action (e.g. 'yes do it', 'go ahead', "
                    "'create that', 'start'). "
                    "Reply 'chat' if it is a general question, explanation, or conversation."
                )},
                {"role": "user", "content": user_prompt},
            ],
        )
        intent = IntentFormat.model_validate_json(result.message.content).intent.strip().lower()
        return "task" if intent == "task" else "chat"
    except Exception:
        return "chat"


def runCommand(cmd: str):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        output = result.stdout + result.stderr
        return output.strip() if output.strip() else "Command executed successfully"
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out"
    except Exception as e:
        return f"ERROR: {str(e)}"


def writeFile(args: str):
    try:
        parts = args.split("|||", 1)
        if len(parts) < 2:
            return "ERROR: input must be 'filepath|||content'"
        filepath = parts[0].strip()
        content = parts[1].strip()
        folder = os.path.dirname(filepath)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File '{filepath}' created successfully"
    except Exception as e:
        return f"ERROR: {str(e)}"


def get_weather(city: str):
    response = requests.get(f"https://wttr.in/{city}?format=%C+%t")
    return response.text if response.status_code == 200 else "Sorry, couldn't fetch weather."


Available_Tools = {
    "get_weather": get_weather,
    "runCommand": runCommand,
    "writeFile": writeFile  # ✅ added
}

message_History = [{"role": "system", "content": System_Prompt}]

console.print(
    Panel(
        "[bold]G-Code[/bold] — your local coding & general-purpose assistant\n"
        "[dim]Ask a question or give a task. Type 'exit' or press Ctrl+C to quit.[/dim]",
        border_style="magenta",
        padding=(0, 1),
    )
)

while True:
    try:
        user_Prompt = console.input("\n[bold green]You[/bold green] ")
    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]Goodbye![/dim]")
        break

    if not user_Prompt.strip():
        continue
    if user_Prompt.strip().lower() in ("exit", "quit"):
        console.print("[dim]Goodbye![/dim]")
        break

    message_History.append({"role": "user", "content": user_Prompt})

    with console.status("[dim]Thinking...[/dim]", spinner="dots"):
        require_tool = classify_intent(user_Prompt) == "task"

    tool_was_called = False
    max_retries = 15
    retries = 0

    while retries < max_retries:
        retries += 1

        try:
            with console.status("[dim]Thinking...[/dim]", spinner="dots"):
                response = client.chat(
                    model="qwen2.5:7b",
                    format=MyoutputFormat.model_json_schema(),
                    messages=message_History,
                )
            raw_response = response.message.content
            message_History.append({"role": "assistant", "content": raw_response})
            parsed_response = MyoutputFormat.model_validate_json(raw_response)
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled.[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error talking to the model: {e}[/red]")
            break

        step = parsed_response.step

        if step in ("START", "PLAN"):
            if parsed_response.content.strip():
                console.print(f"[dim]  {parsed_response.content}[/dim]")
            continue

        if step == "TOOL":
            if not parsed_response.input.strip() or not parsed_response.tool_name.strip():
                message_History.append({
                    "role": "assistant",
                    "content": json.dumps({
                        "step": "OBSERVE", "tool_name": "",
                        "output": "ERROR: input was empty. Populate the input field.",
                        "content": "", "input": ""
                    })
                })
                continue

            tool_function = Available_Tools.get(parsed_response.tool_name.strip())
            if not tool_function:
                message_History.append({
                    "role": "assistant",
                    "content": json.dumps({
                        "step": "OBSERVE", "tool_name": parsed_response.tool_name,
                        "output": f"ERROR: Unknown tool '{parsed_response.tool_name}'. Use runCommand, writeFile, or get_weather.",
                        "content": "", "input": ""
                    })
                })
                continue

            console.print(
                f"[cyan]⚙ {parsed_response.tool_name}[/cyan] [dim]{parsed_response.input}[/dim]"
            )
            tool_output = tool_function(parsed_response.input.strip())
            console.print(f"[dim]  ↳ {tool_output}[/dim]")
            tool_was_called = True
            message_History.append({
                "role": "assistant",
                "content": json.dumps({
                    "step": "OBSERVE", "tool_name": parsed_response.tool_name,
                    "output": str(tool_output), "content": "", "input": ""
                })
            })
            continue

        if step == "OUTPUT":
            if require_tool and not tool_was_called:
                message_History.append({
                    "role": "assistant",
                    "content": json.dumps({
                        "step": "OBSERVE", "tool_name": "",
                        "output": "You have NOT finished the task yet and no tool has run. "
                                  "Do NOT ask the user for confirmation. Run the required TOOL "
                                  "steps now (mkdir / writeFile), and only OUTPUT once every "
                                  "folder and file actually exists.",
                        "content": "", "input": ""
                    })
                })
                continue
            console.print()
            console.print(
                Panel(
                    Markdown(parsed_response.content),
                    title="[bold magenta]G-Code[/bold magenta]",
                    title_align="left",
                    border_style="magenta",
                    padding=(1, 2),
                )
            )
            break

    else:
        console.print("[red]Sorry, I couldn't complete that (max steps reached).[/red]")