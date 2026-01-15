
from prompt_builder import build_prompt_for_batch
import logging

# Disable logging to keep output clean
logging.disable(logging.CRITICAL)

# Mock data
questions = [
    {
        'topic': 'Test Topic',
        'marks': 2.5,
        'dok': 3,
        'taxonomy': 'Evaluating',
        'new_concept_source': 'text',
        'additional_notes_source': 'none'
    }
]

general_config = {
    'grade': 'Grade 10',
    'subject': 'Mathematics',
    'chapter': 'Test Chapter',
    'new_concept': 'Test Concept',
    'additional_notes': 'Test Global Notes'
}

# Build prompt for Assertion-Reasoning
result = build_prompt_for_batch("Assertion-Reasoning", questions, general_config)
prompt = result['prompt']

with open("verify_output.txt", "w", encoding="utf-8") as f:
    for line in prompt.split('\n'):
        if "Test Topic" in line:
            f.write(line.strip() + "\n")
