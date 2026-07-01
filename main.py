import json
import subprocess
import os
import requests
from ollama import Client
from pydantic import BaseModel, Field

from openai import OpenAI
client = Client(host="http://localhost:11434")




System_Prompt = """
You are an expert AI assistant resolving user queries using chain of thought prompting.
Do not answer anything other than coding related queries.
You work on START, PLAN, TOOL, OBSERVE and OUTPUT steps.

IMPORTANT RULES:
- You are running on Windows OS
- NEVER use nano, vim, heredoc (<<), or any Linux-only syntax
- To create folders use runCommand with: mkdir foldername
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
"""

class MyoutputFormat(BaseModel):
    step: str = Field(..., description="The current step: 'START' | 'PLAN' | 'OUTPUT' | 'OBSERVE' | 'TOOL'")
    content: str = Field(..., description="Explanation or message for this step. Use empty string if not applicable.")
    output: str = Field(..., description="Tool result used in OBSERVE step. Use empty string if not applicable.")
    input: str = Field(..., description="When step is TOOL: exact argument to pass. Use empty string if not applicable.")
    tool_name: str = Field(..., description="When step is TOOL: name of tool. Either 'runCommand', 'writeFile', or 'get_weather'. Use empty string if not applicable.")


def runCommand(cmd: str):
    print(f"Running command: {cmd}")
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

while True:
    user_Prompt = input("\nYou: ")
    message_History.append({"role": "user", "content": user_Prompt})

    tool_was_called = False
    max_retries = 15
    retries = 0

    while retries < max_retries:
        retries += 1

        response = client.chat(
    model="qwen2.5:7b",
    format=MyoutputFormat.model_json_schema(),
    messages=message_History,
)
        raw_response = response.message.content

        print("RAW RESPONSE:")
        print(raw_response)

        message_History.append({
    "role": "assistant",
    "content": raw_response
})

        parsed_response = MyoutputFormat.model_validate_json(raw_response)

        step = parsed_response.step
        # if step not in ("START", "PLAN", "TOOL", "OBSERVE", "OUTPUT"):
        #     step = "TOOL"

        if step == "START":
            print(f"🚀 Starting...\n💡 {parsed_response.content}")
            continue

        if step == "PLAN":
            print(f"🧠 Planning...\n📋 {parsed_response.content}")
            continue

        if step == "TOOL":
            print(f"🔧 Calling Tool: {parsed_response.tool_name}\n📝 Input: {parsed_response.input}")

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

            tool_output = tool_function(parsed_response.input.strip())
            print(f"📊 Tool Output: {tool_output}")
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
            if not tool_was_called:
                message_History.append({
                    "role": "assistant",
                    "content": json.dumps({
                        "step": "OBSERVE", "tool_name": "",
                        "output": "ERROR: You must call a TOOL before OUTPUT.",
                        "content": "", "input": ""
                    })
                })
                continue
            print(f"✅ Final Output!\n💻 {parsed_response.content}")
            break

    else:
        print("❌ Max retries reached.")