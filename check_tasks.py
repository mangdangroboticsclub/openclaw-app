#!/usr/bin/env python3
"""Check the status of Phase 2 tasks from the Pi terminal."""
import json
import os

TASKS_DIR = os.path.expanduser("~/minipupper-app/tasks")

if not os.path.isdir(TASKS_DIR):
    print("No tasks directory found.")
    print(f"(expected at: {TASKS_DIR})")
    exit(1)

# Scan all subdirectories
all_tasks = {}
for subdir in ("pending", "active", "completed"):
    d = os.path.join(TASKS_DIR, subdir)
    if not os.path.isdir(d):
        continue
    for fname in sorted(os.listdir(d)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(d, fname)
        try:
            with open(fpath) as f:
                task = json.load(f)
            task["_dir"] = subdir
            tid = task.get("taskId") or fname
            all_tasks[tid] = task
        except Exception:
            pass

if not all_tasks:
    print("No tasks found.")
    exit(0)

for task_id, task in all_tasks.items():
    status = task.get("status", "unknown")
    action = task.get("action", "unknown")
    phase = task.get("phase", "")
    progress = task.get("progress", 0)
    message = task.get("message", "")
    result = task.get("result", "")
    error = task.get("error", "")
    task_dir = task.get("_dir", "?")

    icon = {"running": "🔄", "completed": "✅", "failed": "❌"}.get(status, "❓")
    print(f"{icon} [{task_id[:8]}] {action} ({task_dir})")
    print(f"   Status: {status}")
    if phase:
        print(f"   Phase: {phase}")
    print(f"   Progress: {progress:.0f}%")
    print(f"   Message: {message}")
    if result:
        txt = str(result)
        print(f"   Result: {txt[:200]}")
    if error:
        print(f"   Error: {error[:200]}")
    print()
