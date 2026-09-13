"""List recent LangSmith traces for the Disha project.

    cd backend
    python -m evals.traces                 # last 24h
    python -m evals.traces --hours 2 --run-type LLM --limit 20

Uses the current `client.runs.query()` API. The older `client.list_runs()` is deprecated (LangSmith
flags it as legacy API usage). `runs.query_v2` is the same contract as `runs.query` in langsmith 0.9.2 —
identical parameters and docstring — so there is nothing further to move to. Both are marked Alpha:
query() takes project_ids (not project_name, so the name is resolved first), min_start_time /
max_start_time, uppercase run_type and `selects`, and returns only `id` unless fields are selected.
See https://docs.langchain.com/langsmith/smithdb-sdk-migration-query-runs
"""
import argparse
import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

SELECTS = ["ID", "NAME", "STATUS", "RUN_TYPE", "START_TIME", "ERROR"]


def _collect(result, limit):
    """query() may hand back a sync paginator or an async iterator depending on SDK version."""
    if hasattr(result, "__aiter__"):
        async def drain():
            out = []
            async for run in result:
                out.append(run)
                if len(out) >= limit:
                    break
            return out
        return asyncio.run(drain())
    out = []
    for run in result:
        out.append(run)
        if len(out) >= limit:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--run-type", help="LLM, CHAIN, TOOL … (uppercase)")
    args = ap.parse_args()

    if not os.environ.get("LANGSMITH_API_KEY"):
        raise SystemExit("No LANGSMITH_API_KEY in backend/.env")

    from langsmith import Client
    client = Client()
    project_name = os.environ.get("LANGSMITH_PROJECT", "default")

    # query() takes ids, never names. read_project is the only name->id lookup (there is no
    # `client.projects` resource and no aread_project), and it is one of the older-style calls —
    # so set LANGSMITH_PROJECT_ID in backend/.env to skip it entirely.
    project_id = os.environ.get("LANGSMITH_PROJECT_ID")
    if not project_id:
        project_id = str(client.read_project(project_name=project_name).id)
        print(f"  resolved '{project_name}' -> {project_id}  (put LANGSMITH_PROJECT_ID in .env to skip this lookup)")

    params = {"project_ids": [project_id],
              "min_start_time": datetime.now(timezone.utc) - timedelta(hours=args.hours),
              "selects": SELECTS,
              "page_size": min(args.limit, 1000)}
    if args.run_type:
        params["run_type"] = args.run_type.upper()

    try:
        runs = _collect(client.runs.query(**params), args.limit)
    except TypeError as e:  # a field this SDK build doesn't accept - retry with the essentials
        print(f"  (retrying without optional fields: {e})")
        runs = _collect(client.runs.query(project_ids=[str(project.id)],
                                          min_start_time=params["min_start_time"]), args.limit)

    print(f"{len(runs)} run(s) in '{project_name}' over the last {args.hours:g}h")
    for run in runs:
        started = getattr(run, "start_time", None)
        stamp = started.strftime("%Y-%m-%d %H:%M:%S") if hasattr(started, "strftime") else str(started)
        flag = " ERROR" if getattr(run, "error", None) else ""
        print(f"  {stamp}  {str(getattr(run, 'run_type', '?')):8} {str(getattr(run, 'name', '?'))[:40]:40}"
              f" {str(getattr(run, 'status', '?')):10}{flag}")


if __name__ == "__main__":
    main()
