# Migration to Gemini 3 Flash Preview

## Overview
Successfully migrated the application from `gemini-2.5-pro` to `gemini-3-flash-preview` with updated pricing and API configuration.

## Changes Made

### 1. Updated Model and API Configuration
**File**: `llm_engine.py`

- **Model**: Changed from `gemini-2.5-pro` to `gemini-3-flash-preview`
- **Thinking Config**: Updated from `thinking_budget` to `thinking_level="medium"`
  
```python
# Old Configuration
config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(
        include_thoughts=False,
        thinking_budget=thinking_budget
    )
)
stream = client.models.generate_content_stream(
    model="gemini-2.5-pro",
    contents=contents,
    config=config
)

# New Configuration
config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(
        thinking_level="medium"
    )
)
stream = client.models.generate_content_stream(
    model="gemini-3-flash-preview",
    contents=contents,
    config=config
)
```

### 2. Updated Pricing
**File**: `batch_processor.py`

Added new pricing constants and `calculate_cost()` function:

- **Input Cost**: $0.50 per 1M tokens (was variable based on model)
- **Output Cost**: $3.00 per 1M tokens (includes thought tokens)

```python
# Gemini 3 Flash Preview Pricing (per 1M tokens)
INPUT_PRICE_PER_1M = 0.50   # $0.50 per 1M input tokens
OUTPUT_PRICE_PER_1M = 3.00  # $3.00 per 1M output tokens (includes thought tokens)

def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """
    Calculate the cost of a Gemini API call based on token usage.
    
    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens (includes thought tokens)
    
    Returns:
        Total cost in USD
    """
    input_cost = (input_tokens / 1_000_000) * INPUT_PRICE_PER_1M
    output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
    return input_cost + output_cost
```

### 3. Updated Documentation
**Files**: `llm_engine.py`

- Updated docstrings to reflect that `thinking_budget` is deprecated
- Added notes about fixed `thinking_level="medium"` for gemini-3-flash-preview
- Updated logging to show model name instead of thinking budget

## Backward Compatibility

The `thinking_budget` parameter is kept in function signatures for backward compatibility but is no longer used. All calls now use the fixed `thinking_level="medium"` configuration.

## Testing Recommendations

1. Test question generation with the new model
2. Verify cost calculations are accurate
3. Check that thinking/reasoning output quality is acceptable with `thinking_level="medium"`
4. Monitor token usage and costs

## Pricing Comparison

| Metric | Gemini 2.5 Pro | Gemini 3 Flash Preview |
|--------|----------------|------------------------|
| Input  | Variable       | $0.50 / 1M tokens     |
| Output | Variable       | $3.00 / 1M tokens     |

**Note**: Output costs include thought tokens, which are automatically billed as output tokens.
