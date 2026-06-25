"""
Minipupper Operator - Main Application
Autonomous Operator role with robust capabilities
Last Updated: 2026-05-10
"""

import json
import logging
import os
import sys
import yaml
import threading
from pathlib import Path
from typing import Dict, Any, Optional
import time
import re
import subprocess
import glob
import argparse

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from src.core.task_queue import (
    input_text_queue, output_text_queue,
    speech_active, movement_queue, status_queue, control_queue
)
from src.core.task_queue import openclaw_queue
from src.audio.audio_manager import AudioManager, AudioConfig
from src.audio.barge_in_detector import BargeInConfig
from src.core.llm_engine import create_llm_provider, Message
from src.core.task_watcher import TaskWatcher
from src.openclaw.client import OpenClawClient, load_device_identity
from src.core.task_archiver import TaskArchiver

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MinipupperOperator:
    """
    Main operator for Minipupper robot.
    
    Responsibilities:
    - Conversational interaction with user
    - Direct robot control (no OpenClaw dependency)
    - Audio I/O with barge-in support
    - Task execution and movement
    """
    
    def __init__(self, config_path: str = "config/config.yaml", keyboard: bool = False, mute: bool = False):
        """
        Initialize operator.
        
        Args:
            config_path: Path to configuration YAML file
        """
        self.logger = logger

        self._load_environment(config_path)
        self.config = self._load_config(config_path)
        
        # Audio system (Google Cloud Speech-to-Text + TTS with barge-in)
        audio_settings = self.config.get('audio', {})
        asr_settings = audio_settings.get('asr', {})
        tts_settings = audio_settings.get('tts', {})
        barge_in_settings = self.config.get('barge_in', {})
        default_audio_device = self._get_int_setting('AUDIO_DEVICE_INDEX', -1)
        input_device = self._get_int_setting(
            'MIC_DEVICE_INDEX',
            default_audio_device,
        )
        output_device = self._get_int_setting(
            'SPEAKER_DEVICE_INDEX',
            default_audio_device,
        )
        audio_config = AudioConfig(
            sample_rate=self._get_int_setting(
                'MIC_SAMPLE_RATE',
                asr_settings.get('sample_rate', 16000),
            ),
            channels=self._get_int_setting(
                'MIC_CHANNELS',
                audio_settings.get('channels', 1),
            ),
            input_device=input_device,
            output_device=output_device,
            barge_in_enabled=bool(barge_in_settings.get('enabled', True)),
            barge_in_vad_aggressiveness=self._get_int_setting(
                'BARGE_IN_VAD_AGGRESSIVENESS',
                barge_in_settings.get('vad_aggressiveness', 2),
            ),
            barge_in_detection_timeout_ms=self._get_int_setting(
                'BARGE_IN_DETECTION_TIMEOUT_MS',
                barge_in_settings.get('detection_timeout_ms', 90),
            ),
            barge_in_silence_duration_ms=self._get_int_setting(
                'BARGE_IN_SILENCE_DURATION_MS',
                barge_in_settings.get('silence_duration_ms', 300),
            ),
            barge_in_frame_duration_ms=self._get_int_setting(
                'BARGE_IN_FRAME_DURATION_MS',
                barge_in_settings.get('frame_duration_ms', 30),
            ),
            barge_in_aec_enabled=bool(barge_in_settings.get('aec_enabled', True)),
            barge_in_aec_max_delay_ms=self._get_int_setting(
                'BARGE_IN_AEC_MAX_DELAY_MS',
                barge_in_settings.get('aec_max_delay_ms', 180),
            ),
            barge_in_aec_max_gain=float(os.getenv(
                'BARGE_IN_AEC_MAX_GAIN',
                barge_in_settings.get('aec_max_gain', 1.2),
            )),
            barge_in_aec_double_talk_ratio=float(os.getenv(
                'BARGE_IN_AEC_DOUBLE_TALK_RATIO',
                barge_in_settings.get('aec_double_talk_ratio', 1.4),
            )),
            barge_in_echo_suppression_threshold=float(os.getenv(
                'BARGE_IN_ECHO_SUPPRESSION_THRESHOLD',
                barge_in_settings.get('echo_suppression_threshold', 0.80),
            )),
            barge_in_echo_energy_ratio=float(os.getenv(
                'BARGE_IN_ECHO_ENERGY_RATIO',
                barge_in_settings.get('echo_energy_ratio', 0.45),
            )),
            barge_in_nearend_min_cleaned_rms=float(os.getenv(
                'BARGE_IN_NEAREND_MIN_CLEANED_RMS',
                barge_in_settings.get('nearend_min_cleaned_rms', 300.0),
            )),
            barge_in_nearend_mic_to_playback_ratio=float(os.getenv(
                'BARGE_IN_NEAREND_MIC_TO_PLAYBACK_RATIO',
                barge_in_settings.get('nearend_mic_to_playback_ratio', 1.15),
            )),
            barge_in_nearend_frames_required=self._get_int_setting(
                'BARGE_IN_NEAREND_FRAMES_REQUIRED',
                barge_in_settings.get('nearend_frames_required', 4),
            ),
            barge_in_startup_grace_ms=self._get_int_setting(
                'BARGE_IN_STARTUP_GRACE_MS',
                barge_in_settings.get('startup_grace_ms', 300),
            ),
            asr_engine=os.getenv('ASR_ENGINE', asr_settings.get('engine', 'google')),
            asr_model=os.getenv('WHISPER_MODEL', asr_settings.get('model', 'base')),
            asr_device=os.getenv('WHISPER_DEVICE', asr_settings.get('device', 'cpu')),
            mute_mode=mute,
            tts_engine=tts_settings.get('engine', 'google'),
            tts_speed=float(os.getenv('TTS_SPEED', tts_settings.get('speed', 1.0))),
            language_code=asr_settings.get('language', 'en-US'),
        )
        self.audio_manager = AudioManager(audio_config)
        
        # Phase 2: Load the enhanced system prompt that enables task offloading
        phase2_prompt_path = os.path.join(
            os.path.dirname(config_path), "system_prompt_phase2.txt"
        )
        phase2_prompt = None
        if os.path.exists(phase2_prompt_path):
            try:
                with open(phase2_prompt_path) as f:
                    phase2_prompt = f.read()
                self.logger.info("Loaded Phase 2 system prompt from %s", phase2_prompt_path)
            except Exception as e:
                self.logger.warning("Could not load Phase 2 prompt: %s", e)
        
        # LLM Engine (Gemini via Vertex AI)
        self.llm = create_llm_provider(
            provider_name=self.config.get('operator', {}).get('llm_provider', 'gemini'),
            project_id=os.getenv('GOOGLE_CLOUD_PROJECT_ID'),
            model=self.config.get('operator', {}).get('llm_model', 'gemini-1.5-flash'),
            system_prompt=phase2_prompt,
        )
        
        # Phase 2: File-based task watcher for agent communication
        # Use a dedicated LLM provider for announcements to avoid thread contention
        # with the main operator thread. A simpler system prompt is fine here.
        self.announce_llm = create_llm_provider(
            provider_name=self.config.get('operator', {}).get('llm_provider', 'gemini'),
            project_id=os.getenv('GOOGLE_CLOUD_PROJECT_ID'),
            model=self.config.get('operator', {}).get('llm_model', 'gemini-1.5-flash'),
            system_prompt=(
                "You are a concise status announcer for a robot assistant. "
                "Keep responses under 2 sentences. Sound natural and helpful. "
                "Speak as if you are the robot itself."
            ),
        )
        # State
        self.is_running = False
        self.current_state = "idle"
        self.conversation_history = []
        self._task_results_lock = threading.Lock()
        self.task_watcher = TaskWatcher(
            llm=self.llm,
            announce_llm=self.announce_llm,
            audio_manager=self.audio_manager,
            on_result=self._on_task_result,
        )

        # Phase 3: Pre-inject existing implementations into conversation history
        # so Gemini knows what is already built on first turn
        try:
            _idx_path = os.path.expanduser("~/minipupper-app/knowledge/INDEX.json")
            if os.path.exists(_idx_path):
                with open(_idx_path) as _f:
                    _index = json.load(_f)
                _existing = []
                for _topic, _info in _index.items():
                    _impls = _info.get("implementations", [])
                    for _impl in _impls:
                        _impl_path = os.path.expanduser("~/minipupper-app/custom/" + _impl + "/test_results.md")
                        _tested = os.path.exists(_impl_path)
                        _summary = _info.get("summary", _topic)
                        _existing.append("- " + _impl + ": " + _summary + " [tested=" + str(_tested) + "]")
                if _existing:
                    _lines = "\n".join(_existing)
                    _text = "Existing implementations loaded from knowledge base:\n" + _lines
                    self.conversation_history.append(Message(role="system", content=_text))
                    self.logger.info("Phase 3: Pre-injected %d existing implementations into conversation history", len(_existing))
        except Exception as _e:
            self.logger.warning("Phase 3: Failed to pre-inject knowledge: %s", _e)
        
        # CLI flags
        self.keyboard_mode = keyboard
        self.mute_mode = mute
        # Always set volume on startup: 0% if muted, 100% otherwise
        # (PulseAudio sink volume persists between runs)
        self._set_mute_volume()
        
        # Thread pool
        self._worker_threads = []
        self._stop_event = threading.Event()
        self._interrupt_requested = threading.Event()
        self.gateway_client: Optional[OpenClawClient] = None
        
        # Phase 2: Track start time for filtering stale gateway messages
        self._started_at = time.time()
        self._agent_session = self.config.get("network", {}).get("session_target", None)
        self._cron_job_id = self.config.get("network", {}).get("cron_job_id", "")
        
        self.logger.info("Minipupper Operator initialized")
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load YAML configuration file"""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            self.logger.error(f"Config file not found: {config_path}")
            raise
        except yaml.YAMLError as e:
            self.logger.error(f"Invalid YAML config: {e}")
            raise

    def _load_environment(self, config_path: str):
        """Load environment variables from repo-local .env files if present."""
        if not load_dotenv:
            self.logger.warning("python-dotenv not available; skipping .env loading")
            return

        config_file = Path(config_path).resolve()
        env_files = [
            config_file.parent.parent / ".env",
            config_file.parent / ".env",
        ]

        for env_file in env_files:
            if env_file.exists():
                load_dotenv(dotenv_path=env_file, override=False)
                self.logger.info(f"Loaded environment from {env_file}")

    def _get_int_setting(self, name: str, default: int) -> int:
        """Read an integer environment variable with a safe fallback."""
        value = os.getenv(name)
        if value is None or value == "":
            return int(default)

        try:
            return int(value)
        except ValueError:
            self.logger.warning(f"Invalid integer for {name}: {value!r}; using {default}")
            return int(default)

    def _archive_stale_tasks(self):
        """Clear ALL tasks from tasks.json on startup, archiving first."""

        # New format: scan tasks/*/ for stale files and archive them
        tasks_dir = os.path.expanduser("~/minipupper-app/tasks")
        archiver = TaskArchiver()
        archived_count = 0
        for subdir in ("pending", "active", "completed"):
            d = os.path.join(tasks_dir, subdir)
            if not os.path.isdir(d):
                continue
            for fname in sorted(os.listdir(d)):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(d, fname)
                try:
                    with open(fpath) as f:
                        task = json.load(f)
                    archiver.archive_and_remove(task)
                    archived_count += 1
                except Exception:
                    pass
        if archived_count:
            self.logger.info("Archived %d stale task(s) from tasks/ on startup", archived_count)

        # Legacy fallback: clear old tasks.json
        tasks_file = os.path.expanduser("~/minipupper-app/tasks.json")
        if os.path.exists(tasks_file):
            try:
                os.remove(tasks_file)
            except OSError:
                pass
    
    def start(self):
        """Start the operator"""
        if self.is_running:
            self.logger.warning("Operator already running")
            return
        
        self.is_running = True
        self._stop_event.clear()
        
        # Start worker threads
        self._start_workers()
        
        # Phase 2: Start file-based task watcher
        if hasattr(self, 'task_watcher') and self.task_watcher:
            self.task_watcher.start()

        # Phase 2: Archive stale completed tasks so tasks.json starts clean
        self._archive_stale_tasks()
        
        self.logger.info("Minipupper Operator started")
    
    def stop(self):
        """Stop the operator gracefully"""
        if not self.is_running:
            return
        
        self.is_running = False
        self._stop_event.set()
        
        # Wait for workers
        for thread in self._worker_threads:
            thread.join(timeout=5.0)
        
        self.audio_manager.shutdown()
        # Phase 2: Stop task watcher
        if hasattr(self, 'task_watcher') and self.task_watcher:
            self.task_watcher.stop()
        
        # Phase 2: Kill background audio/dance processes on shutdown
        music_flag = '/tmp/minipupper_music_active'
        dance_flag = '/tmp/minipupper_dance_active'
        if os.path.exists(music_flag):
            subprocess.run([sys.executable, 'custom/play_audio.py', 'stop'],
                capture_output=True, timeout=5)
        if os.path.exists(dance_flag):
            subprocess.run([sys.executable, 'custom/hf_dance/hf_dance_to_audio.py', 'stop'],
                capture_output=True, timeout=10)
        
        self.logger.info('Minipupper Operator stopped')
    
    def _start_workers(self):
        """Start background worker threads"""
        # Speech-to-text worker (or keyboard input worker)
        if self.keyboard_mode:
            kbd_thread = threading.Thread(
                target=self._keyboard_worker,
                daemon=True,
                name="KeyboardWorker"
            )
            kbd_thread.start()
            self._worker_threads.append(kbd_thread)
        else:
            asr_thread = threading.Thread(
                target=self._asr_worker,
                daemon=True,
                name="ASRWorker"
            )
            asr_thread.start()
            self._worker_threads.append(asr_thread)
        
        # Operator Worker - processes input and generates responses
        op_thread = threading.Thread(
            target=self._operator_worker,
            daemon=True,
            name="OperatorWorker"
        )
        op_thread.start()
        self._worker_threads.append(op_thread)
        
        
        # Control Worker - handles system commands
        control_thread = threading.Thread(
            target=self._control_worker,
            daemon=True,
            name="ControlWorker"
        )
        control_thread.start()
        self._worker_threads.append(control_thread)

        # Gateway Worker - connect to OpenClaw Gateway and receive snapshots
        gw_thread = threading.Thread(
            target=self._gateway_worker,
            daemon=True,
            name="GatewayWorker"
        )
        gw_thread.start()
        self._worker_threads.append(gw_thread)

        # Pending Task Watcher - retrigger cron for stale pending tasks
        ptw_thread = threading.Thread(
            target=self._pending_task_watcher,
            daemon=True,
            name="PendingTaskWatcher"
        )
        ptw_thread.start()
        self._worker_threads.append(ptw_thread)
    
    def _asr_worker(self):
        """Worker: Speech-to-text processing"""
        self.logger.info("ASR Worker started")
        
        while self.is_running:
            try:
                # Continuously listen for speech
                transcript = self.audio_manager.listen()
                
                if transcript and transcript.strip():
                    self.logger.info(f"ASR: {transcript}")

                    # Explicit interrupt commands (user telling the robot to stop)
                    try:
                        if self._is_interrupt_command(transcript):
                            self.logger.info("Interrupt command detected from ASR: %s", transcript)
                            # Signal audio manager to stop playback immediately
                            try:
                                self.audio_manager.interrupt_speech()
                            except Exception:
                                pass
                            # mark internal interrupt flag for any other consumers
                            try:
                                self._interrupt_requested.set()
                            except Exception:
                                pass
                            # Also stop dance/music/cleanup like keyboard "stop" does
                            try:
                                import subprocess as _sp
                                _sp.run([sys.executable, "custom/hf_dance/hf_dance_to_audio.py", "stop"],
                                    capture_output=True, timeout=10)
                            except Exception:
                                pass
                            try:
                                _sp.run([sys.executable, "custom/play_audio.py", "stop"],
                                    capture_output=True, timeout=5)
                            except Exception:
                                pass
                            try:
                                import glob as _gl, os as _os
                                for _f in _gl.glob("tasks/pending/*.json") + _gl.glob("tasks/active/*.json"):
                                    try: _os.remove(_f)
                                    except: pass
                            except Exception:
                                pass
                            # Do not enqueue interrupt phrases as user input
                            continue
                    except Exception:
                        pass

                    # If currently speaking, and the transcript is not speaker-bleed,
                    # treat this as user speech and interrupt playback so the user can take over.
                    try:
                        speaking = getattr(self.audio_manager, '_is_speaking', False)
                        if speaking and not self._is_likely_speaker_bleed(transcript):
                            self.logger.info("User speech detected during playback — interrupting: %s", transcript)
                            try:
                                self.audio_manager.interrupt_speech()
                            except Exception:
                                pass
                            try:
                                self._interrupt_requested.set()
                            except Exception:
                                pass
                            # Continue to enqueue the user transcript for processing
                    except Exception:
                        pass

                    # Detect speaker-bleed: if the transcript is essentially verbatim
                    # from the last assistant response, drop it to avoid treating
                    # the robot's own speech as user input.
                    try:
                        if self._is_likely_speaker_bleed(transcript):
                            self.logger.debug("Dropped ASR transcript (likely speaker-bleed): %s", transcript)
                            continue
                    except Exception:
                        # If bleed detection fails for any reason, fallback to enqueue
                        pass

                    input_text_queue.put(transcript)
                        
            except Exception as e:
                self.logger.error(f"ASR Worker error: {e}")
                time.sleep(1.0)
    
    def _keyboard_worker(self):
        """Worker: Keyboard input (replaces ASR in --keyboard mode)"""
        self.logger.info("Keyboard Worker started")
        print()
        print("=" * 60)
        print("  KEYBOARD INPUT MODE")
        print("  " + "-" * 54)
        print("  Type your message below and press Enter.")
        print("  Type 'exit' or 'quit' to stop the operator.")
        print("  Type 'mute' to toggle TTS on/off (if started with --mute).")
        print("=" * 60)
        print()

        while self.is_running:
            try:
                user_input = input("> ")
                if user_input.strip().lower() in ("exit", "quit"):
                    self.logger.info("Exit requested via keyboard")
                    self.is_running = False
                    break
                if user_input.strip().lower() == "mute":
                    self.mute_mode = not self.mute_mode
                    self._set_mute_volume()
                    status = "OFF" if self.mute_mode else "ON"
                    print(f"[Mute mode is now {status}]")
                    continue
                if user_input.strip():
                    input_text_queue.put(user_input.strip())
            except EOFError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"Keyboard Worker error: {e}")
                time.sleep(0.5)
    
    def _preprocess_command(self, text):
        """Fast-path: Handle stop/cancel commands locally before Gemini sees them.

        Returns None if fully handled (Gemini skipped), or remaining text to process.
        """
        if not text or not text.strip():
            return None

        text_lower = text.strip().lower()

        # Keywords and targets
        stop_words = ["stop", "cancel", "shut up", "shutup", "be quiet", "quiet", "enough", "kill"]
        dance_words = ["dance", "dancing"]
        music_words = ["music", "song", "audio", "playing"]
        all_words = ["everything", "all"]

        has_stop = any(kw in text_lower for kw in stop_words)
        has_dance = any(w in text_lower for w in dance_words)
        has_music = any(w in text_lower for w in music_words)
        has_all = any(w in text_lower for w in all_words)

        if not has_stop:
            return text  # Not a stop command, pass through to Gemini

        # Strip stop keywords to get remaining query
        remaining = text_lower
        for kw in stop_words:
            remaining = remaining.replace(kw, "").replace(kw.capitalize(), "")
        remaining = remaining.strip().strip(",.!? ").strip()
        for p in ["and ", "then ", "also "]:
            if remaining.startswith(p):
                remaining = remaining[len(p):]
        remaining = remaining.strip()

        killed_anything = False
        played_result = None

        if has_all or (not has_dance and not has_music and not remaining):
            # "stop everything" or bare "stop"
            subprocess.run([sys.executable, "custom/hf_dance/hf_dance_to_audio.py", "stop"],
                capture_output=True, timeout=10)
            subprocess.run([sys.executable, "custom/play_audio.py", "stop"],
                capture_output=True, timeout=5)
            for f in glob.glob("tasks/pending/*.json") + glob.glob("tasks/active/*.json"):
                try: os.remove(f)
                except: pass
            killed_anything = True
            played_result = "All stopped!"
            self.logger.info("Fast-path: Stopped everything locally")
        else:
            if has_dance:
                subprocess.run([sys.executable, "custom/hf_dance/hf_dance_to_audio.py", "stop"],
                    capture_output=True, timeout=10)
                for f in glob.glob("tasks/pending/*.json") + glob.glob("tasks/active/*.json"):
                    try:
                        with open(f) as fh:
                            data = json.load(fh)
                        if data.get("action", "").startswith("robot.dance") or data.get("action", "").startswith("robot.stop"):
                            os.remove(f)
                    except:
                        pass
                killed_anything = True
                played_result = "Stopped dancing!" if not has_music and not remaining else None
                self.logger.info("Fast-path: Stopped dance locally")

            if has_music:
                subprocess.run([sys.executable, "custom/play_audio.py", "stop"],
                    capture_output=True, timeout=5)
                for f in glob.glob("tasks/pending/*.json") + glob.glob("tasks/active/*.json"):
                    try:
                        with open(f) as fh:
                            data = json.load(fh)
                        if data.get("action", "").startswith("robot.play") or data.get("action", "").startswith("robot.stop"):
                            os.remove(f)
                    except:
                        pass
                killed_anything = True
                played_result = played_result or ("Music stopped." if not remaining else None)
                self.logger.info("Fast-path: Stopped music locally")

        if killed_anything and played_result:
            output_text_queue.put(played_result)
            try:
                self.audio_manager.speak(played_result)
            except Exception:
                pass

        if killed_anything and not remaining:
            return None  # Fully handled, skip Gemini

        # Return remaining query text (e.g., "stop dancing and play jazz" -> "play jazz")
        return remaining if (killed_anything and remaining and remaining != text_lower) else text
    def _operator_worker(self):
        """Worker: Process input and generate responses"""
        self.logger.info("Operator Worker started")
        
        while self.is_running:
            try:
                # Check for input text
                try:
                    text = input_text_queue.get(timeout=1.0)
                except Exception:
                    continue


                # Phase 4: Local fast-path pre-processor for stop/cancel commands
                text = self._preprocess_command(text)
                if text is None:
                    continue  # fully handled locally, skip Gemini
                self.logger.info(f"Operator processing: {text}")
                self.current_state = "processing"

                # Phase 3: Drain any completed task results into conversation history,
                # so Gemini knows what happened and can follow up properly.
                # (Note: _on_task_result may add during processing, but the lock
                #  and the fact that the watcher runs on a delay means this is fine.)
                # (Already injected asynchronously by _on_task_result callback.)

                # Phase 2: Always process through Gemini LLM first
                # Gemini decides whether to handle locally or offload to agent
                response = self._process_user_input(text)
                
                # Phase 2: Check if Gemini wants to offload one or more tasks to the OpenClaw agent.
                spoken_text, task_payloads = self._extract_task_blocks(response)
                if task_payloads:
                    self.logger.info("Phase 2: Offloading %d task(s) to agent", len(task_payloads))
                    if not spoken_text:
                        spoken_text = "I'll handle that now."
                    # Write all pending tasks first, then trigger cron once for the full batch.
                    if hasattr(self, 'task_watcher') and self.task_watcher:
                        self.task_watcher.write_tasks(task_payloads)
                        self.logger.info("Phase 2: Wrote %d task(s) to tasks.json for agent", len(task_payloads))
                        if self.gateway_client:
                            cron_id = getattr(self, "_cron_job_id", "")
                            if cron_id:
                                self.gateway_client.trigger_cron(cron_id)
                                self.logger.info("Phase 2: Triggered cron %s for %d task(s)", cron_id, len(task_payloads))
                            else:
                                self.gateway_client.send_sessions_send(
                                    getattr(self, "_agent_session", "") or "main",
                                    "task_written"
                                )
                                self.logger.info("Phase 2: Notified agent via main session")

                        # Speak introductory text once before the task batch executes.
                        if spoken_text:
                            output_text_queue.put(spoken_text)
                            try:
                                completed = self.audio_manager.speak(spoken_text)
                                if not completed:
                                    self.logger.info("Speech interrupted")
                            except Exception:
                                pass
                        self.current_state = "idle"
                        continue
                
                # Fallback: No offload or failed to send — speak Gemini's response locally
                
                if response:
                    # Log generated response text at INFO so operator output is visible
                    try:
                        self.logger.info("Generated response (%d chars): %s", len(response), response)
                    except Exception:
                        # Fallback if message too large for formatting
                        self.logger.info("Generated response (%d chars)", len(response))
                    output_text_queue.put(response)
                    
                    # Speak response with barge-in support
                    try:
                        interrupted = not self.audio_manager.speak(response)
                        if interrupted:
                            self.logger.info("Speech playback stopped")
                    except Exception as e:
                        self.logger.error(f"TTS Error: {e}")
                
                self.current_state = "idle"
                    
            except Exception as e:
                self.logger.error(f"Operator Worker error: {e}")
                self.current_state = "idle"
                time.sleep(0.5)

    def _gateway_worker(self):
        """Worker: maintain connection to OpenClaw Gateway and forward frames."""
        self.logger.info("Gateway Worker started")
        network_cfg = self.config.get('network', {})
        if not network_cfg.get('tailscale_enabled', False):
            self.logger.info("Tailscale disabled; skipping Gateway Worker")
            return

        gateway_url = os.getenv('OPENCLAW_GATEWAY_URL') or network_cfg.get('gateway_url')
        if not gateway_url:
            self.logger.warning("No gateway_url configured; skipping Gateway Worker")
            return

        # Load device identity if available
        device_identity = load_device_identity()
        # Phase 2: Determine agent session from config
        self._agent_session = self.config.get('network', {}).get('session_target', None)
        if self._agent_session:
            self.logger.info("Phase 2: Agent session target: %s", self._agent_session)
        self.gateway_client = OpenClawClient(
            gateway_url,
            device_identity=device_identity,
            session_target=self._agent_session or 'main',
        )

        def handler(frame: dict):
            try:
                openclaw_queue.put(frame, timeout=0.1)
            except Exception:
                pass

        try:
            try:
                self.gateway_client.start(handler)
            except Exception as e:
                # Likely missing dependency (websocket-client) or startup failure.
                # Log once and disable gateway integration without crashing the thread.
                logger.warning(f"Gateway client could not start: {e}")
                self.gateway_client = None
                return

            # keep alive until stop requested
            while self.is_running and not self._stop_event.is_set():
                # Drain openclaw frames and make lightweight decisions here
                try:
                    frame = openclaw_queue.get(timeout=1.0)
                except Exception:
                    continue

                try:
                    self._handle_openclaw_frame(frame)
                except Exception:
                    continue

        finally:
            if self.gateway_client:
                self.gateway_client.stop()


    def _handle_openclaw_frame(self, frame: dict):
        """Process raw frame from OpenClaw Gateway and potentially announce via LLM.

        Phase 2: Before falling back to freeform parsing, check for structured
        minipupper-v1 protocol messages. If found, use the protocol handler
        for clean status/result extraction.

        Phase 2b: Only process protocol messages from 'assistant' role that
        are actual task results, not internal cron chatter.
        """
        # Phase 2b: Skip messages from 'user' role (our own task sends echo back)
        if frame.get('event') == 'session.message':
            msg_role = frame.get('payload', {}).get('message', {}).get('role', '')
            msg_content = frame.get('payload', {}).get('message', {}).get('content', '')
            if msg_role == 'user':
                return  # Don't process our own messages echoing back
        # Phase 2: Try structured protocol first
            # Phase 2c: Skip cron session chatter — file-based protocol only
            session_key = frame.get("payload", {}).get("sessionKey", "")
            if ":cron:" in session_key:
                return
        try:
            from src.core.protocol_handler import handle_protocol_frame
            announcement = handle_protocol_frame(frame, self.llm, started_at=self._started_at)
            if announcement:
                self.logger.info("Gateway response: %s", announcement[:200])
                return
        except Exception:
            pass

        # Phase 2d: No legacy fallback — file-based protocol only; the file
        # handles everything.
        return

    
    
    def _control_worker(self):
        """Worker: Handle system control commands"""
        self.logger.info("Control Worker started")
        
        while self.is_running:
            try:
                # Check for control commands
                try:
                    command = control_queue.get(timeout=1.0)
                except:
                    continue
                
                if command == "shutdown":
                    self.logger.info("Shutdown command received")
                    self.stop()
                elif command == "restart":
                    self.logger.info("Restart command received")
                    self.stop()
                    self.start()
                    
            except Exception as e:
                self.logger.error(f"Control Worker error: {e}")

    
    def _on_task_result(self, task: dict):
        """Called by TaskWatcher when a task completes and is announced.
        Injects the result into Gemini's conversation history so it knows
        what happened on subsequent turns."""
        action = task.get("action", "unknown")
        result = task.get("result", "")
        error = task.get("error")
        user_query = task.get("userQuery", "")
        if error:
            text = f"[Task completed: {action}] Error: {error}"
        else:
            text = f"[Task completed: {action}] Result: {result}"
        with self._task_results_lock:
            self.conversation_history.append(Message(role="system", content=text))
        self.logger.info("Phase 3: Injected task result into conversation history: %s", action)

    def _process_user_input(self, text: str) -> str:
        """
        Process user input and generate response using Gemini LLM.
        
        Args:
            text: User input text
            
        Returns:
            Response text to speak
        """
        self.logger.info(f"Processing input: {text}")
        self.current_state = "processing"
        
        try:
            # Store in conversation history
            self.conversation_history.append(Message(role="user", content=text))
            messages_for_llm = self._get_context_messages()
            
            # Generate response using LLM (Gemini)
            response = self.llm.generate_response(
                messages=messages_for_llm,
                max_tokens=self.config.get('operator', {}).get('max_response_tokens', 500)
            )
            
            # Store response in conversation history
            self.conversation_history.append(Message(role="assistant", content=response))
            
            # Log successful processing
            self.logger.debug(f"Generated response: {response[:100]}...")
            self.current_state = "idle"
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error processing input: {e}")
            self.current_state = "idle"
            return "I encountered an error processing your request. Please try again."

    def _extract_task_blocks(self, response: str):
        """Split Gemini output into spoken text and one or more task payloads."""
        task_pattern = re.compile(r'\[TASK\](.*?)\[/TASK\]', re.DOTALL)
        matches = list(task_pattern.finditer(response))
        if not matches:
            return response.strip(), []

        spoken_text = response[:matches[0].start()].strip()
        task_payloads = []

        for match in matches:
            raw_task = match.group(1).strip()
            if not raw_task:
                continue

            try:
                parsed_task = json.loads(raw_task)
            except json.JSONDecodeError as e:
                self.logger.warning("Phase 2: Invalid task JSON from Gemini: %s", e)
                continue

            if isinstance(parsed_task, list):
                for item in parsed_task:
                    if isinstance(item, dict) and item.get("protocol") == "minipupper-v1" and item.get("type") == "task":
                        task_payloads.append(item)
                continue

            if isinstance(parsed_task, dict) and parsed_task.get("protocol") == "minipupper-v1" and parsed_task.get("type") == "task":
                task_payloads.append(parsed_task)
            else:
                self.logger.warning("Phase 2: Ignoring unsupported task payload from Gemini")

        return spoken_text, task_payloads
    
    def _get_context_messages(self) -> list:
        """
        Get conversation history for LLM context.
        
        Keeps recent messages up to token limit.
        
        Args:
            
        Returns:
            List of Message objects for LLM
        """
        # For now, keep last 10 messages (can improve with actual token counting)
        max_messages = 10
        start_idx = max(0, len(self.conversation_history) - max_messages)
        
        return self.conversation_history[start_idx:]

    def _is_likely_speaker_bleed(self, transcript: str) -> bool:
        """
        Heuristic: returns True when the ASR `transcript` appears to be
        a verbatim (or nearly verbatim) echo of the last assistant message.

        Method:
        - Find the most recent assistant message in `conversation_history`.
        - Normalize both strings (lowercase, strip punctuation).
        - Compute token coverage: fraction of transcript tokens present in assistant tokens.
        - If coverage >= 0.95 and transcript has >= 3 tokens, consider it bleed.
        - Also treat as bleed when the cleaned transcript is a substring of the assistant text
          (useful for short repeats) with >=2 tokens.
        """
        if not transcript:
            return False

        # find last assistant message
        last_assistant = None
        for msg in reversed(self.conversation_history):
            if getattr(msg, 'role', None) == 'assistant' and getattr(msg, 'content', None):
                last_assistant = msg.content
                break

        if not last_assistant:
            return False

        def _clean(s: str) -> str:
            return re.sub(r"[^\w\s]", "", s.lower()).strip()

        t_clean = _clean(transcript)
        a_clean = _clean(last_assistant)

        if not t_clean:
            return False

        t_tokens = t_clean.split()
        a_tokens = set(a_clean.split())

        if not t_tokens:
            return False

        # token coverage
        matched = sum(1 for tok in t_tokens if tok in a_tokens)
        coverage = matched / float(len(t_tokens))

        if len(t_tokens) >= 3 and coverage >= 0.95:
            return True

        # substring check for shorter transcripts
        if len(t_tokens) >= 2 and t_clean in a_clean:
            return True

        return False

    def _is_interrupt_command(self, transcript: str) -> bool:
        """
        Heuristic to detect short explicit user interrupt phrases.
        Returns True for clear short commands like "stop", "cancel", "that's enough", etc.
        """
        if not transcript:
            return False

        t = re.sub(r"[^\w\s]", "", transcript.lower()).strip()
        if not t:
            return False

        # exact phrases
        phrases = {"stop", "cancel", "cancel output", "thats enough", "that's enough", "stop that", "interrupt", "abort", "never mind"}
        if t in phrases:
            return True

        tokens = t.split()
        # single-word interrupts
        if len(tokens) <= 3 and tokens and tokens[0] in {"stop", "cancel", "abort", "interrupt"}:
            return True

        return False
    
    
    
    
    
    
    
    def _pending_task_watcher(self):
        """Check tasks/pending/ every 5s for stale pending tasks (>30s old).
        
        If a pending task has been sitting untouched — likely a missed
        cron.run trigger — retrigger the cron. Scans the per-file task
        directory directly instead of relying on the legacy tasks.json rebuild.
        """
        cron_id = getattr(self, "_cron_job_id", "")
        if not cron_id:
            self.logger.warning("PendingTaskWatcher: No cron_job_id configured")
            return

        pending_dir = os.path.expanduser("~/minipupper-app/tasks/pending")

        while self.is_running and not self._stop_event.is_set():
            time.sleep(5)
            try:
                if not os.path.isdir(pending_dir):
                    continue
                for fname in sorted(os.listdir(pending_dir)):
                    if not fname.endswith(".json"):
                        continue
                    fpath = os.path.join(pending_dir, fname)
                    try:
                        with open(fpath) as f:
                            task = json.load(f)
                    except (json.JSONDecodeError, OSError):
                        continue
                    if task.get("status") == "pending":
                        age = time.time() - task.get("createdAt", 0)
                        if age > 30 and self.gateway_client:
                            # Mark stale in file to prevent re-trigger loops
                            task["startedAt"] = time.time()
                            with open(fpath, "w") as f:
                                json.dump(task, f, indent=2)
                            self.gateway_client.trigger_cron(cron_id)
                            self.logger.info("PendingTaskWatcher: Retriggered cron for stale task %s (age=%ds)", fname, int(age))
                            break
            except Exception as e:
                self.logger.warning("PendingTaskWatcher error: %s", e)

    def _set_mute_volume(self):
        """Sync mute state to AudioManager and set speaker to idle volume.

        Delegates volume control to AudioManager which handles the
        amixer ramp-up/down around every TTS call.
        """
        self.audio_manager.mute_mode = self.mute_mode
        self.audio_manager._set_volume(tts_active=False)



def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Minipupper Operator — Autonomous robot assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s                          Normal mode (voice in/out)
  %(prog)s -k                       Keyboard input mode (no STT)
  %(prog)s -m                       Mute mode (no TTS, output in log)
  %(prog)s -k -m                    Keyboard + silent (dev mode)
        """
    )
    parser.add_argument(
        "-k", "--keyboard",
        action="store_true",
        help="Disable speech-to-text; use terminal keyboard for input"
    )
    parser.add_argument(
        "-m", "--mute",
        action="store_true",
        help="Disable text-to-speech; show responses on screen only"
    )
    args = parser.parse_args()

    operator = MinipupperOperator(keyboard=args.keyboard, mute=args.mute)

    try:
        operator.start()

        if args.keyboard:
            logger.info("\u2713 Minipupper Operator running. Using KEYBOARD input.")
            logger.info("Type your messages in the terminal and press Enter.")
        elif args.mute:
            logger.info("\u2713 Minipupper Operator running. TTS is MUTED.")
            logger.info("Listening for speech... (output shown in log)")
        else:
            logger.info("\u2713 Minipupper Operator running. Listening for speech...")
        logger.info("Press Ctrl+C to stop.")

        # Keep running and wait for signals
        while operator.is_running:
            time.sleep(0.5)

    except KeyboardInterrupt:
        logger.info("\nReceived shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Shutting down...")
        operator.stop()
        logger.info("Operator stopped")


if __name__ == "__main__":
    main()

    