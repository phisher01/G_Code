import json
from ollama import Client
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from prompts import System_Prompt
from schemas import MyoutputFormat, IntentFormat
from tools import Available_Tools


client = Client(host="http://localhost:11434")
console = Console()


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
