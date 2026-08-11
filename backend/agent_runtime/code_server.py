"""MCP server for running code, so an agent can test what it writes.

Without this an agent writes a file, declares it correct, and nobody finds out
otherwise until a human runs it. With it the agent gets the loop that actually
produces working code: write, run, read the traceback, fix, run again.

Runs as a stdio subprocess inside the agent's OWN container, which is what
makes it defensible. The blast radius is one agent's container — the same one
already executing that agent's tool calls — and the working directory is the
same /workspace/files the Filesystem capability uses, so code and the files it
operates on are the same files.

Two deliberate limits, neither of which the container itself would impose:
the subprocess gets a timeout, because a model writing `while True` otherwise
hangs the capability until the agent is redeployed; and it gets an environment
with the agent's own credentials removed, so generated code can't read the
model or capability keys out of os.environ and put them in its output.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

WORK_DIR = Path("/workspace/files")

DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120

# Enough to see a traceback and the tail of a test run, bounded so a runaway
# loop's output can't consume the model's whole context window.
MAX_OUTPUT_CHARS = 6000

# Anything that looks like a credential is withheld from the subprocess. The
# agent runtime still has them — it needs them to call models and tools — but
# code the model just wrote has no business reading them.
_SECRET_PATTERN = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)

mcp = FastMCP("Code Execution")


def _child_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not _SECRET_PATTERN.search(k)}


def _clamp(value: int | None, default: int) -> int:
    try:
        seconds = int(value if value is not None else default)
    except (TypeError, ValueError):
        return default
    return max(1, min(seconds, MAX_TIMEOUT))


def _format(completed: subprocess.CompletedProcess) -> str:
    parts = []
    out = (completed.stdout or "").strip()
    err = (completed.stderr or "").strip()
    if out:
        parts.append(f"stdout:\n{out}")
    if err:
        parts.append(f"stderr:\n{err}")
    if not parts:
        parts.append("(no output)")
    parts.append(f"exit code: {completed.returncode}")
    text = "\n\n".join(parts)
    if len(text) > MAX_OUTPUT_CHARS:
        half = MAX_OUTPUT_CHARS // 2
        text = f"{text[:half]}\n\n… [output truncated] …\n\n{text[-half:]}"
    return text


@mcp.tool()
def run_python(code: str, timeout_seconds: int = DEFAULT_TIMEOUT) -> str:
    """Run Python code and return its output, so you can check it works.

    The code runs in this agent's own workspace, so it can open and write the
    files there by relative path. Use this to test what you write rather than
    assuming it's correct — read the traceback, fix the code, and run it
    again. Print what you want to see; nothing is returned implicitly.
    """
    if not (code or "").strip():
        return "Error: no code to run."
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    # A temp file rather than `python -c`: tracebacks then carry real line
    # numbers, which is the whole point of running it.
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", dir=WORK_DIR, delete=False, encoding="utf-8"
    ) as handle:
        handle.write(code)
        script = Path(handle.name)
    try:
        completed = subprocess.run(
            ["python3", script.name],
            cwd=WORK_DIR,
            env=_child_env(),
            capture_output=True,
            text=True,
            timeout=_clamp(timeout_seconds, DEFAULT_TIMEOUT),
        )
    except subprocess.TimeoutExpired:
        return (
            f"Error: the code was still running after {_clamp(timeout_seconds, DEFAULT_TIMEOUT)}s "
            "and was stopped. Check for an unbounded loop or a call that waits forever."
        )
    finally:
        script.unlink(missing_ok=True)
    return _format(completed)


@mcp.tool()
def run_command(command: str, timeout_seconds: int = DEFAULT_TIMEOUT) -> str:
    """Run a shell command in this agent's workspace and return its output.

    For the things around the code rather than the code itself — running a
    test suite, listing files, installing a package, checking a version.
    Runs from the workspace directory, so relative paths work.
    """
    if not (command or "").strip():
        return "Error: no command to run."
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=WORK_DIR,
            env=_child_env(),
            capture_output=True,
            text=True,
            timeout=_clamp(timeout_seconds, DEFAULT_TIMEOUT),
        )
    except subprocess.TimeoutExpired:
        return (
            f"Error: {command!r} was still running after "
            f"{_clamp(timeout_seconds, DEFAULT_TIMEOUT)}s and was stopped."
        )
    return _format(completed)


if __name__ == "__main__":
    mcp.run(transport="stdio")
