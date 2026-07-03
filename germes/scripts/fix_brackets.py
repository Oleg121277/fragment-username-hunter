#!/usr/bin/env python3
"""Check and fix bracket balance in Python files."""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path
from typing import List, Tuple

OPEN = "([{" 
CLOSE = ")]}"
MATCH = dict(zip(CLOSE, OPEN))

def strip_strings_comments(line: str) -> str:
    result, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c == '#': break
        if c in ('"', "'"):
            q = c
            if line[i:i+3] in ('"""', "'''"):
                end = line.find(line[i:i+3], i+3)
                i = end + 3 if end != -1 else n
                continue
            i += 1
            while i < n:
                if line[i] == '\\': i += 2; continue
                if line[i] == q: i += 1; break
                i += 1
            continue
        result.append(c); i += 1
    return ''.join(result)

def check_brackets(content: str) -> List[Tuple[int, str]]:
    errors, stack = [], []
    for lno, line in enumerate(content.splitlines(), 1):
        cleaned = strip_strings_comments(line)
        for ch in cleaned:
            if ch in OPEN: stack.append((ch, lno))
            elif ch in CLOSE:
                exp = MATCH[ch]
                if not stack:
                    errors.append((lno, f"Extra closing '{ch}'"))
                elif stack[-1][0] != exp:
                    errors.append((lno, f"Expected '{stack[-1][0]}' (line {stack[-1][1]}), got '{ch}'"))
                    found = False
                    for idx in range(len(stack)-1, -1, -1):
                        if stack[idx][0] == exp:
                            for j in range(len(stack)-1, idx, -1):
                                uc, ul = stack[j]
                                errors.append((ul, f"Unclosed '{uc}'"))
                            stack = stack[:idx]; found = True; break
                    if not found: stack.clear()
                else: stack.pop()
    for char, lno in stack:
        errors.append((lno, f"Unclosed '{char}'"))
    return errors

def fix_brackets(content: str) -> tuple[str, list[str]]:
    fixes, lines = [], content.splitlines(keepends=True)
    new_lines = []
    for i, line in enumerate(lines):
        stripped = line.rstrip('\n\r')
        cleaned = strip_strings_comments(stripped)
        opens = sum(1 for c in cleaned if c in OPEN)
        closes = sum(1 for c in cleaned if c in CLOSE)
        if closes > opens and stripped:
            trailing, j = '', len(stripped) - 1
            while j >= 0 and stripped[j] in CLOSE + ' \t':
                if stripped[j] in CLOSE: trailing = stripped[j] + trailing
                j -= 1
            excess = closes - opens
            if len(trailing) >= excess:
                old = stripped
                stripped = stripped[:j+1] + trailing[excess:]
                if old != stripped:
                    fixes.append(f"Line {i+1}: removed {excess} extra closing bracket(s)")
        new_lines.append(stripped + '\n')
    result = ''.join(new_lines)
    errs = check_brackets(result)
    unclosed = [e for e in errs if 'Unclosed' in e[1]]
    if unclosed:
        close_map = {'(': ')', '[': ']', '{': '}'}
        missing = ''.join(close_map.get(e[1].split("'")[1], '') for _, e in reversed(unclosed))
        if missing:
            result = result.rstrip() + '\n' + missing + '\n'
            fixes.append(f"Added missing closing brackets: {missing}")
    return result, fixes

def process_file(path: Path, do_fix=False, verbose=False) -> bool:
    try: content = path.read_text(encoding='utf-8')
    except Exception as e: print(f"  ERR {path}: {e}"); return False
    errors = check_brackets(content)
    if not errors:
        if verbose: print(f"  OK: {path}")
        return False
    print(f"  ISSUES in {path} ({len(errors)}):")
    for lno, msg in errors: print(f"    L{lno}: {msg}")
    if do_fix:
        fixed, applied = fix_brackets(content)
        if applied:
            path.write_text(fixed, encoding='utf-8')
            print(f"  FIXED ({len(applied)}):")
            for f in applied: print(f"    - {f}")
            rem = check_brackets(fixed)
            print(f"  VERIFIED" if not rem else f"  WARNING: {len(rem)} remain")
        else: print("  NO AUTO-FIX")
    return True

def main():
    p = argparse.ArgumentParser(description="Bracket checker/fixer")
    p.add_argument("target")
    p.add_argument("--fix", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    t = Path(args.target)
    files = [t] if t.is_file() else sorted(
        f for f in t.rglob("*.py")
        if '.venv' not in str(f) and '__pycache__' not in str(f)
    )
    print(f"Scanning {len(files)} file(s)...")
    bad = sum(process_file(f, args.fix, args.verbose) for f in files)
    print(f"\n{'ALL OK' if bad == 0 else f'{bad} file(s) with issues'}")
    sys.exit(1 if bad > 0 and not args.fix else 0)

if __name__ == "__main__":
    main()
