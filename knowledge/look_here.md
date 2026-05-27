# Custom Command Mapping: "Look Here"

## Summary
Implemented a mechanism to map the spoken phrase "look here" (or any hand gesture pointing direction) from user speech to the execution of `custom/look_here.py` via the `robot.look_here` action.

## How It Works

### Architecture

1. **User says** "look here" or makes a pointing gesture the robot can see
2. **Gemini LLM** (in MinipupperOperator) recognizes this as a task that should use `robot.look_here`
3. **Gemini outputs** a `[TASK]` block with `action: "robot.look_here"`
4. **TaskWatcher** writes it to `~/minipupper-app/tasks.json`
5. **Cron task processor** reads the task, sees `action: "robot.look_here"`, and executes:
   ```
   python3 ~/minipupper-app/custom/look_here.py --json
   ```
6. **look_here.py** captures a photo from MIPI camera, analyzes it with Gemini Vision for hand gestures, and makes the robot look in the pointed direction (or squat if fingergun forward)
7. **Result** is written back to `tasks.json` for the TaskWatcher to announce

### Files Modified

| File | Change |
|------|--------|
| `config/system_prompt_phase2.txt` | Added `robot.look_here` as a known action with usage example |
| `knowledge/INDEX.json` | Added `custom_command_mapping_to_script` entry with implementations |

### Files Used (pre-existing)

| File | Purpose |
|------|---------|
| `custom/look_here.py` | Main script: capture → Gemini Vision analysis → robot movement |
| `scripts/capture_and_show.py` | Camera capture + LCD display helper |
| `robot/robot_control.py` | Low-level robot movement API (look-up, look-down, squat, etc.) |
| `tasks.json` | Shared task file between app and agent |
| `src/core/task_watcher.py` | Watches for task completion and announces via TTS |

### Cron Task Processor Mapping

The cron-based task processor (minipupper-task-processor) handles `robot.look_here` by executing:
```
python3 ~/minipupper-app/custom/look_here.py --json
```

This maps the `robot.look_here` action to the standalone script rather than the `robot_control.py` subcommand system.

### Supported Gestures (from look_here.py)

| Gesture | Robot Reaction |
|---------|---------------|
| Fingergun pointing forward (toward camera) | Squat |
| Hand pointing up | Look up |
| Hand pointing down | Look down |
| Hand pointing left | Look left |
| Hand pointing right | Look right |
| Open palm / single finger forward | Greet (wave) |
| No hand detected | Nothing (no movement) |

## Usage

When user says "look here" or points while saying it:
- Gemini will output: `[TASK]{"protocol":"minipupper-v1","type":"task","action":"robot.look_here","params":{}}[/TASK]`
- The robot will capture a photo, analyze the hand gesture, and react accordingly

## Future Improvements

- Add gesture detection confidence threshold tuning
- Support multi-word alias commands (e.g., "look over there", "check this out")
- Add fallback if camera is unavailable
- Pre-warm Gemini model for faster analysis
