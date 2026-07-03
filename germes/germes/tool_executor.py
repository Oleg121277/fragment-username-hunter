"""Tool Executor - parses and executes tool_calls from Hermes responses."""
from __future__ import annotations

import json
import logging
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("germes.tool_executor")


def extract_tool_calls(text: str) -> List[Dict[str, Any]]:
    """Extract tool_calls from Hermes response text."""
    calls = []
    patterns = [
        r'''```json\s*(\{.*?\})\s*```''',
        r'''```\s*(\{.*?\})\s*```''',
        r'(\{"tool_calls":\s*\[.*?\]\})',
        r'(\{"tool":\s*"[^"]+".*?\})',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match)
                if "tool_calls" in data and isinstance(data["tool_calls"], list):
                    for tc in data["tool_calls"]:
                        if isinstance(tc, dict):
                            name = tc.get("name") or tc.get("function", {}).get("name", "")
                            args = tc.get("arguments") or tc.get("function", {}).get("arguments", {})
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except json.JSONDecodeError:
                                    args = {}
                            if name:
                                calls.append({"name": name, "arguments": args})
                elif "tool" in data:
                    name = data["tool"]
                    args = data.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    calls.append({"name": name, "arguments": args})
            except json.JSONDecodeError:
                continue
    return calls


def execute_terminal(command: str, timeout: int = 60, workdir: Optional[str] = None) -> Dict[str, Any]:
    log.info("EXEC: %s", command[:200])
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace", cwd=workdir)
        output = (result.stdout or "") + (result.stderr or "")
        return {"output": output.strip(), "exit_code": result.returncode, "error": None}
    except subprocess.TimeoutExpired:
        return {"output": "", "exit_code": -1, "error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"output": "", "exit_code": -1, "error": str(e)}


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    log.info("Tool call: %s(%s)", name, list(arguments.keys()))
    if name == "terminal":
        return execute_terminal(arguments.get("command", ""), arguments.get("timeout", 60), arguments.get("workdir"))
    elif name == "read_file":
        try:
            with open(arguments.get("path", ""), "r", encoding="utf-8") as f:
                return {"output": f.read(), "exit_code": 0, "error": None}
        except Exception as e:
            return {"output": "", "exit_code": 1, "error": str(e)}
    elif name == "write_file":
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"output": f"Written {len(content)} bytes to {path}", "exit_code": 0, "error": None}
        except Exception as e:
            return {"output": "", "exit_code": 1, "error": str(e)}
    else:
        return {"output": "", "exit_code": 1, "error": f"Unknown tool: {name}"}


def process_response(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Process Hermes response: extract and execute tool_calls.
    Returns: (cleaned_text, execution_results)
    """
    tool_calls = extract_tool_calls(text)
    if not tool_calls:
        return text, []
    log.info("Found %d tool_call(s) in response", len(tool_calls))
    results = []
    for tc in tool_calls:
        result = execute_tool(tc["name"], tc["arguments"])
        results.append({"tool": tc["name"], "arguments": tc["arguments"], "result": result})
        log.info("Result [%s]: exit=%s", tc["name"], result["exit_code"])
    cleaned = text
    clean_patterns = [
        r'```json\s*\{.*?\}\s*```',
        r'```\s*\{.*?\}\s*```',
        r'\{"tool_calls":\s*\[.*?\]\}',
        r'\{"tool":\s*"[^"]+".*?\}',
    ]
    for pattern in clean_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned, results
