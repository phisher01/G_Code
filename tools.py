import subprocess
import os
import requests


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
