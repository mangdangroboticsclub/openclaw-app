# Diet Food Analysis — Cron Trigger Capability

## What It Does
When the user says "tell me which food is better for my diet" (or similar food/calorie questions), the Gemini system prompt now recognizes this intent and emits a `food.analyze` task via the [TASK] protocol.

## Pipeline
1. **User says**: "Tell me which food is better for my diet" (or "what are the calories?", "is this food healthy?")
2. **Gemini LLM** in system_prompt_phase2.txt matches this to `food.analyze` action and emits a [TASK] JSON block
3. **App writes** the task JSON to `~/minipupper-app/tasks.json`
4. **Task Processor** (cron/agent) reads the pending task, sees `action: "food.analyze"`
5. **task_handler.py** routes to `_handle_food_analyze()` which runs:
   ```
   python3 /home/ubuntu/minipupper-app/custom/calorie_calculator.py --json
   ```
6. **calorie_calculator.py** captures a photo from the MIPI CSI camera, sends to Gemini Vision (Vertex AI), and returns estimated calories per food item plus a diet suggestion

## Files Involved
| File | Purpose |
|------|---------|
| `custom/calorie_calculator.py` | Photo capture + Gemini Vision analysis script (EXISTS) |
| `config/system_prompt_phase2.txt` | Gemini prompt — contains `food.analyze` action example (UPDATED) |
| `~/minipupper-app/tasks.json` | Task queue file (EXISTS) |
| Agent's `task_handler.py` | Routes `food.analyze` action to exec command (UPDATED) |

## How to Use
Just say to the robot:
- "Tell me which food is better for my diet"
- "What are the calories in this food?"
- "Is this food healthy for me?"

The robot will take a photo of the food in front of its camera, analyze it with AI, and tell you estimated calories per item and which one is better for your diet.

## Implementation Notes
- The calorie_calculator.py script was ALREADY EXISTING and functional before this implementation
- This implementation only wired up the command routing (system prompt + task handler)
- Uses Gemini 2.5 Flash via Vertex AI for vision analysis
- Credentials: /home/ubuntu/apps-md-robots/20250923.json
- Project: modern-rex-420404

## Tested
- [ ] Voice command → task created in tasks.json
- [ ] Task processor reads and routes to exec
- [ ] calorie_calculator.py runs correctly
- [ ] Results returned to user
