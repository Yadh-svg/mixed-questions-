# Key Normalization and Regex Matching System

## Overview

This document describes the robust key normalization and regex-based matching system implemented in `result_renderer.py` to handle inconsistent JSON keys from Gemini's output.

## Problem Statement

Gemini's JSON output often contains inconsistent key formats, including:
- Different casing: `CorrectAnswer`, `correctanswer`, `CORRECT_ANSWER`
- Different separators: `correct_answer`, `correct-answer`, `correct answer`
- Collapsed camelCase: `DistractorAnalysis`, `KeyIdea`
- Variations: `Solution` vs `Solution Explanation`

These inconsistencies made it difficult to reliably extract and render question data.

## Solution

### 1. Key Normalization Function

```python
def normalize_field(field: str) -> str:
    """
    Normalize a field/key string by:
    - Stripping whitespace
    - Replacing spaces, underscores, and hyphens with a single space
    - Converting to lowercase
    """
    field = field.strip()
    field = re.sub(r'[\s_\-]+', ' ', field)
    field = field.lower()
    return field
```

**Examples:**
- `"DistractorAnalysis"` → `"distractoranalysis"`
- `"Distractor_Analysis"` → `"distractor analysis"`
- `"distractor-analysis"` → `"distractor analysis"`
- `"DISTRACTOR ANALYSIS"` → `"distractor analysis"`

### 2. Comprehensive Regex Patterns

Each expected field has a regex pattern that matches multiple format variations:

| Standard Key | Regex Pattern | Matches |
|-------------|---------------|---------|
| `TOPIC` | `^topic$` | topic, Topic, TOPIC |
| `QUESTION` | `^question$` | question, Question |
| `OPTION` | `^options?$` | option, options, Options |
| `ANSWER_KEY` | `^answer[\s_\-]?key$` | answerkey, answer_key, answer key |
| `CORRECT_ANSWER` | `^(?:correct[\s_\-]?)?(?:answer\|option)(?:[\s_\-]?key)?$` | answer, correctanswer, correct_answer, correct answer |
| `SOLUTION` | `^solution(?:[\s_\-]?explanation)?$` | solution, solutionexplanation, solution_explanation |
| `DISTRACTOR_ANALYSIS` | `^distractor[\s_\-]?analysis$` | distractoranalysis, distractor_analysis, distractor analysis |
| `KEY_IDEA` | `^key[\s_\-]?idea$` | keyidea, key_idea, key idea |
| `SUBQ` | `^(?:sub[\s_\-]?q(?:uestions?)?|parts?)$` | subq, sub_q, subquestions, parts |
| `DIAGRAM_PROMPT` | `^diagram[\s_\-]?prompt$` | diagramprompt, diagram_prompt, diagram prompt |
| `DOK` | `^dok(?:[\s_\-]?level)?$` | dok, doklevel, dok_level, dok level |
| `MARKS` | `^(?:mark(?:s)?|marking[\s_\-]?scheme)$` | marks, markingscheme, marking_scheme |
| `Q_TYPE` | `^(?:q[\s_\-]?type\|question[\s_\-]?type)$` | qtype, q_type, questiontype, question_type |

### 3. Pattern Ordering

**IMPORTANT:** More specific patterns must come before general patterns to prevent incorrect matches.

Example:
- `ANSWER_KEY` pattern must come **before** `CORRECT_ANSWER` pattern
- Otherwise, "answerkey" would match the broader `CORRECT_ANSWER` pattern first

### 4. Regex Quantifiers

- `[\s_\-]?` - Matches **zero or one** separator (space, underscore, or hyphen)
  - This handles both collapsed forms (`correctanswer`) and separated forms (`correct_answer`)
- `(?:...)?` - Optional non-capturing group
  - Used for optional words like "correct" in "correct answer" or "explanation" in "solution explanation"

## How It Works

1. **For each key in the JSON:**
   ```python
   for k, v in q.items():
       normalized_k = normalize_field(str(k))  # Normalize the key
       
       for pattern, standard_key in key_patterns:
           if re.match(pattern, normalized_k, re.IGNORECASE):
               normalized[standard_key] = v  # Map to standard key
               break
   ```

2. **If no pattern matches:** The original key is preserved

3. **Type inference:** If `Q_TYPE` is missing, it's inferred from specialized keys like `FIB_TYPE` or `MULTIPART_TYPE`

## Supported Variations

All of the following key formats are supported:

### CamelCase
- `DistractorAnalysis`
- `KeyIdea`
- `CorrectAnswer`
- `SolutionExplanation`

### Underscore-separated
- `distractor_analysis`
- `key_idea`
- `correct_answer`
- `solution_explanation`

### Hyphen-separated
- `distractor-analysis`
- `key-idea`
- `correct-answer`
- `solution-explanation`

### Space-separated
- `Distractor Analysis`
- `Key Idea`
- `Correct Answer`
- `Solution Explanation`

### Collapsed (no separators)
- `distractoranalysis`
- `keyidea`
- `correctanswer`
- `solutionexplanation`

### Mixed casing
- `DISTRACTOR_ANALYSIS`
- `Key_Idea`
- `Correct Answer`

## Testing

A comprehensive test suite (`test_key_normalization.py`) verifies:

1. **Field normalization:** Ensures the normalization function works correctly
2. **Pattern matching:** Tests all patterns against various input formats
3. **Full integration:** Tests complete question object normalization

Run tests with:
```bash
python test_key_normalization.py
```

All tests should pass with the message: "🎉 ALL TESTS PASSED! 🎉"

## Benefits

1. **Robustness:** Handles any key format Gemini produces
2. **Flexibility:** Easy to add new patterns for additional fields
3. **Maintainability:** Clear, well-documented regex patterns
4. **Performance:** Fast regex matching with early termination
5. **Reliability:** Comprehensive test coverage ensures correctness

## Future Enhancements

Potential improvements:
- Add fuzzy matching for misspelled keys
- Support for custom key mappings via configuration
- Logging for unmatched keys to identify new variations
- Performance optimization for very large JSON objects
