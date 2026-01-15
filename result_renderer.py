import streamlit as st
import json
import re
from typing import Dict, List, Any, Optional

def extract_json_objects(text: str) -> List[Dict[str, Any]]:
    """
    Robustly extract JSON objects from text by finding top-level brace pairs.
    """
    # Simply use brace matching on the whole text. 
    # This covers JSONs inside markdown blocks and raw JSONs.
    return extract_json_by_braces(text)

def extract_json_by_braces(text: str) -> List[Dict[str, Any]]:
    """
    Extract JSON objects by finding matching braces.
    """
    objects = []
    stack = []
    start_index = -1
    
    for i, char in enumerate(text):
        if char == '{':
            if not stack:
                start_index = i
            stack.append(char)
        elif char == '}':
            if stack:
                stack.pop()
                if not stack:
                    # Found a complete block
                    json_str = text[start_index:i+1]
                    try:
                        obj = json.loads(json_str)
                        if isinstance(obj, dict):
                            objects.append(obj)
                    except json.JSONDecodeError:
                        pass # Ignore invalid blocks
    return objects

def clean_key(key: str) -> str:
    """Helper to format keys for display."""
    return key.replace('_', ' ').title()

def render_mcq(q: Dict[str, Any], index: int):
    """Render MCQ Question."""
    st.markdown(f"#### Q{index}: {q.get('TOPIC', 'MCQ')} ({q.get('TYPE', '')})")
    
    # Diagram Prompt
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
    
    # Question
    # Question
    st.markdown(f"{q.get('QUESTION', '')}")
    
    # Options
    options = q.get('OPTION', {})
    if options:
        for key, value in options.items():
            st.markdown(f"- **{key})** {value}")
    
    # Solution & Analysis
    with st.expander("👁️ View Solution & Analysis"):
        st.markdown(f"**Correct Answer:** {q.get('CORRECT_ANSWER', '')}")
        st.markdown(f"**Key Idea:** {q.get('KEY_IDEA', '')}")
        st.markdown("---")
        st.markdown("**Solution:**")
        st.markdown(q.get('SOLUTION', ''))
        
        st.markdown("---")
        st.markdown("**Distractor Analysis:**")
        da = q.get('DISTRACTOR_ANALYSIS', '')
        # If DA is a table string, render it as markdown
        st.markdown(da)
        
        if q.get('validation_report'):
            st.markdown("---")
            st.caption(f"Validation Report: {q['validation_report']}")

def render_case_study(q: Dict[str, Any], index: int):
    """Render Case Study."""
    # Normalization for Generator Schema (CBS Material X / Item Questions)
    # If standard keys are missing, try to extract from generator format
    if not q.get('SCENARIO') and not q.get('SUBQ'):
        # Attempt to find 'CBS Material' keys
        cbs_data = None
        for key in q.keys():
            if 'CBS Material' in key:
                cbs_data = q[key]
                break
        
        if cbs_data:
            q['SCENARIO'] = cbs_data.get('Scenario', '')
            q['DIAGRAM_PROMPT'] = cbs_data.get('Diagram Prompt', q.get('DIAGRAM_PROMPT'))
            
            # Normalize Sub-questions
            item_qs = cbs_data.get('Item Questions', {})
            answer_key = cbs_data.get('Answer Key', {})
            subqs = []
            
            for part_key, question_text in item_qs.items():
                # Clean part key (e.g., "(a)" -> "a")
                safe_part = part_key.replace('(', '').replace(')', '').strip()
                
                # Try to find corresponding answer/solution in Answer Key
                ans_data = answer_key.get(part_key, {})
                # It might be a dict or string
                solution_text = ""
                marks = ""
                
                if isinstance(ans_data, dict):
                    solution_text = ans_data.get('Solution', '')
                    marks = ans_data.get('Marking Scheme', '')
                    # Sometimes answer is explicitly in the dict, or implied in solution
                    answer_text = solution_text # Fallback
                else:
                    answer_text = str(ans_data)
                
                subqs.append({
                    'part': safe_part,
                    'question': question_text,
                    'answer': answer_text,
                    'marks': marks,
                    'dok': q.get('DOK Level', '') # Fallback to global DOK
                })
            q['SUBQ'] = subqs
            q['KEY_IDEA'] = cbs_data.get('Key Idea', q.get('Key Idea', ''))

    st.markdown(f"#### Q{index}: Case Study - {q.get('TOPIC', q.get('Topic', ''))}")
    
    st.markdown(f"**Scenario:**")
    st.markdown(f"> {q.get('SCENARIO', '')}")
    
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
    
    if q.get('QUESTION'):
         st.markdown(f"{q.get('QUESTION', '')}")

    # Subquestions
    subqs = q.get('SUBQ', [])
    if subqs:
        st.markdown("**Sub-Questions:**")
        for sq in subqs:
            part = sq.get('part', '')
            txt = sq.get('question', '')
            marks = sq.get('marks', '')
            dok = sq.get('dok', '')
            st.markdown(f"- **({part})** {txt} *(Marks: {marks}, DOK: {dok})*")
    
    with st.expander("👁️ View Solution"):
        st.markdown(f"**Correct Answer:** {q.get('CORRECT_ANSWER', '')}")
        
        if subqs:
             st.markdown("**Sub-Question Solutions:**")
             for sq in subqs:
                 st.markdown(f"- **({sq.get('part')})** {sq.get('answer', '')}")

        st.markdown("---")
        st.markdown("**Detailed Solution:**")
        st.markdown(q.get('SOLUTION', ''))
        st.markdown(f"**Key Idea:** {q.get('KEY_IDEA', '')}")
        
        if q.get('validation_report'):
            st.caption(f"Validation Report: {q['validation_report']}")

def render_fib(q: Dict[str, Any], index: int):
    """Render Fill in the Blanks."""
    st.markdown(f"#### Q{index}: Fill in the Blanks - {q.get('TOPIC', '')}")
    
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
        
    st.markdown(f"{q.get('QUESTION', '')}")
    
    subqs = q.get('SUBQ', [])
    if subqs:
        for sq in subqs:
             st.markdown(f"- **({sq.get('part', '')})** {sq.get('question', '')}")

    with st.expander("👁️ View Solution"):
        st.markdown("**Detailed Solution:**")
        st.markdown(q.get('SOLUTION', ''))
        st.markdown(f"**Correct Answer:** {q.get('CORRECT_ANSWER', '')}")
        st.markdown(f"**Key Idea:** {q.get('KEY_IDEA', '')}")
        
        if subqs:
             st.markdown("**Part Answers:**")
             for sq in subqs:
                 st.markdown(f"- **({sq.get('part')})** {sq.get('answer', '')}")
        
        if q.get('validation_report'):
            st.caption(f"Validation Report: {q['validation_report']}")

def render_multipart(q: Dict[str, Any], index: int):
    """Render Multi-Part Question."""
    st.markdown(f"#### Q{index}: Multi-Part - {q.get('TOPIC', '')}")
    
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
        
    st.markdown(f"{q.get('QUESTION', '')}")
    
    subqs = q.get('SUBQ', [])
    if subqs:
        for sq in subqs:
            st.markdown(f"- **({sq.get('part', '')})** {sq.get('question', '')} *(Marks: {sq.get('marks')}, DOK: {sq.get('dok')})*")

    with st.expander("👁️ View Solution"):
        st.markdown("**Detailed Solution:**")
        st.markdown(q.get('SOLUTION', ''))
        
        st.markdown("**Part Answers:**")
        if subqs:
             for sq in subqs:
                 st.markdown(f"- **({sq.get('part')})** {sq.get('answer', '')}")
        
        if q.get('DISTRACTOR_ANALYSIS'):
             st.markdown("---")
             st.markdown("**Distractor Analysis:**")
             st.markdown(q['DISTRACTOR_ANALYSIS'])

        st.markdown(f"**Key Idea:** {q.get('KEY_IDEA', '')}")
        if q.get('validation_report'):
            st.caption(f"Validation Report: {q['validation_report']}")

def render_ar(q: Dict[str, Any], index: int):
    """Render Assertion-Reasoning."""
    st.markdown(f"#### Q{index}: Assertion-Reasoning - {q.get('TOPIC', '')}")
    
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
        
    st.markdown(f"{q.get('QUESTION', '')}")
    
    options = q.get('OPTION', {})
    if options:
        for key, value in options.items():
            st.markdown(f"- **{key})** {value}")

    with st.expander("👁️ View Solution"):
        st.markdown(f"**Correct Answer:** {q.get('CORRECT_ANSWER', '')}")
        st.markdown("**Reasoning:**")
        st.markdown(q.get('SOLUTION', ''))
        
        if q.get('DISTRACTOR_ANALYSIS'):
            st.markdown("---")
            st.markdown("**Distractor Analysis:**")
            st.markdown(q['DISTRACTOR_ANALYSIS'])
            
        st.markdown(f"**Key Idea:** {q.get('KEY_IDEA', '')}")
        if q.get('validation_report'):
            st.caption(f"Validation Report: {q['validation_report']}")

def render_descriptive(q: Dict[str, Any], index: int):
    """Render Descriptive."""
    st.markdown(f"#### Q{index}: Descriptive - {q.get('TOPIC', '')}")
    
    if q.get('SCENARIO'):
        st.markdown(f"> {q['SCENARIO']}")
        
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
        
    st.markdown(f"{q.get('QUESTION', '')}")

    with st.expander("👁️ View Solution"):
        st.markdown(f"**Answer:** {q.get('CORRECT_ANSWER', '')}")
        st.markdown("**Detailed Solution:**")
        st.markdown(q.get('SOLUTION', ''))
        st.markdown(f"**Key Idea:** {q.get('KEY_IDEA', '')}")
        if q.get('validation_report'):
            st.caption(f"Validation Report: {q['validation_report']}")

def render_descriptive_subq(q: Dict[str, Any], index: int):
    """Render Descriptive with Subquestions."""
    st.markdown(f"#### Q{index}: Descriptive (Sub-Q) - {q.get('TOPIC', '')}")
    
    if q.get('SCENARIO'):
        st.markdown(f"> {q['SCENARIO']}")
        
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
        
    st.markdown(f"{q.get('QUESTION', '')}")
    
    subqs = q.get('SUBQ', [])
    if subqs:
        for sq in subqs:
             st.markdown(f"- **({sq.get('part', '')})** {sq.get('question', '')}")

    with st.expander("👁️ View Solution"):
        st.markdown(f"**Main Answer:** {q.get('CORRECT_ANSWER', '')}")
        st.markdown("**Detailed Solution:**")
        st.markdown(q.get('SOLUTION', ''))
        
        if subqs:
             st.markdown("**Sub-Question Answers:**")
             for sq in subqs:
                 st.markdown(f"- **({sq.get('part')})** {sq.get('answer', '')}")
                 
        st.markdown(f"**Key Idea:** {q.get('KEY_IDEA', '')}")
        if q.get('validation_report'):
            st.caption(f"Validation Report: {q['validation_report']}")

def render_batch_results(batch_key: str, result_data: Dict[str, Any]):
    """
    Main entry point to render a batch of results.
    """
    # Prefer validated text, fallback to raw
    text_content = result_data.get('text', '')
    if not text_content:
        st.warning("No content to display.")
        return

    # Extract JSONs
    questions = extract_json_objects(text_content)
    
    if not questions:
        st.warning(f"⚠️ Could not parse structured output for {batch_key}. Showing raw text below.")
        st.text(text_content)
        return

    st.success(f"Successfully parsed {len(questions)} questions.")

    for i, q in enumerate(questions, 1):
        st.markdown("---")
        
        # Unwrap validation response if present
        validation_report = q.get('VALIDATION_REPORT')
        validation_status = q.get('STATUS')
        
        if 'CORRECTED_ITEM' in q:
            q = q['CORRECTED_ITEM']
            # Inject validation info back into the unwrapped object so renderers can see it
            if validation_report:
                q['validation_report'] = validation_report
            if validation_status:
                q['validation_status'] = validation_status
        
        # Dispatch based on Q_TYPE or infer from structure keys
        q_type = q.get('Q_TYPE', '').upper()
        
        # Fallback detection if Q_TYPE is missing or generic
        if not q_type:
            if 'MCQ' in q: q_type = 'MCQ'
            elif 'Case_Study' in q or any(k.startswith('CBS Material') for k in q.keys()): q_type = 'CASESTUDY'
            elif 'FIB' in q: q_type = 'FIB'
            elif 'Multi_Part' in q: q_type = 'MULTIPART'
            elif 'A&R' in q: q_type = 'ASSERTION_REASONING'
            elif 'Descriptive' in q: q_type = 'DESCRIPTIVE'
            elif 'Descriptive_w_subq' in q: q_type = 'DESCRIPTIVE_SUBQ'

        if q_type == 'MCQ':
            render_mcq(q, i)
        elif q_type == 'CASESTUDY':
            render_case_study(q, i)
        elif q_type == 'FIB':
            render_fib(q, i)
        elif q_type == 'MULTIPART':
            render_multipart(q, i)
        elif q_type == 'ASSERTION_REASONING':
            render_ar(q, i)
        elif q_type == 'DESCRIPTIVE':
            render_descriptive(q, i)
        elif q_type == 'DESCRIPTIVE_SUBQ':
            render_descriptive_subq(q, i)
        else:
            # Generic fallback
            st.markdown(f"#### Question {i}")
            st.json(q)
