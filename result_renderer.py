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



def normalize_question(q: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize keys and infer Q_TYPE to handle inconsistent JSON output.
    Uses regex patterns for flexible key matching.
    """
    normalized = {}
    
    # Regex-based key patterns (pattern -> standard key)
    # These patterns are case-insensitive and flexible with spaces/underscores
    key_patterns = [
        # Topic variations
        (r'^topic$', 'TOPIC'),
        (r'^topic[\s_]*used$', 'TOPIC'),
        
        # Question variations
        (r'^question$', 'QUESTION'),
        
        # Options variations
        (r'^options?$', 'OPTION'),
        
        # Answer variations
        (r'^(?:correct[\s_]*)?(?:answer|option)$', 'CORRECT_ANSWER'),
        (r'^answer[\s_]*key$', 'ANSWER_KEY'),
        
        # Solution variations - THIS IS THE KEY FIX
        (r'^solution(?:[\s_]*explanation)?$', 'SOLUTION'),
        
        # Distractor Analysis variations
        (r'^distractor[\s_]*analysis$', 'DISTRACTOR_ANALYSIS'),
        
        # Key Idea variations
        (r'^key[\s_-]*idea$', 'KEY_IDEA'),
        
        # Scenario variations
        (r'^scenario$', 'SCENARIO'),
        
        # Diagram variations
        (r'^diagram[\s_]*prompt$', 'DIAGRAM_PROMPT'),
        
        # DOK variations
        (r'^dok(?:[\s_]*level)?$', 'DOK'),
        
        # Taxonomy variations
        (r'^taxonomy$', 'TAXONOMY'),
        
        # Marks variations
        (r'^(?:marking[\s_]*scheme|marks?)$', 'MARKS'),
        
        # Subquestions variations
        (r'^(?:sub[\s_]*q(?:uestions)?|parts)$', 'SUBQ'),
        
        # Question type variations
        (r'^(?:q[\s_]*type|question[\s_]*type)$', 'Q_TYPE'),
        (r'^fib[\s_]*type$', 'FIB_TYPE'),
        (r'^multipart[\s_]*type$', 'MULTIPART_TYPE'),
    ]

    for k, v in q.items():
        # Normalize the key for pattern matching
        clean_k = str(k).lower().replace('_', ' ').strip()
        clean_k = re.sub(r'\s+', ' ', clean_k)  # Normalize multiple spaces
        
        # Try to match against patterns
        matched = False
        for pattern, standard_key in key_patterns:
            if re.match(pattern, clean_k, re.IGNORECASE):
                normalized[standard_key] = v
                matched = True
                break
        
        # If no pattern matched, keep the original key
        if not matched:
            normalized[k] = v
            
    # Infer Q_TYPE from specialized type keys if explicit Q_TYPE is missing
    if 'Q_TYPE' not in normalized:
        if 'FIB_TYPE' in normalized:
            normalized['Q_TYPE'] = 'FIB'
        elif 'MULTIPART_TYPE' in normalized:
            normalized['Q_TYPE'] = 'MULTIPART'

    # Normalization for FIB and MULTIPART to create SUBQ from ANSWER_KEY if needed
    q_type_upper = normalized.get('Q_TYPE', '').upper()
    
    if q_type_upper in ['FIB', 'MULTIPART'] and 'SUBQ' not in normalized and 'ANSWER_KEY' in normalized:
        ak = normalized['ANSWER_KEY']
        subqs = []
        if isinstance(ak, dict):
            for key, val in ak.items():
                # For FIB: key might be "TEXT 1", val might be answer string
                # For Multipart: key might be "(a)", val might be dict with Solution/Final Answer
                
                sq = {'part': key}
                if isinstance(val, dict):
                    # Complex answer key (Multipart)
                    sq['answer'] = val.get('Final Answer', val.get('Solution', ''))
                    sq['solution'] = val.get('Solution', '') # Store full solution if available
                    sq['marks'] = val.get('Marking Scheme', '')
                else:
                    # Simple answer (FIB)
                    sq['answer'] = str(val)
                
                # Try to extract question text for this part if possible
                # (This is harder without a structured question input, but we do what we can)
                # Maybe the question text is embedded in the main question? 
                # For Multipart, usually the question has (a)... (b)... 
                # We can leave 'question' empty in SUBQ and rely on the main text, 
                # OR try to parse the main text. For now, let's at least populate the answer.
                
                subqs.append(sq)
        
        # Sort subqs if possible (by part name)
        # e.g. (a), (b) or TEXT 1, TEXT 2
        try:
            subqs.sort(key=lambda x: x['part'])
        except:
            pass
            
        normalized['SUBQ'] = subqs
    
    return normalized

def clean_key(key: str) -> str:
    """Helper to format keys for display."""
    return key.replace('_', ' ').title()

def format_multiline(text: Any) -> str:
    """
    Ensure newlines are rendered correctly in Markdown.
    Replaces single newlines with double newlines or two spaces for hard breaks.
    """
    if not text:
        return ""
    
    # Handle dicts or other types gracefully
    if isinstance(text, dict):
        return json.dumps(text, indent=2)
    
    text = str(text)
    
    # Specific fix for Assertion-Reasoning spacing
    # Look for "Reason (R):" following an assertion and force a newline
    text = re.sub(r'(Assertion\s*\(A\):.*?)(\s+Reason\s*\(R\):)', r'\1\n\n\2', text, flags=re.DOTALL)
    
    # General structural formatting
    # Force newlines before common markers if they don't have one
    patterns = [
        r'((?:\*\*|__)?\s*Step\s+\d+:)',          # Step 1: or **Step 1:
        r'((?:\*\*|__)?\s*Statement\s+[IVX0-9]+:)', # Statement I:
        r'((?:\*\*|__)?\s*Note:)',                # Note:
        r'((?:\*\*|__)?\s*Conclusion:)',          # Conclusion:
        r'((?:\*\*|__)?\s*Explanation:)',         # Explanation:
        r'((?:\*\*|__)?\bPart\s+\([a-zA-Z0-9]+\):)' # Part (a):
    ]
    
    for pattern in patterns:
        # Replace "match" with "\n\nmatch", avoiding adding extra newlines if already present
        # The lookbehind (?<!\n\n) is hard to use with variable length, so we substitute and then cleanup
        text = re.sub(pattern, r'\n\n\1', text)

    # Check for Markdown Tables (lines starting with |)
    # If it looks like a table, we should likely NOT force double newlines globally
    stripped_lines = [l.strip() for l in text.split('\n') if l.strip()]
    if any(l.startswith('|') and '|' in l[1:] for l in stripped_lines):
         # It has table rows. We should be careful.
         # For tables, we usually don't want to mess with newlines inside the table structure.
         # But we might still want the "Section:" headers to break.
         # Strategy: Apply headers fix, but skip general newline doubling.
         pass
    else:
        # General text - use soft breaks (two spaces + newline) to preserve bold context
        # UNLESS it's a structural break we inserted above.
        # But we already handled structural breaks with \n\n.
        # So we just want to ensure other single newlines become visible soft breaks.
        text = text.replace('\n', '  \n')

    return text.strip()

def render_mcq(q: Dict[str, Any], index: int):
    """Render MCQ Question."""
    st.markdown(f"#### Q{index}: {q.get('TOPIC', 'MCQ')} ({q.get('TYPE', '')})")
    
    # Diagram Prompt
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
    
    # Question
    st.markdown(format_multiline(q.get('QUESTION', '')))
    
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
        st.markdown(f"**Solution:**")
        st.markdown(format_multiline(q.get('SOLUTION', '')))
        
        st.markdown("---")
        st.markdown("**Distractor Analysis:**")
        da = q.get('DISTRACTOR_ANALYSIS', '')
        # If DA is a table string, render it as markdown
        st.markdown(format_multiline(da))
        
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
    st.markdown(f"> {format_multiline(q.get('SCENARIO', ''))}")
    
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
    
    if q.get('QUESTION'):
         st.markdown(format_multiline(q.get('QUESTION', '')))

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
                 st.markdown(f"- **({sq.get('part')})** {format_multiline(sq.get('answer', ''))}")

        st.markdown("---")
        st.markdown("**Detailed Solution:**")
        st.markdown(format_multiline(q.get('SOLUTION', '')))
        st.markdown(f"**Key Idea:** {q.get('KEY_IDEA', '')}")
        
        if q.get('validation_report'):
            st.caption(f"Validation Report: {q['validation_report']}")

def render_fib(q: Dict[str, Any], index: int):
    """Render Fill in the Blanks."""
    st.markdown(f"#### Q{index}: Fill in the Blanks - {q.get('TOPIC', '')}")
    
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
        
    st.markdown(format_multiline(q.get('QUESTION', '')))
    
    subqs = q.get('SUBQ', [])
    if subqs:
        for sq in subqs:
             if sq.get('question'):
                 st.markdown(f"- **({sq.get('part', '')})** {sq.get('question', '')}")

    with st.expander("👁️ View Solution"):
        st.markdown("**Detailed Solution:**")
        st.markdown(format_multiline(q.get('SOLUTION', '')))
        st.markdown(f"**Correct Answer:** {q.get('CORRECT_ANSWER', '')}")
        st.markdown(f"**Key Idea:** {q.get('KEY_IDEA', '')}")
        
        if subqs:
             st.markdown("**Part Answers:**")
             for sq in subqs:
                 st.markdown(f"- **({sq.get('part')})** {format_multiline(sq.get('answer', ''))}")
        
        if q.get('validation_report'):
            st.caption(f"Validation Report: {q['validation_report']}")

def render_multipart(q: Dict[str, Any], index: int):
    """Render Multi-Part Question."""
    st.markdown(f"#### Q{index}: Multi-Part - {q.get('TOPIC', '')}")
    
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
        
    st.markdown(format_multiline(q.get('QUESTION', '')))
    
    subqs = q.get('SUBQ', [])
    if subqs:
        for sq in subqs:
            if sq.get('question'):
                st.markdown(f"- **({sq.get('part', '')})** {sq.get('question', '')} *(Marks: {sq.get('marks')}, DOK: {sq.get('dok')})*")

    with st.expander("👁️ View Solution"):
        st.markdown("**Detailed Solution:**")
        st.markdown(format_multiline(q.get('SOLUTION', '')))
        
        st.markdown("**Part Answers:**")
        if subqs:
             for sq in subqs:
                 st.markdown(f"- **({sq.get('part')})** {format_multiline(sq.get('answer', ''))}")
        
        if q.get('DISTRACTOR_ANALYSIS'):
             st.markdown("---")
             st.markdown("**Distractor Analysis:**")
             st.markdown(format_multiline(q['DISTRACTOR_ANALYSIS']))

        st.markdown(f"**Key Idea:** {q.get('KEY_IDEA', '')}")
        if q.get('validation_report'):
            st.caption(f"Validation Report: {q['validation_report']}")

def render_ar(q: Dict[str, Any], index: int):
    """Render Assertion-Reasoning."""
    st.markdown(f"#### Q{index}: Assertion-Reasoning - {q.get('TOPIC', '')}")
    
    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")
        
    st.markdown(format_multiline(q.get('QUESTION', '')))
    
    options = q.get('OPTION', {})
    if options:
        for key, value in options.items():
            st.markdown(f"- **{key})** {value}")

    with st.expander("👁️ View Solution"):
        st.markdown(f"**Correct Answer:** {q.get('CORRECT_ANSWER', '')}")
        st.markdown("**Reasoning:**")
        st.markdown(format_multiline(q.get('SOLUTION', '')))
        
        if q.get('DISTRACTOR_ANALYSIS'):
            st.markdown("---")
            st.markdown("**Distractor Analysis:**")
            st.markdown(format_multiline(q['DISTRACTOR_ANALYSIS']))
            
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
        
    st.markdown(format_multiline(q.get('QUESTION', '')))

    with st.expander("👁️ View Solution"):
        st.markdown(f"**Answer:** {q.get('CORRECT_ANSWER', '')}")
        st.markdown("**Detailed Solution:**")
        st.markdown(format_multiline(q.get('SOLUTION', '')))
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
        
    st.markdown(format_multiline(q.get('QUESTION', '')))
    
    subqs = q.get('SUBQ', [])
    if subqs:
        for sq in subqs:
             st.markdown(f"- **({sq.get('part', '')})** {sq.get('question', '')}")

    with st.expander("👁️ View Solution"):
        st.markdown(f"**Main Answer:** {q.get('CORRECT_ANSWER', '')}")
        st.markdown("**Detailed Solution:**")
        st.markdown(format_multiline(q.get('SOLUTION', '')))
        
        if subqs:
             st.markdown("**Sub-Question Answers:**")
             for sq in subqs:
                 st.markdown(f"- **({sq.get('part')})** {format_multiline(sq.get('answer', ''))}")
                 
        st.markdown(f"**Key Idea:** {q.get('KEY_IDEA', '')}")
        if q.get('validation_report'):
            st.caption(f"Validation Report: {q['validation_report']}")

def render_generic(q: Dict[str, Any], index: int):
    """Fallback renderer that attempts to display content nicely."""
    topic = q.get('TOPIC', '')
    st.markdown(f"#### Q{index}: {topic if topic else 'Question'}")
    
    if q.get('SCENARIO'):
        st.markdown(f"> {format_multiline(q['SCENARIO'])}")

    if q.get('DIAGRAM_PROMPT'):
        st.info(f"🖼️ **Diagram Prompt:** {q['DIAGRAM_PROMPT']}")

    # Render Question
    q_text = q.get('QUESTION', '')
    if q_text:
        st.markdown(format_multiline(q_text))
    
    # Try to render options if present (like MCQ fallback)
    options = q.get('OPTION', {})
    if options and isinstance(options, dict):
        for key, value in options.items():
            st.markdown(f"- **{key})** {value}")

    # Try to verify if there are subquestions (like Multipart fallback)
    subqs = q.get('SUBQ', [])
    if subqs and isinstance(subqs, list):
        for sq in subqs:
             part = sq.get('part', '')
             txt = sq.get('question', '')
             if txt:
                 st.markdown(f"- **({part})** {txt} *(Marks: {sq.get('marks', '')})*")

    # Solution Expander
    with st.expander("👁️ View Solution"):
        if q.get('CORRECT_ANSWER'):
             st.markdown(f"**Correct Answer:** {q['CORRECT_ANSWER']}")
        
        if q.get('SOLUTION'):
            st.markdown("**Detailed Solution:**")
            st.markdown(format_multiline(q['SOLUTION']))
        
        # Subquestion answers
        if subqs and isinstance(subqs, list):
             st.markdown("**Part Answers:**")
             for sq in subqs:
                 ans = sq.get('answer', '')
                 if ans:
                     st.markdown(f"- **({sq.get('part', '')})** {format_multiline(ans)}")

        if q.get('KEY_IDEA'):
            st.markdown(f"**Key Idea:** {q['KEY_IDEA']}")
            
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
        
        # Normalize keys and infer type
        q = normalize_question(q)
        
        # Dispatch based on Q_TYPE or infer from structure keys
        q_type = q.get('Q_TYPE', '').upper()
        
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
            # Generic fallback - Render decently instead of raw JSON
            render_generic(q, i)
