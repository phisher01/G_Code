from pydantic import BaseModel, Field


class MyoutputFormat(BaseModel):
    step: str = Field(..., description="The current step: 'START' | 'PLAN' | 'OUTPUT' | 'OBSERVE' | 'TOOL'")
    content: str = Field(..., description="Explanation or message for this step. Use empty string if not applicable.")
    output: str = Field(..., description="Tool result used in OBSERVE step. Use empty string if not applicable.")
    input: str = Field(..., description="When step is TOOL: exact argument to pass. Use empty string if not applicable.")
    tool_name: str = Field(..., description="When step is TOOL: name of tool. Either 'runCommand', 'writeFile', or 'get_weather'. Use empty string if not applicable.")


class IntentFormat(BaseModel):
    intent: str = Field(..., description="Either 'task' or 'chat'")
