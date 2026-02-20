
import logging
from pipeline_builder import build_math_core_prompt, build_writer_prompt

# Mock data
questions = [
    {
        'topic': 'Test Topic',
        'type': 'MCQ',
        'mcq_type': 'Image Based',
        'taxonomy': 'Analyzing',
        'statement_based': True,
        'dok': 2,
        'marks': 2.0,
        'subparts': []
    }
]

general_config = {
    'grade': 'Grade 10',
    'subject': 'Math',
    'api_key': 'dummy'
}

def test_prompts():
    output = []
    output.append("Testing Math Core Prompt (MCQ Mode)...")
    try:
        res = build_math_core_prompt(questions, general_config)
        output.append("--- MATH CORE PROMPT START ---")
        output.append(res['prompt'])
        output.append("--- MATH CORE PROMPT END ---")
        
        output.append("\n\nTesting Writer Prompt (MCQ Mode)...")
        math_core_data = {"math_cores": [{"id": "Q1", "Topic": "Test Topic"}]}
        res2 = build_writer_prompt(math_core_data, questions, general_config)
        output.append("--- WRITER PROMPT START ---")
        output.append(res2['prompt'])
        output.append("--- WRITER PROMPT END ---")
        
    except Exception as e:
        output.append(f"ERROR: {str(e)}")

    with open("verification_result_2.txt", "w", encoding='utf-8') as f:
        f.write("\n".join(output))

if __name__ == "__main__":
    test_prompts()
