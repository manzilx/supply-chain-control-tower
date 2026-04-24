#!/usr/bin/env python3
"""Extract a human-readable markdown chat log from a Claude Code session jsonl.

Keeps user text + assistant text; summarizes tool use as one-liners so the log
stays readable and well under repo-size sanity. Run with:

    python3 extract_chat.py <session.jsonl> <out.md>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def render_content(content):
    """Turn a content array (or string) into markdown, skipping tool_result text."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            text = block.get("text", "").strip()
            if text:
                parts.append(text)
        elif btype == "tool_use":
            name = block.get("name", "?")
            tool_input = block.get("input", {})
            # one-line summary of the tool call
            preview = json.dumps(tool_input, default=str)
            if len(preview) > 160:
                preview = preview[:157] + "..."
            parts.append(f"_[tool: {name}({preview})]_")
        elif btype == "tool_result":
            # suppress tool outputs — they explode size and are reproducible from code
            continue
        elif btype == "image":
            parts.append("_[image]_")
    return "\n\n".join(p for p in parts if p)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: extract_chat.py <session.jsonl> <out.md>", file=sys.stderr)
        sys.exit(1)

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    out_lines: list[str] = [
        f"# Chat log — {src.stem}",
        "",
        f"Extracted from Claude Code session `{src.name}`. Tool outputs omitted; tool calls shown as one-liners. For the full raw transcript see the session backup referenced in README.",
        "",
    ]

    user_count = 0
    assistant_count = 0
    with src.open("r", encoding="utf-8") as f:
        for raw in f:
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if d.get("type") not in {"user", "assistant"}:
                continue
            msg = d.get("message", {})
            role = msg.get("role")
            content = msg.get("content")
            body = render_content(content)
            if not body:
                continue
            if role == "user":
                user_count += 1
                out_lines.append(f"## 👤 User — turn {user_count}")
                out_lines.append("")
                out_lines.append(body)
                out_lines.append("")
            elif role == "assistant":
                assistant_count += 1
                out_lines.append(f"## 🤖 Assistant — turn {assistant_count}")
                out_lines.append("")
                out_lines.append(body)
                out_lines.append("")

    dst.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"Wrote {dst} — {user_count} user turns, {assistant_count} assistant turns, {dst.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
