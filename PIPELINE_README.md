# Multi-Stage Question Generation Pipeline

## ✨ Simplified Architecture: 4 Prompts Only

Instead of managing 12 different prompts (text/PDF/image variants), you now have **just 4 unified prompts** - one per stage. Each prompt automatically handles text, PDFs, and images.

```
Pipeline Flow:
┌──────────────────────────────────────────┐
│ Stage 1: SCENARIO GENERATION             │
│ Prompt: cbs_scenario                     │
└────────────────┬─────────────────────────┘
                 ↓
┌──────────────────────────────────────────┐
│ Stage 2: QUESTION GENERATION             │
│ Prompt: cbs_question_from_scenario       │
└────────────────┬─────────────────────────┘
                 ↓
┌──────────────────────────────────────────┐
│ Stage 3: SOLUTION GENERATION             │
│ Prompt: cbs_solution_from_question       │
└────────────────┬─────────────────────────┘
                 ↓
┌──────────────────────────────────────────┐
│ Stage 4: EDUCATIONAL ANALYSIS            │
│ Prompt: cbs_analysis_from_solution       │
└──────────────────────────────────────────┘
```

## 📁 Files Overview

### 1. `pipeline_prompts.yaml` ⭐
**4 unified prompt keys** - fill these with your instructions:
- `cbs_scenario` - Create realistic scenario
- `cbs_question_from_scenario` - Generate question from scenario
- `cbs_solution_from_question` - Create step-by-step solution
- `cbs_analysis_from_solution` - Generate educational insights

Each prompt:
- Receives PDF/image files automatically when present
- Gets structured data from previous stages injected
- Outputs structured JSON

### 2. `pipeline_config.yaml` ⚙️
**Control model settings per stage:**
- Which model to use (e.g., gemini-2.0-flash-thinking-exp-01-21)
- Temperature (0.0 conservative → 2.0 creative)
- Thinking level (low/medium/high)
- Advanced params (max_tokens, top_p, top_k)

Current defaults create a balanced pipeline.

### 3. `pipeline_builder.py` 🔧
Stage-specific prompt builders that:
- Load templates from `pipeline_prompts.yaml`
- Inject data from previous stages
- Handle file attachments
- Replace placeholders with config values

### 4. `pipeline_executor.py` 🚀
Main execution engine:
- Runs all 4 stages sequentially
- Loads per-stage config
- Tracks tokens across stages
- Handles errors gracefully

### 5. `batch_processor.py` (Modified) ✅
Integrated to use pipeline when:
```python
GENERATION_PIPELINE_MODE == "SCENARIO_FIRST"  # Enabled by default
```

## 🎯 Quick Start

### Step 1: Fill Prompts (REQUIRED)
Open `pipeline_prompts.yaml` and replace `[USER TO FILL]` for each of the 4 prompts.

**Example for `cbs_scenario`:**
```yaml
cbs_scenario: |
  Create a realistic {{Grade}} {{Subject}} scenario for {{Topic}}.
  
  Generate JSON with:
  {
    "context": "real-world situation",
    "known_values": {"var": "value with units"},
    "constraints": ["constraint list"],
    "measurable_relationships": {"formula_name": "equation"},
    "real_world_goal": "what to find",
    "concept_tags": ["tag1", "tag2"]
  }
```

Available placeholders in prompts:
- `{{Grade}}`, `{{Subject}}`, `{{Chapter}}`, `{{Topic}}`
- `{{SCENARIO_DATA}}` (Stage 2+)
- `{{QUESTION_DATA}}` (Stage 3+)
- `{{SOLUTION_DATA}}` (Stage 4)

### Step 2: Adjust Model Settings (Optional)
Edit `pipeline_config.yaml` to customize per-stage behavior:
```yaml
scenario_generation:
  temperature: 1.2  # More creative scenarios
  thinking_level: "high"
```

### Step 3: Run Generation
Once prompts are filled, the pipeline runs automatically. No code changes needed.

## 🎛️ Configuration Examples

### Creative Scenario, Precise Solution
```yaml
scenario_generation:
  temperature: 1.5  # Very creative
solution_generation:
  temperature: 0.1  # Very precise
```

### Fast Pipeline (Lower Thinking)
```yaml
global:
  default_thinking_level: "medium"
```

### Uniform Model for All Stages
```yaml
global:
  use_uniform_model: true
  uniform_model: "gemini-2.0-flash-exp"
```

## 📊 Output Structure

Each generation produces:
```json
{
  "scenario": {
    "context": "...",
    "known_values": {...},
    ...
  },
  "question": {
    "question_text": "...",
    "target_unknown": "...",
    ...
  },
  "solution": {
    "stepwise_solution": "...",
    "final_answer": "...",
    ...
  },
  "analysis": {
    "key_concept": "...",
    "skills_tested": [...],
    ...
  },
  "_pipeline_metadata": {
    "mode": "SCENARIO_FIRST",
    "stages_completed": 4,
    "total_tokens": {...}
  }
}
```

## ✅ Benefits

✨ **Simple**: 4 prompts instead of 12  
🎯 **Unified**: Same prompt for text/PDF/images  
⚙️ **Controllable**: Different model/temp per stage  
🔄 **Automatic**: Data flows between stages  
🔙 **Compatible**: Falls back to legacy mode if needed  

## 🧪 Testing (After Filling Prompts)

1. Test scenario generation
2. Test full 4-stage pipeline
3. Test with PDF files
4. Test batch processing
5. Test regeneration

## 📝 Status

✅ Infrastructure complete  
✅ Configuration system ready  
✅ Batch processor integrated  
⏳ **ACTION REQUIRED**: Fill 4 prompts in `pipeline_prompts.yaml`  
⏳ Testing pending

## 🆘 Troubleshooting

**Q: Pipeline not activating?**  
A: Check `GENERATION_PIPELINE_MODE == "SCENARIO_FIRST"` in `pipeline_builder.py`

**Q: How to disable pipeline?**  
A: Set `GENERATION_PIPELINE_MODE = None` to use legacy flow

**Q: Stage failing with error?**  
A: Check prompt outputs valid JSON matching expected structure
