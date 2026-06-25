"""
Minipupper Phase 2 - Task File Watcher

Watches ~/minipupper-app/tasks.json for completed tasks from the OpenClaw agent.
When a task completes, injects the result into Gemini's conversation so it
can generate a natural TTS announcement for the user.

This replaces the complex session-based protocol with a simple shared file.

Protocol: The file at ~/minipupper-app/tasks.json is the shared task file.
- App writes tasks with status="pending"
- Agent updates status to "running" -> "completed" or "failed"
- This watcher detects completed tasks and triggers TTS
"""

import json
import logging
import os
import threading
import time
import uuid
from typing import Optional, List

from src.core.task_archiver import TaskArchiver

logger = logging.getLogger(__name__)

TASKS_FILE = os.path.expanduser("~/minipupper-app/tasks.json")
TASKS_DIR = os.path.expanduser("~/minipupper-app/tasks")
POLL_INTERVAL = 2.0  # Check file every 2 seconds


class TaskWatcher:
    def __init__(self, llm, audio_manager, announce_llm=None, on_result=None):
        self._task_display = None
        # Try to initialize the ST7789 LCD display for task status
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.expanduser("~/minipupper-app/scripts"))
            from display_task_info import TaskDisplay
            self._task_display = TaskDisplay()
        except Exception:
            pass
        self.announce_llm = announce_llm or llm  # dedicated LLM for announcements
        self.audio_manager = audio_manager
        self.archiver = TaskArchiver()
        self._on_result = on_result
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Track which task's progress announcement is being made (for interruption context)
        self._announcing_progress_task_id: Optional[str] = None
        self._announcing_progress_message: Optional[str] = None

    def start(self):
        # Archive any old completed tasks from previous sessions
        self._archive_old_completed()

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="TaskWatcher")
        self._thread.start()
        logger.info("TaskWatcher started (polling %s every %.1fs)",
                     TASKS_FILE, POLL_INTERVAL)

    def _archive_old_completed(self):
        """Archive stale tasks from previous app sessions silently.

        Iterates tasks in memory, archives each to disk, then removes
        from the active file. The active file is rewritten once at the end
        with only non-archivable tasks remaining.

        Handles:
        - completed/failed tasks (previous sessions)
        - pending/running/feedback_required/processing tasks (app crashed mid-task or unconfirmed)
        """
        tasks = self._load_tasks()
        if not tasks:
            return

        kept = {}
        for task_id, task in tasks.items():
            status = task.get("status", "")
            if status in ("completed", "failed"):
                task["announced"] = True
                try:
                    self.archiver.archive_task(task)
                    logger.info("TaskWatcher: archived stale %s task %s (%s) on startup",
                               status, task_id[:8], task.get("action", "?"))
                except Exception:
                    kept[task_id] = task
            elif status in ("pending", "running", "feedback_required", "processing"):
                task["status"] = "archived"
                task["announced"] = True
                try:
                    self.archiver.archive_task(task)
                    logger.info("TaskWatcher: archived stale %s task %s (%s) on startup",
                               status, task_id[:8], task.get("action", "?"))
                except Exception:
                    kept[task_id] = task
            else:
                kept[task_id] = task

        # Rewrite active file with only non-archived tasks
        self._save_tasks(kept)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _load_tasks(self) -> dict:
        """Scan tasks/ subdirectories for individual task files.
        
        Precedence: pending over active over completed.
        Skips archived dir (only for archival storage).
        Also falls back to legacy tasks.json if new format is empty.
        """
        tasks = {}
        for subdir in ("pending", "active", "completed"):
            d = os.path.join(TASKS_DIR, subdir)
            if not os.path.isdir(d):
                continue
            try:
                for fname in sorted(os.listdir(d)):
                    if not fname.endswith(".json"):
                        continue
                    fpath = os.path.join(d, fname)
                    try:
                        with open(fpath) as f:
                            task = json.load(f)
                        tid = task.get("taskId")
                        if tid:
                            # Completed + announced is still interesting (for cleanup)
                            tasks[tid] = task
                    except (json.JSONDecodeError, OSError):
                        pass
            except OSError:
                pass

        # Normalize: LLM sometimes invents statuses like "pending_feedback"
        for task in tasks.values():
            result = task.get("result")
            if isinstance(result, dict) and result.get("feedback_required"):
                task["status"] = "completed"

        # Fallback to legacy tasks.json if no individual files found
        if not tasks and os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE) as f:
                    data = json.load(f)
                if isinstance(data, dict) and "tasks" in data:
                    return data["tasks"]
                if isinstance(data, dict):
                    for task in data.values():
                        result = task.get("result")
                        if isinstance(result, dict) and result.get("feedback_required"):
                            task["status"] = "completed"
                    return data
            except (json.JSONDecodeError, OSError):
                pass

        return tasks

    def _save_tasks(self, tasks: dict):
        """Write individual task files into tasks/*/ subdirectories.
        
        Each task is written to the file corresponding to its status:
          pending → tasks/pending/{taskId}.json
          active/running/processing → tasks/active/{taskId}.json
          completed/failed → tasks/completed/{taskId}.json
          
        Tasks with unknown status are skipped.
        Tasks in the dict that already have correct files are updated in place.
        """
        dirs = {
            "pending": os.path.join(TASKS_DIR, "pending"),
            "active": os.path.join(TASKS_DIR, "active"),
            "running": os.path.join(TASKS_DIR, "active"),
            "processing": os.path.join(TASKS_DIR, "active"),
            "completed": os.path.join(TASKS_DIR, "completed"),
            "failed": os.path.join(TASKS_DIR, "completed"),
        }
        for tid, task in tasks.items():
            status = task.get("status", "")
            d = dirs.get(status)
            if not d:
                continue
            # Remove stale file from any other status dir
            for other_dir in set(dirs.values()):
                other_path = os.path.join(other_dir, f"{tid}.json")
                if other_path != os.path.join(d, f"{tid}.json"):
                    try:
                        os.remove(other_path)
                    except OSError:
                        pass
            # Write to correct dir
            path = os.path.join(d, f"{tid}.json")
            os.makedirs(d, exist_ok=True)
            with open(path, "w") as f:
                json.dump(task, f, indent=2)

    def write_task(self, task_data: dict):
        """Write a new pending task to the file."""
        task_ids = self.write_tasks([task_data])
        return task_ids[0] if task_ids else None

    def write_tasks(self, task_items: List[dict]) -> List[str]:
        """Write one or more new pending tasks as individual files."""
        if not task_items:
            return []

        task_ids: List[str] = []
        with self._lock:
            for task_data in task_items:
                task_id = task_data.get("taskId") or f"task-{uuid.uuid4().hex[:12]}"
                task = {
                    "taskId": task_id,
                    "action": task_data.get("action", ""),
                    "params": task_data.get("params", {}),
                    "userQuery": task_data.get("userQuery", ""),
                    "status": "pending",
                    "phase": "queued",
                    "progress": 0,
                    "message": "Waiting for agent...",
                    "result": None,
                    "error": None,
                    "announced": False,
                    "createdAt": time.time(),
                    "updatedAt": time.time(),
                }
                path = os.path.join(TASKS_DIR, "pending", f"{task_id}.json")
                os.makedirs(os.path.join(TASKS_DIR, "pending"), exist_ok=True)
                with open(path, "w") as f:
                    json.dump(task, f, indent=2)
                task_ids.append(task_id)

        if len(task_ids) == 1:
            logger.info("TaskWatcher: wrote pending task %s (%s)",
                        task_ids[0][:8], task_items[0].get("action"))
        else:
            logger.info("TaskWatcher: wrote %d pending tasks %s",
                        len(task_ids), ", ".join(task_id[:8] for task_id in task_ids))
        return task_ids

    def _announce_progress(self, task: dict):
        """Announce a progress update using the dedicated announce LLM."""
        # Skip TTS if music is playing (dance audio, etc.)
        if os.path.exists("/tmp/minipupper_dance_active") or os.path.exists("/tmp/minipupper_music_active"):
            return
        phase = task.get("phase", "")
        progress = task.get("progress", 0)
        message = task.get("message", "")
        action = task.get("action", "")
        task_id = task.get("taskId", "")

        # Remember what we're about to announce (for interruption context later)
        self._announcing_progress_task_id = task_id
        self._announcing_progress_message = message or f"{action} progress at {progress:.0f}%"

        # Generate announcement using the dedicated announce LLM
        announcement = message if message and len(message) > 3 else f"{action.replace('_', ' ')}: {progress:.0f}% done"

        logger.info("TaskWatcher: announcing progress: %s", announcement[:100])
        if self.audio_manager:
            try:
                completed = self.audio_manager.speak(announcement)
            except Exception as e:
                logger.error("TaskWatcher: TTS error: %s", e)

        # Clear tracking after announcement finishes (or was interrupted)
        if self._announcing_progress_task_id == task_id:
            self._announcing_progress_task_id = None
            self._announcing_progress_message = None

    def _announce_result(self, task: dict):
        """Announce task result — interrupts progress, uses LLM, gated on TTS.

        - Interrupts any in-progress speech immediately
        - If a progress announcement for this same task was interrupted,
          tells the LLM about the interruption context
        - Only marks announced=True after TTS successfully completes
        """
        action = task.get("action", "unknown")
        result = task.get("result", "")
        error = task.get("error")
        user_query = task.get("userQuery", "")
        task_id = task.get("taskId", "unknown")

        # ── 1. INTERRUPT any in-progress speech ──────────────────
        progress_was_interrupted = False
        interrupted_message = ""
        was_playing = False
        if self.audio_manager:
            try:
                was_playing = True
                self.audio_manager.interrupt_speech()
                import time as _t
                _t.sleep(0.05)  # tiny settle for audio pipeline
            except Exception:
                was_playing = False

        # ── 2. Check if we were just announcing progress for this task ──
        if (self._announcing_progress_task_id == task_id
                and self._announcing_progress_message):
            progress_was_interrupted = True
            interrupted_message = self._announcing_progress_message
            logger.info("TaskWatcher: progress for %s was interrupted by result",
                        task_id[:8])

        self._announcing_progress_task_id = None
        self._announcing_progress_message = None

        # ── 3. GENERATE announcement text (own LLM, no thread contention) ──
        # Normalize result to string for LLM prompt building
        if isinstance(result, dict) or isinstance(result, list):
            result_str = json.dumps(result, indent=2)
        else:
            result_str = str(result) if result is not None else ""

        if error:
            # Short path: don't bother LLM for errors
            announcement = f"Sorry, there was an error: {error}"
        else:
            # Build LLM prompt with interruption context if available
            prompt_parts = []
            if progress_was_interrupted:
                prompt_parts.append(
                    "The previous progress announcement was interrupted "
                    "because the task completed. "
                    "Progress that was interrupted: '" + interrupted_message + "'"
                )
            if action in ("web_search", "web_fetch", "query", "food.analyze"):
                action_label = action.replace('_', ' ')
                prompt_parts.append(
                    "The task was: " + action_label + ". "
                    "The user asked about: '" + user_query + "'. "
                    "Result: " + result_str + ". "
                    "Summarize briefly and naturally in 1-2 sentences."
                )
            else:
                action_label = action.replace("_", " ").replace("robot", "").strip()
                prompt_parts.append(
                    "The task '" + action_label + "' completed. "
                    + ("Result: " + result_str if result_str else "")
                )

            prompt = "\n".join(prompt_parts)

            try:
                from src.core.llm_engine import Message
                messages = [
                    Message(role="system", content=(
                        "You are a concise status announcer for a robot assistant. "
                        "Keep responses under 2 sentences. Sound natural and helpful. "
                        "Speak as if you are the robot itself."
                    )),
                    Message(role="user", content=prompt),
                ]
                announcement = self.announce_llm.generate_response(
                    messages=messages, max_tokens=100
                )
            except Exception as e:
                logger.warning("TaskWatcher: LLM announcement failed: %s", e)
                announcement = result_str if result_str else f"{action.replace('_', ' ')} completed."

        logger.info("TaskWatcher: announcing result: %s", announcement[:200])

        # ── 4. Mark announced NOW so poll loop never re-enters ──
        self._mark_announced(task_id)

        # ── 5. SPEAK via TTS ──────────────────────────────────────
        tts_succeeded = False
        if self.audio_manager:
            try:
                completed = self.audio_manager.speak(announcement)
                if completed:
                    tts_succeeded = True
                else:
                    logger.info("TaskWatcher: result interrupted by user")
            except Exception as e:
                logger.error("TaskWatcher: TTS error: %s", e)

        # ── 6. Always inject result into Gemini's history ───────────
        # (even if interrupted — user may ask about it later)
        if self._on_result:
            try:
                self._on_result(task)
            except Exception as _e:
                logger.warning("TaskWatcher: on_result callback failed: %s", _e)

        # ── 7. Archive only if TTS completed successfully ─────────
        if tts_succeeded:
            logger.info("TaskWatcher: archiving and removing task %s", task_id[:8])
            try:
                self.archiver.archive_task(task)
                self.archiver.remove_task_from_active(task_id)
            except Exception as e:
                logger.warning("TaskWatcher: archive/remove failed: %s", e)
        else:
            logger.info(
                "TaskWatcher: announced already set, will be cleaned up later")

    def _mark_announced(self, task_id: str):
        """Set announced=True on a completed task so cron cleanup can archive it."""
        tasks = self._load_tasks()
        if task_id in tasks:
            tasks[task_id]["announced"] = True
            tasks[task_id]["updatedAt"] = time.time()
            self._save_tasks(tasks)
            logger.info("TaskWatcher: marked task %s as announced", task_id[:8])
        # Sync: remove this task from legacy tasks.json to prevent
        # fallback re-announce loops when per-file is later archived.
        self._sync_remove_from_legacy(task_id)

    def _sync_remove_from_legacy(self, task_id: str):
        """Remove a task from the legacy tasks.json after per-file processing."""
        import os as _os
        legacy = _os.path.expanduser("~/minipupper-app/tasks.json")
        if not _os.path.exists(legacy):
            return
        try:
            with open(legacy) as f:
                data = json.load(f)
            changed = False
            if isinstance(data, dict):
                if "tasks" in data and task_id in data["tasks"]:
                    del data["tasks"][task_id]
                    changed = True
                elif task_id in data:
                    del data[task_id]
                    changed = True
            if changed:
                data["updatedAt"] = time.time()
                with open(legacy, 'w') as f:
                    json.dump(data, f, indent=2)
                logger.info("TaskWatcher: cleaned task %s from legacy tasks.json", task_id[:8])
        except (json.JSONDecodeError, OSError):
            pass

    def _update_display(self, tasks: dict):
        """Update the LCD display with the most interesting task state."""
        if not self._task_display:
            return

        try:
            import time as _t
            # Find the most interesting task: running > pending > completed > idle
            display_task = None
            priority = -1
            for tid, task in tasks.items():
                s = task.get("status", "")
                p = {"running": 3, "processing": 3, "pending": 2, "completed": 1, "failed": 1}.get(s, 0)
                if p > priority:
                    priority = p
                    display_task = task

            if display_task and priority > 0:
                self._task_display.show_task(
                    action=display_task.get("action", ""),
                    status=display_task.get("status", "idle"),
                    phase=display_task.get("phase", ""),
                    progress=display_task.get("progress", 0),
                    message=display_task.get("message", ""),
                    time_str=_t.strftime("%H:%M"),
                )
            else:
                self._task_display.show_idle()
        except Exception:
            pass  # Don't crash if display fails

    def _rebuild_index(self):
        """Rebuild tasks.json as a read-only snapshot from individual files."""
        try:
            all_tasks = self._load_tasks()
            index_path = os.path.expanduser("~/minipupper-app/tasks.json")
            with open(index_path, "w") as f:
                json.dump({"tasks": all_tasks, "updatedAt": time.time()}, f, indent=2)
        except Exception:
            pass  # Best-effort, never critical

    def _run(self):
        # Track last announced progress per task
        _last_announced: dict = {}
        while not self._stop.is_set():
            try:
                tasks = self._load_tasks()
                # Update LCD display with current task state
                self._update_display(tasks)
                # Snapshot tasks.json BEFORE processing completed tasks (archiving deletes files)
                self._rebuild_index()
                for task_id, task in tasks.items():
                    status = task.get("status", "")
                    prev = _last_announced.get(task_id, {})

                    # Completed/failed tasks: only announce if not already announced
                    if status in ("completed", "failed") and not task.get("announced"):
                        logger.info("TaskWatcher: detected completed task %s",
                                     task_id[:8])
                        self._announce_result(task)

                    # Progress updates: only announce meaningful changes
                    elif status == "running":
                        cur_progress = task.get("progress", 0)
                        cur_phase = task.get("phase", "")
                        cur_msg = task.get("message", "")
                        prev_progress = prev.get("progress", -1)
                        prev_phase = prev.get("phase", "")
                        prev_msg = prev.get("message", "")

                        # Announce if phase changed, progress jumped 20%+, or message changed significantly
                        progress_jump = cur_progress - prev_progress >= 20
                        phase_changed = cur_phase and cur_phase != prev_phase
                        msg_changed = cur_msg and cur_msg != prev_msg and len(cur_msg) > 3

                        if progress_jump or phase_changed or msg_changed:
                            _last_announced[task_id] = task
                            logger.info("TaskWatcher: progress update for %s: %s %.0f%% - %s",
                                         task_id[:8], cur_phase, cur_progress, cur_msg[:50])
                            self._announce_progress(task)

                time.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.warning("TaskWatcher: error in poll loop: %s", e)
                time.sleep(POLL_INTERVAL)