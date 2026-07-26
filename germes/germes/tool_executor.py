"""Tool Executor - parses and executes tool_calls from Hermes responses.
Includes robust JSON auto-repair to prevent agent crashes on malformed LLM output."""
from __future__ import annotations

import json
import logging
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("germes.tool_executor")


def _try_fix_json(raw: str) -> Optional[Any]:
    """Attempt to repair common JSON malformations from LLM output.
    Returns parsed object (dict/list) on success, None on failure.
    
    Repair strategies applied in order:
    1. Parse as-is
    2. Strip trailing commas before } or ]
    3. Replace single quotes with double quotes
    4. Wrap unquoted keys: {key: "val"} -> {"key": "val"}
    5. Truncate at last balanced brace/bracket
    6. Extract first {...} or [...] substring and retry
    """
    if not raw or not raw.strip():
        return None
    
    # 1. Try as-is
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # 2. Strip trailing commas before } or ]
    fixed = re.sub(r',\s*([}\]])', r'\1', raw)
    try:
        return json.loads(fixed)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # 3. Replace single quotes with double quotes
    # Always try this — LLMs frequently output {'key': 'val'} format
    fixed2 = fixed.replace("'", '"')
    try:
        return json.loads(fixed2)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # 4. Wrap unquoted keys: {key: "val"} -> {"key": "val"}
    fixed3 = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', fixed2)
    try:
        return json.loads(fixed3)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # 5. Truncate at last balanced brace/bracket
    for end_ch in ('}', ']'):
        idx = raw.rfind(end_ch)
        if idx > 0:
            candidate = raw[:idx+1]
            # Find matching opening bracket
            open_ch = '{' if end_ch == '}' else '['
            start_idx = candidate.rfind(open_ch)
            if start_idx >= 0:
                sub = candidate[start_idx:]
                try:
                    return json.loads(sub)
                except (json.JSONDecodeError, ValueError):
                    continue
    
    # 6. Try to find any JSON object/array in the string
    for pattern in [r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', r'\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]']:
        m = re.search(pattern, raw)
        if m:
            try:
                return json.loads(m.group())
            except (json.JSONDecodeError, ValueError):
                continue
    
    log.warning("JSON repair failed for snippet: %s", raw[:300])
    return None


def extract_tool_calls(text: str) -> List[Dict[str, Any]]:
    """Extract tool_calls from Hermes response text with auto-repair.
    
    Handles multiple formats:
    - ```json {...} ``` blocks
    - Raw {"tool_calls": [...]} objects
    - Raw {"tool": "name", ...} objects
    - Malformed JSON (trailing commas, single quotes, unquoted keys)
    """
    calls = []
    seen = set()  # Deduplicate by (name, args_str)
    
    patterns = [
        r'```json\s*(\{.*?\})\s*```',
        r'```\s*(\{.*?\})\s*```',
        r'(\{"tool_calls":\s*\[.*?\]\})',
        r'(\{"tool":\s*"[^"]+".*?\})',
        # Fallback: capture any {...} block (will be repaired by _try_fix_json)
        r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            data = _try_fix_json(match)
            if data is None:
                continue
            
            if isinstance(data, dict):
                if "tool_calls" in data and isinstance(data["tool_calls"], list):
                    for tc in data["tool_calls"]:
                        if isinstance(tc, dict):
                            name = tc.get("name") or tc.get("function", {}).get("name", "")
                            args = tc.get("arguments") or tc.get("function", {}).get("arguments", {})
                            if isinstance(args, str):
                                repaired = _try_fix_json(args)
                                args = repaired if repaired is not None else {}
                            if name:
                                key = (name, json.dumps(args, sort_keys=True, default=str))
                                if key not in seen:
                                    seen.add(key)
                                    calls.append({"name": name, "arguments": args})
                elif "tool" in data:
                    name = data["tool"]
                    args = data.get("arguments", {})
                    if isinstance(args, str):
                        repaired = _try_fix_json(args)
                        args = repaired if repaired is not None else {}
                    key = (name, json.dumps(args, sort_keys=True, default=str))
                    if key not in seen:
                        seen.add(key)
                        calls.append({"name": name, "arguments": args})
                elif "name" in data:
                    # Direct tool call format: {"name": "terminal", "arguments": {...}}
                    name = data["name"]
                    args = data.get("arguments", {})
                    if isinstance(args, str):
                        repaired = _try_fix_json(args)
                        args = repaired if repaired is not None else {}
                    key = (name, json.dumps(args, sort_keys=True, default=str))
                    if key not in seen:
                        seen.add(key)
                        calls.append({"name": name, "arguments": args})
    
    return calls


def execute_terminal(command: str, timeout: int = 60, workdir: Optional[str] = None) -> Dict[str, Any]:
    log.info("EXEC: %s", command[:200])
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            cwd=workdir
        )
        output = (result.stdout or "") + (result.stderr or "")
        return {"output": output.strip(), "exit_code": result.returncode, "error": None}
    except subprocess.TimeoutExpired:
        return {"output": "", "exit_code": -1, "error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"output": "", "exit_code": -1, "error": str(e)}


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    log.info("Tool call: %s(%s)", name, list(arguments.keys()))
    if name == "terminal":
        return execute_terminal(
            arguments.get("command", ""),
            arguments.get("timeout", 60),
            arguments.get("workdir")
        )
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
        try:
            result = execute_tool(tc["name"], tc["arguments"])
        except Exception as e:
            log.error("Tool execution crashed: %s — %s", tc["name"], e)
            result = {"output": "", "exit_code": -1, "error": str(e)}
        results.append({"tool": tc["name"], "arguments": tc["arguments"], "result": result})
        log.info("Result [%s]: exit=%s", tc["name"], result["exit_code"])
    
    cleaned = text
    clean_patterns = [
        r'```json\s*\{.*?\}\s*```',
        r'```\s*\{.*?\}\s*```',
        r'\{"tool_calls":\s*\[.*?\]\}',
        r'\{"tool":\s*"[^"]+".*?\}',
        r'\{"name":\s*"[^"]+".*?\}',
    ]
    for pattern in clean_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned, results
