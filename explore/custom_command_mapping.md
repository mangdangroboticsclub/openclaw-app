# Explore: Custom Command Mapping

## Question
Check if there's an existing mechanism to map custom phrases like "look here" to specific Python scripts like "look_here.py"

## Short Answer
No dynamic plugin system exists. Command routing is hardcoded at every stage.

## Architecture Walkthrough

### Stage 1 — Gemini LLM (system_prompt_phase2.txt)
Gemini's system prompt teaches it which `action` values to output in [TASK] blocks.
The prompt has no mention of "look here" or `custom.look_here`.
Available actions: `robot.move_forward`, `robot.take_photo_and_show`, `explore`, `implement`, `web_search`, `web_fetch`.

### Stage 2 — Task File (tasks.json)
App writes the [TASK] JSON verbatim to tasks.json. No mapping layer here.

### Stage 3 — Agent Task Processor (cron)
Reads tasks.json, maps action strings to execution:
- `robot.*` → `robot_control.py` (hardcoded action→subcommand in TOOLS.md)
- `explore`, `implement`, `web_search`, `web_fetch`, `query`, `vision_analyze_image`
No `custom.*` or `robot.look_here` routing exists.

### Stage 4 — robot_control.py (FPC API)
Hardcoded command→MovementGroup mappings:
- `look-up` → `move.look_up()`
- `forward` → `move.gait_uni(v_x=0.2)`
Cannot run external scripts.

### Stage 5 — custom/look_here.py
Standalone script that captures photo → Gemini Vision analysis → calls robot_control.py as subprocess.
No registration mechanism — must be invoked explicitly.

## Options to Add the Mapping
A. **System prompt** — Add `robot.look_here` to Gemini's known actions
B. **Task processor** — Add mapping in this cron processor
C. **Plugin registry** — Auto-scan custom/ for scripts
D. **Direct keyword** — The app detects "look here" directly

**Recommended: B + A** for minimal effort.

## Files Examined
- ~/minipupper-app/config/system_prompt_phase2.txt
- ~/minipupper-app/gateway/cron_config.json
- ~/minipupper-app/gateway/protocol.py
- ~/minipupper-app/gateway/task_handler.py
- ~/minipupper-app/robot/robot_control.py
- ~/minipupper-app/custom/look_here.py
- ~/minipupper-app/minipupper_operator.py
- ~/minipupper-app/src/core/task_watcher.py
- ~/minipupper-app/src/core/protocol_handler.py
