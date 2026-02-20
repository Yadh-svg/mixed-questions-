
import streamlit as st
import json
from result_renderer import render_batch_results

# Mock data from user request
sample_data = {
  "math_core": {
    "math_cores": [
      {
        "id": "Q1",
        "Topic": "Linear Pair Axiom",
        "Subtopic": "Direct application...",
        "Question_Design": {
          "Description": "Find an unknown angle...",
          "Given": {"Angle1": "115"},
          "Find": "x"
        }
      }
    ]
  },
  "writer_output": {
    "questions": [
      {
        "question_id": "Q1",
        "question_text": "John is looking at a straight fence...",
        "options": {
          "A": "115",
          "B": "75",
          "C": "65",
          "D": "245"
        },
        "correct_option": "C",
        "solution": "1. Identify that the fence is a straight line...",
        "key_idea": "In problems where a ray meets a straight line...",
        "distractor_analysis": "| Option | Misconception |\n| :--- | :--- |\n| A | Error... |",
        "mcq_type": "Real-World Image-Based Word Questions",
        "mark": 2.0,
        "dok_level": 2,
        "taxonomy": "Applying",
        "statement_based": "NO",
        "diagram_prompt": "Draw a horizontal line..."
      }
    ]
  },
  "_pipeline_metadata": {
    "mode": "MATH_FIRST",
    "stages": 2
  }
}

st.title("MCQ Rendering Verification")

# Mock the session state structure expected by render_batch_results
if 'generated_output' not in st.session_state:
    st.session_state.generated_output = {}

# Call the renderer
st.write("Calling render_batch_results...")
try:
    # Wrap in expected structure
    result_data = {'text': json.dumps(sample_data)}
    render_batch_results("MCQ - Batch 1", result_data)
    st.success("Rendering completed successfully!")
except Exception as e:
    st.error(f"Rendering failed: {e}")
    import traceback
    st.text(traceback.format_exc())
