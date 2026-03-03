"""
Simplified Result Renderer for Streamlit Question Display
Renders questions in the new simplified format: { "question1": "markdown", "question2": "markdown" }
Question type is inferred from batch_key parameter.
"""
import streamlit as st
import json
import re
import html
from typing import Dict, List, Any, Optional


def extract_json_objects(text: str) -> List[Dict[str, Any]]:
    """
    Robustly extract JSON objects from text using json.JSONDecoder.
    This handles braces inside strings correctly, unlike simple stack counting.
    """
    objects = []
    decoder = json.JSONDecoder()
    pos = 0
    length = len(text)
    
    while pos < length:
        # Find the next opening brace
        try:
            # Skip whitespace
            while pos < length and text[pos].isspace():
                pos += 1
            if pos >= length:
                break
                
            if text[pos] != '{':
                # Skip until next brace
                pos = text.find('{', pos)
                if pos == -1:
                    break
            
            # Attempt to decode from this position
            obj, end_pos = decoder.raw_decode(text, idx=pos)
            if isinstance(obj, dict):
                objects.append(obj)
            pos = end_pos
            
        except json.JSONDecodeError:
            # If decoding failed, advance past the current '{' and try again
            # efficiently advance to next '{'
            pos += 1
            
    return objects


def extract_question_values_fallback(json_objects: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    ERROR HANDLING: Extract values from keys containing "question" (case-insensitive).
    This acts as a fallback when structural mismatch occurs.
    
    Args:
        json_objects: List of parsed JSON objects
        
    Returns:
        Dict mapping question keys to their string values
    """
    questions_dict = {}
    
    for obj in json_objects:
        if not isinstance(obj, dict):
            continue
            
        # Flatten nested structures if needed
        def flatten_dict(d: Dict[str, Any], parent_key: str = '') -> Dict[str, Any]:
            """Recursively flatten nested dicts"""
            items = {}
            for k, v in d.items():
                new_key = f"{parent_key}.{k}" if parent_key else k
                if isinstance(v, dict):
                    items.update(flatten_dict(v, new_key))
                else:
                    items[new_key] = v
            return items
        
        flattened = flatten_dict(obj)
        
        # Extract any keys containing "question" (case-insensitive)
        for key, value in flattened.items():
            # Case-insensitive match for "question"
            if re.search(r'question', key, re.IGNORECASE):
                # Only accept string values for rendering
                if isinstance(value, str):
                    questions_dict[key] = value
                elif isinstance(value, dict):
                    # If it's a dict, try to extract a "question" sub-key
                    for sub_key, sub_value in value.items():
                        if re.search(r'question', sub_key, re.IGNORECASE) and isinstance(sub_value, str):
                            questions_dict[f"{key}.{sub_key}"] = sub_value
    
    return questions_dict



def unescape_json_string(s: str) -> str:
    """Safely unescape JSON-escaped strings (convert \\n to real newlines, etc.)"""
    try:
        # Use json.loads to properly unescape the string
        escaped = s.replace('"', '\\"')
        return json.loads(f'"{escaped}"')
    except Exception:
        # Fallback: manual replacement of common escapes
        return s.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")


def normalize_llm_output_to_questions(text: str) -> Dict[str, str]:
    """
    SINGLE NORMALIZATION BOUNDARY: Converts ANY LLM validator output into:
    { "question1": "<markdown>", "question2": "<markdown>", ... }
    
    Handles all known LLM output variants:
    1. Correct: { "question1": "markdown..." }
    2. JSON string instead of object
    3. Wrapped/double-encoded JSON: { "question1": "{ \"question1\": \"...\" }" }
    4. Validation wrapper format: { "CORRECTED_ITEM": { "question1": "..." } }
    
    This is the ONLY place where LLM output parsing/normalization happens.
    After this function, we guarantee: Dict[str, str] where values are pure markdown.
    """
    # -------------------------------------------------------
    # STRIP MARKDOWN CODE FENCES (LLM often emits ```json)
    # -------------------------------------------------------
    if isinstance(text, str):
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?\s*```$", "", text)
    
    questions = {}
    
    # Step 1: Extract JSON objects from text
    json_objects = extract_json_objects(text)
    
    if not json_objects:
        # If no JSON found, try treating entire text as a question (rare fallback)
        return {"question1": text} if text.strip() else {}
    
    for obj in json_objects:
        if not isinstance(obj, dict):
            continue
        
        # Handle validation wrapper format (old format)
        if 'CORRECTED_ITEM' in obj or 'corrected_item' in obj:
            obj = obj.get('CORRECTED_ITEM') or obj.get('corrected_item')
        
        if not isinstance(obj, dict):
            continue
        
        for k, v in obj.items():
            # Only process keys matching question pattern
            if not re.match(r'^(question|q)\d+$', k, re.IGNORECASE):
                continue
            
            # Normalize the key to consistent questionX format
            num = re.search(r"\d+", k)
            if not num:
                continue
            normalized_key = f"question{num.group()}"
            
            # ---- VALUE NORMALIZATION ----
            if isinstance(v, str):
                s = v.strip()
                
                # Strip fences inside values (LLM may emit fenced JSON as value)
                if s.startswith("```"):
                    s = re.sub(r"^```(?:json)?\s*\n?", "", s, flags=re.IGNORECASE)
                    s = re.sub(r"\n?\s*```$", "", s)
                
                # Handle double-encoded JSON: value is a JSON string containing the actual question
                if s.startswith("{"):
                    try:
                        parsed = json.loads(s)
                        if isinstance(parsed, dict):
                            # Extract the first string value from the nested JSON
                            for inner_key, inner_v in parsed.items():
                                if isinstance(inner_v, str):
                                    questions[normalized_key] = unescape_json_string(inner_v)
                                    break
                            else:
                                # No string value found, use the original string
                                questions[normalized_key] = unescape_json_string(s)
                        else:
                            questions[normalized_key] = unescape_json_string(s)
                    except json.JSONDecodeError:
                        # Not valid JSON, treat as markdown (might just start with {)
                        questions[normalized_key] = unescape_json_string(s)
                else:
                    # Normal markdown string
                    questions[normalized_key] = unescape_json_string(s)
            
            elif isinstance(v, dict):
                # Value is a dict - try to extract markdown from known keys
                extracted = v.get('content') or v.get('value') or v.get('markdown') or v.get('text')
                if isinstance(extracted, str):
                    questions[normalized_key] = unescape_json_string(extracted)
                else:
                    # Fallback: take first string value
                    for inner_v in v.values():
                        if isinstance(inner_v, str):
                            questions[normalized_key] = unescape_json_string(inner_v)
                            break
                    else:
                        # Convert dict to JSON for debugging
                        questions[normalized_key] = json.dumps(v, indent=2)
    
    # Apply text replacements for Hindi to English
    for key in questions:
        questions[key] = questions[key].replace("ऑप्शंस", "OPTIONS")
    
    return questions


def render_markdown_question(question_key: str, markdown_content: str, question_type: str, batch_key: str = "", render_context: str = "results", is_regenerated: bool = False):
    """
    Render a single question from its markdown content.
    
    Args:
        question_key: The key (e.g., "question1", "question2")
        markdown_content: The complete markdown content
        question_type: The question type from batch_key
        batch_key: The batch identifier for session state management
        render_context: Context identifier ("progressive" or "results") to prevent duplicate keys
        is_regenerated: Whether to flag this as a regenerated question
    """
    # Extract question number from key (e.g., "question1" -> "1")
    q_num = question_key.replace("question", "").replace("q", "")
    
    # Create a header with question type and number
    type_emoji_map = {
        "MCQ": "☑️",
        "Fill in the Blanks": "📝",
        "Case Study": "📚",
        "Multi-Part": "📋",
        "Assertion-Reasoning": "🔗",
        "Descriptive": "✍️",
        "Descriptive w/ Subquestions": "📄"
    }
    
    # Extract base type for emoji lookup
    base_type = question_type.split(' - Batch ')[0] if question_type else ""
    emoji = type_emoji_map.get(base_type, "❓")
    
    # Create unique session state keys for this question with context namespace
    checkbox_key = f"duplicate_{render_context}_{batch_key}_{question_key}"
    count_key = f"duplicate_count_{render_context}_{batch_key}_{question_key}"
    duplicates_key = f"duplicates_{batch_key}_{question_key}"  # Shared across contexts
    
    # Initialize session state for duplicates if not exists
    if duplicates_key not in st.session_state:
        st.session_state[duplicates_key] = []
    
    # Only show duplication controls in "results" context, not in progressive rendering
    if render_context == "results":
        # Question header with checkbox (using Streamlit's built-in state management)
        col1, col2, col3, col4 = st.columns([0.6, 2.5, 1.5, 0.6])
        
        with col1:
            # Checkbox state is automatically managed by Streamlit via the key parameter
            duplicate_selected = st.checkbox(
                "Duplicate",
                key=checkbox_key,
                help="Select this question to generate duplicates"
            )
        
        with col2:
            regen_tag = " 🔄 *(Regenerated)*" if is_regenerated else ""
            st.markdown(f"### {emoji} Question {q_num}{regen_tag}")
            
            # Check for "newly generated" flag
            # We need to peek at the question data. Since we only have markdown_content here which might be a string,
            # we rely on the caller to handle this or we inspect the session state if available.
            # However, for simplicity, if the markdown_content is a dict (which we support), check there.
            # If it's a string, we can't easily check without extra args.
            # Let's handle the badge in the loop that calls this function, OR pass a flag.
            
            # Add "Select for Regeneration" checkbox
            regen_key = f"regen_select_{batch_key}_{q_num}"
            regen_selected = st.checkbox("Select for Regeneration", key=regen_key, help="Select to regenerate ONLY this question")
            
            if regen_selected:
                # Add to a global set of selected questions for regeneration
                if 'regen_selection' not in st.session_state:
                    st.session_state.regen_selection = set()
                st.session_state.regen_selection.add(f"{batch_key}:{q_num}")
                
                # Show reason input field when checkbox is selected
                regen_reason_key = f"regen_reason_{batch_key}_{q_num}"
                st.text_input(
                    "Reason for Regeneration (Optional)",
                    placeholder="e.g., Options are incorrect, off-topic, needs clarity...",
                    key=regen_reason_key,
                    help="Explain what needs to be fixed or changed in this question"
                )
            else:
                if 'regen_selection' in st.session_state:
                    st.session_state.regen_selection.discard(f"{batch_key}:{q_num}")
        
        with col3:
            if duplicate_selected:
                # Number input state is also automatically managed via key parameter
                st.number_input(
                    "# Duplicates",
                    min_value=1,
                    max_value=5,
                    value=1,
                    key=count_key,
                    help="Number of duplicates to generate"
                )
                
                # Additional Notes for Duplicates
                notes_key = f"duplicate_notes_{batch_key}_{question_key}"
                file_key = f"duplicate_file_{batch_key}_{question_key}"
                
                with st.expander("📝 Duplicate Customization (Text Notes & PDF)", expanded=False):
                    st.info("💡 You can use both notes and a file together. The AI will synthesize them.")
                    
                    st.text_area(
                        "Additional Instructions",
                        placeholder="e.g., Use the graph in the uploaded PDF but change values...",
                        key=notes_key,
                        height=70,
                        help="Specific instructions for these duplicates"
                    )
                    
                    st.file_uploader(
                        "Context File (PDF/Image)",
                        type=['pdf', 'png', 'jpg', 'jpeg', 'webp'],
                        key=file_key,
                        help="Upload a file to provide context. Can be used along with text notes."
                    )
        
        with col4:
            # Add copy-to-clipboard button with markdown stripping
            import streamlit.components.v1 as components
            import json
            
            copy_button_key = f"copy_{render_context}_{batch_key}_{question_key}"
            
            # HTML-escape the content to prevent breaking the HTML structure
            escaped_content = html.escape(markdown_content)
            
            copy_html = f"""
            <div style="display: flex; align-items: center; justify-content: center; height: 50px;">
                <textarea id="text_{copy_button_key}" style="position: absolute; left: -9999px;">{escaped_content}</textarea>
                <button id="btn_{copy_button_key}" 
                        style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                               color: white;
                               border: none;
                               border-radius: 8px;
                               padding: 10px 14px;
                               font-size: 18px;
                               cursor: pointer;
                               transition: all 0.3s ease;
                               box-shadow: 0 2px 4px rgba(0,0,0,0.1);"
                        title="Copy to clipboard (plain text, tables preserved)">
                    📋
                </button>
            </div>
            <script>
                (function() {{
                    const btn = document.getElementById('btn_{copy_button_key}');
                    const textarea = document.getElementById('text_{copy_button_key}');
                    
                    btn.addEventListener('click', function() {{
                        try {{
                            // Get original content
                            const originalText = textarea.value;
                            
                            // Create temporary textarea with original text
                            const tempTextarea = document.createElement('textarea');
                            tempTextarea.value = originalText;
                            tempTextarea.style.position = 'fixed';
                            tempTextarea.style.left = '-9999px';
                            document.body.appendChild(tempTextarea);
                            
                            // Copy cleaned text
                            tempTextarea.select();
                            tempTextarea.setSelectionRange(0, 99999);
                            document.execCommand('copy');
                            
                            // Clean up
                            document.body.removeChild(tempTextarea);
                            
                            // Visual feedback
                            btn.innerHTML = '✅';
                            btn.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';
                            
                            setTimeout(function() {{
                                btn.innerHTML = '📋';
                                btn.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
                            }}, 1500);
                        }} catch(err) {{
                            btn.innerHTML = '❌';
                            setTimeout(function() {{
                                btn.innerHTML = '📋';
                            }}, 1500);
                        }}
                    }});
                    
                    btn.addEventListener('mouseover', function() {{
                        this.style.transform = 'translateY(-2px)';
                        this.style.boxShadow = '0 4px 12px rgba(102, 126, 234, 0.4)';
                    }});
                    
                    btn.addEventListener('mouseout', function() {{
                        this.style.transform = 'translateY(0)';
                        this.style.boxShadow = '0 2px 4px rgba(0,0,0,0.1)';
                    }});
                }})();
            </script>
            """
            components.html(copy_html, height=55)
    else:
        # Progressive rendering - no duplication controls
        st.markdown(f"### {emoji} Question {q_num}")
    
    st.caption(f"*Type: {question_type}*")
    st.markdown("")  # spacing
    
    # Render the markdown content directly
    # Fix: Replace single newlines with double newlines for proper markdown rendering
    # This ensures OPTIONS and other sections render with proper line breaks
    
    # Normalize Windows line endings (important safeguard)
    markdown_content = markdown_content.replace('\r\n', '\n')
    
    # Convert ONLY isolated single newlines into Markdown hard breaks
    rendered_content = re.sub(r'(?<!\n)\n(?!\n)', '  \n', markdown_content)
    
    st.markdown(rendered_content)
    
    # Display duplicates if they exist (only in results context)
    if render_context == "results" and st.session_state[duplicates_key]:
        st.markdown("")
        st.markdown("---")
        st.markdown(f"**🔄 Duplicates ({len(st.session_state[duplicates_key])})**")
        
        for i, duplicate in enumerate(st.session_state[duplicates_key], 1):
            dup_question_key = duplicate.get('question_code', f'{question_key}-dup-{i}')
            
            # Get the markdown content from the duplicate
            if 'markdown' in duplicate:
                dup_markdown = duplicate['markdown']
            else:
                dup_content_key = [k for k in duplicate.keys() if k != 'question_code'][0] if len(duplicate.keys()) > 1 else 'question1'
                dup_markdown = duplicate.get(dup_content_key, str(duplicate))
            
            # Create layout with copy button for duplicate
            dup_col1, dup_col2 = st.columns([0.9, 0.1])
            
            with dup_col1:
                with st.expander(f"Duplicate {i} - {dup_question_key}", expanded=False):
                    st.markdown(dup_markdown)
            
            with dup_col2:
                # Add copy button for duplicate with markdown stripping
                import streamlit.components.v1 as components
                import json
                
                dup_copy_key = f"copy_dup_{render_context}_{batch_key}_{question_key}_{i}"
                
                # HTML-escape the duplicate content as well
                escaped_dup_markdown = html.escape(dup_markdown)
                
                dup_copy_html = f"""
                <div style="display: flex; align-items: center; justify-content: center; height: 50px; margin-top: 8px;">
                    <textarea id="text_{dup_copy_key}" style="position: absolute; left: -9999px;">{escaped_dup_markdown}</textarea>
                    <button id="btn_{dup_copy_key}" 
                            style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                   color: white;
                                   border: none;
                                   border-radius: 8px;
                                   padding: 10px 14px;
                                   font-size: 18px;
                                   cursor: pointer;
                                   transition: all 0.3s ease;
                                   box-shadow: 0 2px 4px rgba(0,0,0,0.1);"
                            title="Copy duplicate {i} to clipboard (plain text, tables preserved)">
                        📋
                    </button>
                </div>
                <script>
                    (function() {{
                        const btn = document.getElementById('btn_{dup_copy_key}');
                        const textarea = document.getElementById('text_{dup_copy_key}');
                        
                        btn.addEventListener('click', function() {{
                            try {{
                                const originalText = textarea.value;
                                
                                const tempTextarea = document.createElement('textarea');
                                tempTextarea.value = originalText;
                                tempTextarea.style.position = 'fixed';
                                tempTextarea.style.left = '-9999px';
                                document.body.appendChild(tempTextarea);
                                
                                tempTextarea.select();
                                tempTextarea.setSelectionRange(0, 99999);
                                document.execCommand('copy');
                                
                                document.body.removeChild(tempTextarea);
                                
                                btn.innerHTML = '✅';
                                btn.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';
                                
                                setTimeout(function() {{
                                    btn.innerHTML = '📋';
                                    btn.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
                                }}, 1500);
                            }} catch(err) {{
                                btn.innerHTML = '❌';
                                setTimeout(function() {{
                                    btn.innerHTML = '📋';
                                }}, 1500);
                            }}
                        }});
                        
                        btn.addEventListener('mouseover', function() {{
                            this.style.transform = 'translateY(-2px)';
                            this.style.boxShadow = '0 4px 12px rgba(102, 126, 234, 0.4)';
                        }});
                        
                        btn.addEventListener('mouseout', function() {{
                            this.style.transform = 'translateY(0)';
                            this.style.boxShadow = '0 2px 4px rgba(0,0,0,0.1)';
                        }});
                    }})();
                </script>
                """
                components.html(dup_copy_html, height=60)
                
    # Render Regenerated Question at the very bottom (if available) - REMOVED for inline replacement




def render_duplication_controls(batch_key: str, question_key: str, q_num: str, render_context: str = "results"):
    """Render duplication checkboxes and input fields for a given question."""
    if render_context != "results":
        return
        
    import streamlit as st
    
    checkbox_key = f"duplicate_{render_context}_{batch_key}_{question_key}"
    count_key = f"duplicate_count_{render_context}_{batch_key}_{question_key}"
    
    st.markdown("") # spacing
    col1, col2, col3 = st.columns([0.8, 1.2, 2.5])
    
    with col1:
        duplicate_selected = st.checkbox(
            "Duplicate Item",
            key=checkbox_key,
            help="Select this question to generate duplicates"
        )
        
    with col2:
        regen_key = f"regen_select_{batch_key}_{q_num}"
        regen_selected = st.checkbox("Regenerate Item", key=regen_key, help="Select to regenerate ONLY this question")
        if regen_selected:
            if 'regen_selection' not in st.session_state:
                st.session_state.regen_selection = set()
            st.session_state.regen_selection.add(f"{batch_key}:{q_num}")
            regen_reason_key = f"regen_reason_{batch_key}_{q_num}"
            st.text_input(
                "Reason",
                placeholder="e.g., Options are incorrect...",
                key=regen_reason_key
            )
        else:
            if 'regen_selection' in st.session_state:
                st.session_state.regen_selection.discard(f"{batch_key}:{q_num}")
                
    with col3:
        if duplicate_selected:
            st.number_input(
                "# Duplicates",
                min_value=1,
                max_value=5,
                value=1,
                key=count_key,
                help="Number of duplicates to generate"
            )
            
            notes_key = f"duplicate_notes_{batch_key}_{question_key}"
            file_key = f"duplicate_file_{batch_key}_{question_key}"
            
            with st.expander("📝 Duplicate Customization (Notes & PDF)", expanded=False):
                st.text_area("Additional Instructions", key=notes_key, height=70)
                st.file_uploader("Context File (PDF/Image)", type=['pdf', 'png', 'jpg', 'jpeg', 'webp'], key=file_key)


def render_generated_duplicates(batch_key: str, question_key: str, render_context: str = "results"):
    """Render previously generated duplicates for a question."""
    if render_context != "results":
        return
        
    import html
    import streamlit as st
    import streamlit.components.v1 as components
    
    duplicates_key = f"duplicates_{batch_key}_{question_key}"
    
    if duplicates_key in st.session_state and st.session_state[duplicates_key]:
        st.markdown("")
        st.markdown(f"**🔄 Duplicates ({len(st.session_state[duplicates_key])})**")
        
        for i, duplicate in enumerate(st.session_state[duplicates_key], 1):
            dup_question_key = duplicate.get('question_code', f'{question_key}-dup-{i}')
            
            # The LLM sometimes returns structured JSON embedded inside a `question1` string value.
            # Unwrap it so we can render it properly instead of displaying raw JSON text.
            _structured_keys = ['scenario_text', 'question_text', 'options', 'solution',
                                'distractor_analysis', 'correct_answer', 'final_answer', 'questions_list', 'answer_key', 'correct_option']
            if not any(k in duplicate for k in _structured_keys):
                for _k, _v in duplicate.items():
                    if _k == 'question_code':
                        continue
                    if isinstance(_v, str) and _v.strip().startswith('{'):
                        try:
                            _inner = json.loads(_v)
                            if isinstance(_inner, dict) and any(k2 in _inner for k2 in _structured_keys):
                                duplicate = _inner
                                break
                        except json.JSONDecodeError:
                            pass

            # Detect structured output — covers MCQ, FIB, Descriptive, Case Study, Multi-Part
            is_structured = any(k in duplicate for k in [
                'question_text', 'scenario_text', 'options', 'solution',
                'distractor_analysis', 'correct_answer', 'final_answer', 'questions_list', 'answer_key', 'correct_option'
            ])
            
            if is_structured:
                import json
                
                parts = []
                top_note = ""

                handled_keys = [
                    'question_code', 'question_id', 'question_text', 'scenario_text',
                    'scenario_text/question_text', 'options', 'solution', 'distractor_analysis',
                    'correct_option', 'correct_answer', 'final_answer', 'questions_list', 'key_idea', 'answer_key'
                ]

                for k, v in duplicate.items():
                    if k not in handled_keys and isinstance(v, str):
                        top_note += f"**{k}**: {v}\n\n"
                if top_note:
                    parts.append(top_note)
                
                # Scenario or question stem
                q_text = (
                    duplicate.get('scenario_text/question_text')
                    or duplicate.get('scenario_text')
                    or duplicate.get('question_text', '')
                )
                if q_text:
                    parts.append(f"**{q_text}**\n\n")

                # Sub-questions (Case Study, Multi-Part, Descriptive w/ Sub)
                questions_list = duplicate.get('questions_list', [])
                if isinstance(questions_list, list) and questions_list:
                    parts.append("**Sub-questions:**\n")
                    for si, sq in enumerate(questions_list, 1):
                        clean_sq = re.sub(r"^\s*(?:\([a-zA-Z0-9]+\)|[a-zA-Z0-9]+[.)])\s*", "", str(sq))
                        parts.append(f"**({chr(96+si)})** {clean_sq}\n")
                    parts.append("\n")

                # MCQ options
                options = duplicate.get('options', {})
                if isinstance(options, dict) and options:
                    for opt_k, opt_v in options.items():
                        parts.append(f"- **{opt_k})** {opt_v}")
                    parts.append("\n")
                
                answer_key = duplicate.get('answer_key', '')
                if answer_key:
                    parts.append(f"**Answer Key:** {answer_key}\n\n")
                
                correct_opt = duplicate.get('correct_option', '')
                if correct_opt and not answer_key:
                    parts.append(f"**Correct Option:** {correct_opt}\n\n")

                # FIB
                correct_answer = duplicate.get('correct_answer', '')
                if correct_answer and not answer_key:
                    parts.append(f"**Correct Answer:** {correct_answer}\n\n")

                # Descriptive
                final_answer = duplicate.get('final_answer', '')
                if final_answer and not answer_key:
                    parts.append(f"**Final Answer:** {final_answer}\n\n")
                    
                solution = duplicate.get('solution', '')
                if solution:
                    parts.append(f"**Solution:**\n{solution}\n\n")
                    
                distractors = duplicate.get('distractor_analysis', [])
                if isinstance(distractors, list) and distractors:
                    parts.append("**Distractor Analysis:**\n")
                    parts.append("| Option | Misconception |")
                    parts.append("| :--- | :--- |")
                    for dist in distractors:
                        if isinstance(dist, dict):
                            # Escape pipe characters in content to avoid breaking the markdown table
                            opt = str(dist.get('Option', '')).replace('|', '\\|')
                            misc = str(dist.get('Misconception', '')).replace('|', '\\|')
                            parts.append(f"| **{opt}** | {misc} |")
                        else:
                            val = str(dist).replace('|', '\\|')
                            parts.append(f"| | {val} |")
                    parts.append("\n")
                
                dup_markdown = "\n".join(parts)
            else:
                # Fallback to older text-based markdown blob or the new delimited markdown format
                if 'markdown' in duplicate:
                    dup_markdown = duplicate['markdown']
                else:
                    dup_content_key = [k for k in duplicate.keys() if k != 'question_code'][0] if len(duplicate.keys()) > 1 else 'question1'
                    dup_markdown = duplicate.get(dup_content_key, str(duplicate))
                
            dup_col1, dup_col2 = st.columns([0.9, 0.1])
            
            with dup_col1:
                with st.expander(f"Duplicate {i} - {dup_question_key}", expanded=False):
                    st.markdown(dup_markdown)
            
            with dup_col2:
                dup_copy_key = f"copy_dup_{render_context}_{batch_key}_{question_key}_{i}"
                escaped_dup_markdown = html.escape(dup_markdown)
                
                dup_copy_html = f"""
                <div style="display: flex; align-items: center; justify-content: center; height: 50px; margin-top: 8px;">
                    <textarea id="text_{dup_copy_key}" style="position: absolute; left: -9999px;">{escaped_dup_markdown}</textarea>
                    <button id="btn_{dup_copy_key}" 
                            style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                   color: white; border: none; border-radius: 8px;
                                   padding: 10px 14px; font-size: 18px; cursor: pointer; transition: all 0.3s ease; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"
                            title="Copy duplicate {i} to clipboard">📋</button>
                </div>
                <script>
                    document.getElementById('btn_{dup_copy_key}').addEventListener('click', function() {{
                        const ta = document.createElement('textarea');
                        ta.value = document.getElementById('text_{dup_copy_key}').value;
                        document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
                        this.innerHTML = '✅'; this.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';
                        setTimeout(() => {{ this.innerHTML='📋'; this.style.background='linear-gradient(135deg, #667eea 0%, #764ba2 100%)'; }}, 1500);
                    }});
                </script>
                """
                components.html(dup_copy_html, height=60)
        st.markdown("---")

def _get_effective_q_item(batch_key: str, idx: int, original_q_item: dict) -> tuple:
    """
    Return (effective_q_item_or_string, is_regenerated).
    If a regenerated version exists in session state (as Markdown text), return that string.
    Otherwise return the original dict.
    """
    regen_key = f"regenerated_{batch_key}_question{idx}"
    regen_data = st.session_state.get(regen_key)
    if regen_data and isinstance(regen_data, dict) and 'markdown' in regen_data:
        # The regenerated data is now stored as { "markdown": "..." } from `llm_engine.py`
        return regen_data['markdown'], True
    return original_q_item, False


def render_batch_results(batch_key: str, result_data: Dict[str, Any], render_context: str = "results"):
    """
    Main entry point to render a batch of results.
    
    Uses the single normalization boundary to convert ANY LLM output to clean markdown.
    After normalization, this function only deals with {questionX: markdown_string}.
    
    Args:
        batch_key: The question type (e.g., "MCQ", "Case Study", etc.)
        result_data: Dict containing 'text' with the JSON output
        render_context: Context identifier ("progressive" or "results") to prevent duplicate keys
    """
    # Get text content
    text_content = result_data.get('text', '')
    
    # DEBUG: Log what we received
    print(f"\n=== DEBUG render_batch_results for {batch_key} ===")
    print(f"result_data keys: {result_data.keys()}")
    print(f"text_content length: {len(text_content) if text_content else 0}")
    print(f"text_content preview (first 200 chars): {text_content[:200] if text_content else 'EMPTY'}")
    
    if not text_content:
        st.warning("No content to display.")
        return
    
    # =======================================================================
    # PIPELINE OUTPUT DETECTION - Check for scenario+question structure
    # =======================================================================
    try:
        parsed_output = json.loads(text_content)
        
        # Handle new 3-stage pipeline output (math_core, writer_output, solution_output)
        if isinstance(parsed_output, dict) and 'writer_output' in parsed_output:
            st.markdown("### 🎯 Generated Content")
            
            # --- RENDER VALIDATED OUTPUT (IF AVAILABLE) ---
            if 'validation_output' in parsed_output and parsed_output['validation_output']:
                st.success("✅ Showing Validated Output")
                val_data = parsed_output['validation_output']
                
                # Sort questions by number (question1, question2, ...)
                sorted_keys = sorted(
                    [k for k in val_data.keys() if re.match(r'^(question|q)\d+$', k, re.IGNORECASE)],
                    key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0
                )
                
                for i, q_key in enumerate(sorted_keys, 1):
                    if i > 1:
                        st.markdown("---")
                    
                    
                    # Intercept regenerated text
                    regen_key = f"regenerated_{batch_key}_{q_key}"
                    regen_data = st.session_state.get(regen_key)
                    is_regen = False
                    if regen_data and isinstance(regen_data, dict) and 'markdown' in regen_data:
                        markdown_content = regen_data['markdown']
                        is_regen = True
                    else:
                        markdown_content = val_data[q_key]
                    
                    # Ensure it's a string
                    if not isinstance(markdown_content, str):
                        # Attempt to extract string if it's a dict
                        if isinstance(markdown_content, dict):
                            extracted = markdown_content.get('content') or markdown_content.get('value') or markdown_content.get('markdown') or markdown_content.get('text')
                            if isinstance(extracted, str):
                                markdown_content = extracted
                            else:
                                markdown_content = json.dumps(markdown_content, indent=2)
                        else:
                            markdown_content = str(markdown_content)
                            
                    # Unescape just in case
                    try:
                        markdown_content = unescape_json_string(markdown_content)
                    except Exception:
                        pass
                        
                    render_markdown_question(q_key, markdown_content, batch_key, batch_key, render_context, is_regen)
                    
                st.markdown("---")
            else:
                 st.info("Validation output not found. Showing raw writer output.")
                 
            # --- RENDER ORIGINAL WRITER OUTPUT ---
            with st.expander("🔍 View Original Structured Output (Before Validation)", expanded=not bool(parsed_output.get('validation_output'))):
                writer_out = parsed_output['writer_output']
                if 'questions' in writer_out:
                    base_type = batch_key.split(' - Batch ')[0] if batch_key else ""
                    
                    for idx, q_item in enumerate(writer_out['questions'], 1):
                        
                        # === MCQ Handling ===
                        if base_type == 'MCQ' or 'options' in q_item:
                            # MCQ Renderer
                            display_item, is_regen = _get_effective_q_item(batch_key, idx, q_item)
                            
                            if is_regen:
                                with st.expander(f"Question {idx} 🔄 (Regenerated)", expanded=True):
                                    render_markdown_question(f"question{idx}", display_item, batch_key, batch_key, f"{render_context}_writer_mcq", is_regenerated=True)
                            else:
                                q_id = display_item.get('question_id', f"Q{idx}")
                                with st.container():
                                    header = f"#### ❓ Question {idx} ({q_id})"
                                    st.markdown(header)
                                    
                                    # Question Text
                                    st.markdown(f"**{display_item.get('question_text', '')}**")
                                    
                                    # Diagram prompt
                                    if 'diagram_prompt' in display_item:
                                        st.info(f"🖼️ **Diagram Request:** {display_item['diagram_prompt']}")
                                        
                                    # Options
                                    opts = display_item.get('options', {})
                                    if opts:
                                        st.markdown("**Options:**")
                                        for opt_key, opt_val in opts.items():
                                            st.markdown(f"- **{opt_key}:** {opt_val}")
                                
                                # Answer & Solution
                                with st.expander("💡 View Solution & Analysis", expanded=False):
                                    # Correct Option
                                    correct_opt = display_item.get('answer_key', display_item.get('correct_option', 'Unknown'))
                                    st.success(f"**Answer Key:** {correct_opt}")
                                    
                                    # Solution
                                    if 'solution' in display_item:
                                        st.markdown("**Solution:**")
                                        st.markdown(display_item['solution'])
                                    
                                    # Key Idea
                                    if 'key_idea' in display_item:
                                        st.markdown("**Key Idea:**")
                                        st.info(display_item['key_idea'])
                                        
                                    # Distractor Analysis
                                    if 'distractor_analysis' in display_item:
                                        st.markdown("**🚫 Distractor Analysis:**")
                                        da_content = display_item['distractor_analysis']
                                        
                                        if isinstance(da_content, list):
                                            md_table = "| Option | Misconception |\n|---|---|\n"
                                            for da_row in da_content:
                                                if isinstance(da_row, dict):
                                                    opt = da_row.get('Option', '') or da_row.get('option', '')
                                                    misc = da_row.get('Misconception', '') or da_row.get('misconception', '') or da_row.get('Explanation', '') or da_row.get('explanation', '')
                                                    md_table += f"| {opt} | {misc} |\n"
                                                else:
                                                    md_table += f"| - | {da_row} |\n"
                                            st.markdown(md_table)
                                        else:
                                            st.markdown(da_content)
                                        
                                    st.markdown("---")
                                    cols = st.columns(4)
                                    cols[0].metric("DOK Level", display_item.get('dok_level', 'N/A'))
                                    cols[1].metric("Taxonomy", display_item.get('taxonomy', 'N/A'))
                                    cols[2].metric("Marks", display_item.get('mark', 'N/A'))
                                    cols[3].metric("Type", display_item.get('mcq_type', 'N/A'))
                                    
                                st.markdown("---")
    
                        elif base_type == 'Fill in the Blanks' or ('correct_answer' in q_item or ('answer_key' in q_item and 'questions_list' not in q_item and 'diagram_prompt' not in q_item)):
                            display_item, is_regen = _get_effective_q_item(batch_key, idx, q_item)
                            
                            if is_regen:
                                with st.expander(f"Question {idx} 🔄 (Regenerated)", expanded=True):
                                    render_markdown_question(f"question{idx}", display_item, batch_key, batch_key, f"{render_context}_writer_fib", is_regenerated=True)
                            else:
                                q_id = display_item.get('question_id', f"Q{idx}")
                                with st.container():
                                    header = f"#### � Question {idx} ({q_id})"
                                    st.markdown(header)
                                    
                                    # Question Text
                                    st.markdown(f"**{display_item.get('question_text', '')}**")
                                    
                                    # Diagram prompt
                                    if 'diagram_prompt' in display_item:
                                        st.info(f"🖼️ **Diagram Request:** {display_item['diagram_prompt']}")
                                    
                                    # Answer & Solution
                                    with st.expander("💡 View Solution & Analysis", expanded=False):
                                        # Correct Answer
                                        correct_ans = display_item.get('answer_key', display_item.get('correct_answer', 'N/A'))
                                        st.success(f"**Answer Key:**\n\n{correct_ans}")
                                        
                                        # Solution
                                        if 'solution' in display_item:
                                            st.markdown("**Solution:**")
                                            st.markdown(display_item['solution'])
                                        
                                        # Key Idea
                                        if 'key_idea' in display_item:
                                            st.markdown("**Key Idea:**")
                                            st.info(display_item['key_idea'])
                                            
                                        st.markdown("---")
                                        cols = st.columns(3)
                                        cols[0].metric("DOK Level", display_item.get('dok_level', 'N/A'))
                                        cols[1].metric("Taxonomy", display_item.get('taxonomy', 'N/A'))
                                        cols[2].metric("Marks", display_item.get('mark', 'N/A'))
                                        
                                    st.markdown("---")
    
                        elif base_type in ('Descriptive', 'Graph Based') or ('final_answer' in q_item or ('answer_key' in q_item and 'questions_list' not in q_item)):
                            display_item, is_regen = _get_effective_q_item(batch_key, idx, q_item)
                            
                            if is_regen:
                                with st.expander(f"Question {idx} 🔄 (Regenerated)", expanded=True):
                                    render_markdown_question(f"question{idx}", display_item, batch_key, batch_key, f"{render_context}_writer_desc", is_regenerated=True)
                            else:
                                q_id = display_item.get('question_id', f"Q{idx}")
                                with st.container():
                                    header = f"#### ✍️ Question {idx} ({q_id})"
                                    st.markdown(header)
                                    
                                    # Question Text
                                    st.markdown(f"**{display_item.get('question_text', '')}**")
                                    
                                    # Diagram prompt
                                    if 'diagram_prompt' in display_item and display_item['diagram_prompt'] != "No diagram":
                                        st.info(f"🖼️ **Diagram Request:** {display_item['diagram_prompt']}")
                                    
                                    # Answer & Solution
                                    with st.expander("💡 View Solution & Analysis", expanded=False):
                                        # Final Answer
                                        correct_ans = display_item.get('answer_key', display_item.get('final_answer', 'N/A'))
                                        st.success(f"**Answer Key:**\n\n{correct_ans}")
                                        
                                        # Solution
                                        if 'solution' in display_item:
                                            st.markdown("**Solution:**")
                                            st.markdown(display_item['solution'])
                                        
                                        # Key Idea
                                        if 'key_idea' in display_item:
                                            st.markdown("**Key Idea:**")
                                            st.info(display_item['key_idea'])
                                            
                                        st.markdown("---")
                                        cols = st.columns(3)
                                        cols[0].metric("DOK Level", display_item.get('dok_level', 'N/A'))
                                        cols[1].metric("Taxonomy", display_item.get('taxonomy', 'N/A'))
                                        cols[2].metric("Marks", display_item.get('mark', 'N/A'))
                                        
                                    st.markdown("---")
    
                        elif base_type in ('Descriptive w/ Subquestions', 'Case Study', 'Multi-Part') or 'questions_list' in q_item:
                            display_item, is_regen = _get_effective_q_item(batch_key, idx, q_item)
                            
                            if is_regen:
                                with st.expander(f"Question {idx} 🔄 (Regenerated)", expanded=True):
                                    render_markdown_question(f"question{idx}", display_item, batch_key, batch_key, f"{render_context}_writer_multi", is_regenerated=True)
                            else:
                                q_id = display_item.get('question_id', f"Q{idx}")
                                
                                scenario_txt = display_item.get('scenario_text/question_text') or display_item.get('scenario_text') or display_item.get('question_text') or ''
                                
                                with st.container():
                                    header = f"#### 📄 Question {idx} ({q_id})"
                                    st.markdown(header)
                                    
                                    # Scenario/Question Text
                                    with st.expander(f"Scenario / Context", expanded=True):
                                        st.markdown(scenario_txt)
                                        if 'diagram_description' in display_item:
                                            st.info(f"**Diagram:** {display_item['diagram_description']}")
                                    
                                    # Sub-questions
                                    if 'questions_list' in display_item:
                                        st.markdown(f"**Sub-questions:**")
                                        for sub_idx, sub_q in enumerate(display_item['questions_list'], 1):
                                            clean_sq = re.sub(r"^\s*(?:\([a-zA-Z0-9]+\)|[a-zA-Z0-9]+[.)])\s*", "", str(sub_q))
                                            st.markdown(f"**({chr(96+sub_idx)})** {clean_sq}")
                                    
                                    # Solution & Key Idea
                                    with st.expander("💡 View Solution & Analysis", expanded=False):
                                        correct_ans = display_item.get('answer_key', display_item.get('final_answer', 'N/A'))
                                        if correct_ans != 'N/A' or 'answer_key' in display_item:
                                            st.success(f"**Answer Key:**\n\n{correct_ans}")
        
                                        if 'solution' in display_item:
                                            st.markdown("**Solution:**")
                                            st.markdown(display_item['solution'])
                                        
                                        if 'key_idea' in display_item:
                                            st.markdown("**Key Idea:**")
                                            st.info(display_item['key_idea'])
                                            
                                        st.markdown("---")
                                        cols = st.columns(3)
                                        cols[0].metric("DOK Level", display_item.get('dok_level', 'N/A'))
                                        cols[1].metric("Taxonomy", display_item.get('taxonomy', 'N/A'))
                                        cols[2].metric("Marks", display_item.get('mark', 'N/A'))
                                        
                                st.markdown("---")
    
                        # === Case Study Handling (Fallback) ===
                        elif 'scenario_text' in q_item:
                            with st.expander(f"Scenario {idx}", expanded=True):
                                st.markdown(q_item['scenario_text'])
                                if 'diagram_description' in q_item:
                                    st.info(f"**Diagram:** {q_item['diagram_description']}")
                            
                            if 'questions_list' in q_item:
                                st.markdown(f"**Questions for Scenario {idx}:**")
                                for sub_idx, sub_q in enumerate(q_item['questions_list'], 1):
                                    clean_sq = re.sub(r"^\s*(?:\([a-zA-Z0-9]+\)|[a-zA-Z0-9]+[.)])\s*", "", str(sub_q))
                                    st.markdown(f"**{sub_idx}.** {clean_sq}")
                            
                            if 'solution' in q_item and q_item['solution']:
                                with st.expander(f"💡 Solution", expanded=False):
                                    st.markdown(q_item['solution'])
    
                            if 'key_idea' in q_item and q_item['key_idea']:
                                with st.expander(f"Key Idea", expanded=False):
                                    st.markdown(q_item['key_idea'])
            
            # Display metadata is removed for cleaner UI
            return

        # Handle legacy or 2-stage pipeline output
        if isinstance(parsed_output, dict) and ('scenario' in parsed_output or 'question' in parsed_output):
            st.markdown("### 🎯 Pipeline Generated Content")
            
            # Display scenarios
            if 'scenario' in parsed_output:
                st.markdown("#### 📝 Generated Scenarios")
                scenarios = parsed_output['scenario']
                if isinstance(scenarios, list):
                    for idx, scenario in enumerate(scenarios, 1):
                        with st.expander(f"Scenario {idx}: {scenario.get('Topic', 'Untitled')}", expanded=idx == 1):
                            st.markdown(scenario.get('scenario_text', 'No scenario text available'))
            
            # Display questions  
            if 'question' in parsed_output:
                st.markdown("#### ❓ Generated Questions")
                question_data = parsed_output['question']
                if isinstance(question_data, dict) and 'questions' in question_data:
                    questions = question_data['questions']
                    for idx, question in enumerate(questions, 1):
                        with st.expander(f"Question {question.get('question_id', idx)}", expanded=True):
                            # Render the markdown content
                            content = question.get('content_markdown', '')
                            if content:
                                st.markdown(content)
                            else:
                                st.warning("No content available for this question")
                
                # Display metadata is removed for cleaner UI
            
            # Successfully rendered pipeline output
            return
            
    except json.JSONDecodeError:
        # Not valid JSON or not pipeline output, continue with normal flow
        pass
    except Exception as e:
        # Something went wrong with pipeline detection — show error in UI so it's visible
        import traceback
        st.error(f"⚠️ Rendering error: {e}")
        with st.expander("Error Details"):
            st.code(traceback.format_exc())
        print(f"Pipeline detection error: {e}")
        return  # Don't fall through to normalizer — partial output already may have rendered
    
    # =======================================================================
    # SINGLE NORMALIZATION BOUNDARY - All LLM output parsing happens here
    # =======================================================================
    questions_dict = normalize_llm_output_to_questions(text_content)
    
    # DEBUG: Log normalization results
    print(f"questions_dict keys: {list(questions_dict.keys())}")
    for k, v in questions_dict.items():
        print(f"  {k}: length={len(v)}, preview={v[:100] if v else 'EMPTY'}...")
    
    # Handle normalization failure
    if not questions_dict:
        st.error(f"❌ Validator output could not be normalized for {batch_key}")
        with st.expander("Raw Output"):
            st.text(text_content)
        return
    
    # Success message
    st.success(f"✅ Successfully parsed {len(questions_dict)} {batch_key} questions")
    st.markdown("")  # spacing
    
    # Sort questions by number (question1, question2, question3, etc.)
    sorted_keys = sorted(questions_dict.keys(), 
                        key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)
    
    # =======================================================================
    # RENDER - After normalization, we ONLY have markdown strings
    # =======================================================================
    for i, q_key in enumerate(sorted_keys, 1):
        # Add prominent separator between questions
        if i > 1:
            st.markdown("")
            st.markdown("")
            st.markdown("---")
            st.markdown("---")  # Double divider for prominence
            st.markdown("")
        
        # After normalization, content is GUARANTEED to be a string
        markdown_content = questions_dict[q_key]
        
        # DEBUG: Log what we're about to render
        print(f"Rendering {q_key}: markdown_content length={len(markdown_content)}, preview={markdown_content[:100]}...")
        
        # Invariant check (should never fail after normalization)
        assert isinstance(markdown_content, str), f"Normalization failed: {q_key} is not a string"
        
        # Check if regenerated
        regen_key = f"regenerated_{batch_key}_{q_key}"
        regen_data = st.session_state.get(regen_key)
        is_regen = False
        if regen_data and isinstance(regen_data, dict) and 'markdown' in regen_data:
            markdown_content = regen_data['markdown']
            is_regen = True
        
        # Render markdown directly - no JSON parsing, no guessing
        render_markdown_question(q_key, markdown_content, batch_key, batch_key, render_context, is_regen)
    
    # Add spacing at the end
    st.markdown("")
    st.markdown("")


def generate_markdown_for_download(batch_key: str, result_data: Dict[str, Any]) -> str:
    """
    Convert a batch result into a clean, human-readable Markdown document
    suitable for download and pasting into Word / Google Docs.

    Priority:
      1. validation_output  (pre-formatted markdown strings from the validator)
      2. writer_output      (structured JSON dicts → formatted markdown)
      3. normalize_llm_output_to_questions fallback (old pipeline format)
    """
    text_content = result_data.get('text', '')
    if not text_content:
        return ""

    lines = []

    try:
        parsed = json.loads(text_content)
    except json.JSONDecodeError:
        parsed = None

    # ------------------------------------------------------------------ #
    # PATH 1 – 3-stage pipeline: validation_output contains {qX: markdown}
    # ------------------------------------------------------------------ #
    if isinstance(parsed, dict) and 'writer_output' in parsed:
        val_data = parsed.get('validation_output') or {}
        writer_questions = parsed.get('writer_output', {}).get('questions', [])

        if val_data:
            sorted_keys = sorted(
                [k for k in val_data.keys() if re.match(r'^(question|q)\d+$', k, re.IGNORECASE)],
                key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0
            )
            for i, q_key in enumerate(sorted_keys, 1):
                if i > 1:
                    lines.append("\n---\n")
                lines.append(f"## Question {i}\n")

                # Check if this question has been regenerated
                regen_key = f"regenerated_{batch_key}_{q_key}"
                regen_data = st.session_state.get(regen_key)
                if regen_data and isinstance(regen_data, dict) and 'markdown' in regen_data:
                    md = regen_data['markdown']
                    lines.append("*(Regenerated)*\n")
                else:
                    md = val_data[q_key]
                    if not isinstance(md, str):
                        md = json.dumps(md, indent=2)
                    try:
                        md = unescape_json_string(md)
                    except Exception:
                        pass

                lines.append(md.strip())
                lines.append("")
            return "\n".join(lines)

        # No validation_output — fall back to formatting writer_output questions
        if writer_questions:
            base_type = batch_key.split(' - Batch ')[0] if batch_key else ""
            for i, q_item in enumerate(writer_questions, 1):
                if i > 1:
                    lines.append("\n---\n")
                lines.append(f"## Question {i}\n")

                q_text = q_item.get('question_text', q_item.get('scenario_text/question_text', q_item.get('scenario_text', '')))
                if q_text:
                    lines.append(f"**{q_text}**\n")

                # OPTIONS (MCQ)
                opts = q_item.get('options', {})
                if isinstance(opts, dict) and opts:
                    lines.append("\n**OPTIONS**\n")
                    for opt_k, opt_v in opts.items():
                        lines.append(f"{opt_k}) {opt_v}")
                    lines.append("")

                # Sub-questions (Case Study / Multi-Part)
                ql = q_item.get('questions_list', [])
                if isinstance(ql, list) and ql:
                    lines.append("\n**Sub-questions:**\n")
                    for si, sq in enumerate(ql, 1):
                        clean_sq = re.sub(r"^\s*(?:\([a-zA-Z0-9]+\)|[a-zA-Z0-9]+[.)]) *", "", str(sq))
                        lines.append(f"({chr(96+si)}) {clean_sq}")
                    lines.append("")

                # ANSWER KEY
                answer = (q_item.get('answer_key')
                          or q_item.get('correct_option')
                          or q_item.get('correct_answer')
                          or q_item.get('final_answer', ''))
                if answer:
                    lines.append(f"\n**ANSWER KEY**\n\n{answer}\n")

                # SOLUTION
                sol = q_item.get('solution', '')
                if sol:
                    lines.append(f"\n**SOLUTION**\n\n{sol}\n")

                # DISTRACTOR ANALYSIS (MCQ)
                da = q_item.get('distractor_analysis', [])
                if isinstance(da, list) and da:
                    lines.append("\n**DISTRACTOR ANALYSIS**\n")
                    for row in da:
                        if isinstance(row, dict):
                            opt = row.get('Option & Error Type', row.get('Option', ''))
                            misc = row.get('Misconception', row.get('Explanation', ''))
                            lines.append(f"- **{opt}**: {misc}")
                        else:
                            lines.append(f"- {row}")
                    lines.append("")

                # KEY IDEA
                ki = q_item.get('key_idea', '')
                if ki:
                    lines.append(f"\n**KEY IDEA**\n\n{ki}\n")

            return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # PATH 2 – normalizer (old 2-stage / raw validator output)
    # ------------------------------------------------------------------ #
    questions_dict = normalize_llm_output_to_questions(text_content)
    if questions_dict:
        sorted_keys = sorted(
            questions_dict.keys(),
            key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0
        )
        for i, q_key in enumerate(sorted_keys, 1):
            if i > 1:
                lines.append("\n---\n")
            lines.append(f"## Question {i}\n")
            lines.append(questions_dict[q_key].strip())
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # PATH 3 – absolute fallback: return raw text as-is
    # ------------------------------------------------------------------ #
    return text_content

