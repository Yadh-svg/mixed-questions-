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


def render_markdown_question(question_key: str, markdown_content: str, question_type: str, batch_key: str = "", render_context: str = "results"):
    """
    Render a single question from its markdown content.
    
    Args:
        question_key: The key (e.g., "question1", "question2")
        markdown_content: The complete markdown content
        question_type: The question type from batch_key
        batch_key: The batch identifier for session state management
        render_context: Context identifier ("progressive" or "results") to prevent duplicate keys
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
            st.markdown(f"### {emoji} Question {q_num}")
            
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
    rendered_content = markdown_content.replace('\n', '  \n')
    st.markdown(rendered_content)
    
    # Display duplicates if they exist (only in results context)
    if render_context == "results" and st.session_state[duplicates_key]:
        st.markdown("")
        st.markdown("---")
        st.markdown(f"**🔄 Duplicates ({len(st.session_state[duplicates_key])})**")
        
        for i, duplicate in enumerate(st.session_state[duplicates_key], 1):
            dup_question_key = duplicate.get('question_code', f'{question_key}-dup-{i}')
            # Get the markdown content from the duplicate (usually second key after question_code)
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
                
    # Render Regenerated Question at the very bottom (if available)
    if render_context == "results":
        render_regenerated_question(batch_key, question_key, render_context)




def render_regenerated_question(batch_key: str, question_key: str, render_context: str = "results"):
    """Render previously regenerated questions underneath the original."""
    if render_context != "results":
        return
        
    import html
    import streamlit as st
    import json
    
    regenerated_key = f"regenerated_{batch_key}_{question_key}"
    
    if regenerated_key in st.session_state and st.session_state[regenerated_key]:
        st.markdown("")
        st.markdown(f"**🔄 Regenerated Version**")
        
        duplicate = st.session_state[regenerated_key]
        
        # The LLM sometimes returns structured JSON embedded inside a `question1` string value.
        # Unwrap it so we can render it properly instead of displaying raw JSON text.
        _structured_keys = ['scenario_text', 'question_text', 'options', 'solution',
                            'distractor_analysis', 'correct_answer', 'final_answer', 'questions_list']
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
            'distractor_analysis', 'correct_answer', 'final_answer', 'questions_list'
        ])
        
        if is_structured:
            parts = []
            top_note = ""
            
            handled_keys = [
                'question_code', 'question_id', 'question_text', 'scenario_text',
                'scenario_text/question_text', 'options', 'solution', 'distractor_analysis',
                'correct_option', 'correct_answer', 'final_answer', 'questions_list', 'key_idea'
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
                    parts.append(f"**({chr(96+si)})** {sq}\n")
                parts.append("\n")

            # MCQ options
            options = duplicate.get('options', {})
            if isinstance(options, dict) and options:
                for opt_k, opt_v in options.items():
                    parts.append(f"- **{opt_k})** {opt_v}")
                parts.append("\n")
            
            correct_opt = duplicate.get('correct_option', '')
            if correct_opt:
                parts.append(f"**Correct Option:** {correct_opt}\n\n")

            # FIB correct answer
            correct_answer = duplicate.get('correct_answer', '')
            if correct_answer:
                parts.append(f"**Correct Answer:** {correct_answer}\n\n")

            # Descriptive final answer
            final_answer = duplicate.get('final_answer', '')
            if final_answer:
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
                        opt = str(dist.get('Option', '')).replace('|', '\\|')
                        misc = str(dist.get('Misconception', '')).replace('|', '\\|')
                        parts.append(f"| **{opt}** | {misc} |")
                    else:
                        val = str(dist).replace('|', '\\|')
                        parts.append(f"| | {val} |")
                parts.append("\n\n")
                
            key_idea = duplicate.get('key_idea', '')
            if key_idea:
                parts.append(f"**Key Idea:**\n{key_idea}\n\n")
            
            dup_markdown = "\n".join(parts)
        else:
            dup_content_key = [k for k in duplicate.keys() if k != 'question_code'][0] if len(duplicate.keys()) > 1 else 'question1'
            dup_markdown = duplicate.get(dup_content_key, str(duplicate))
            
        with st.expander(f"✨ Regenerated Output", expanded=True):
            st.markdown(dup_markdown)
        st.markdown("---")




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
                                'distractor_analysis', 'correct_answer', 'final_answer', 'questions_list']
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
                'distractor_analysis', 'correct_answer', 'final_answer', 'questions_list'
            ])
            
            if is_structured:
                import json
                
                parts = []
                top_note = ""

                handled_keys = [
                    'question_code', 'question_id', 'question_text', 'scenario_text',
                    'scenario_text/question_text', 'options', 'solution', 'distractor_analysis',
                    'correct_option', 'correct_answer', 'final_answer', 'questions_list', 'key_idea'
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
                        parts.append(f"**({chr(96+si)})** {sq}\n")
                    parts.append("\n")

                # MCQ options
                options = duplicate.get('options', {})
                if isinstance(options, dict) and options:
                    for opt_k, opt_v in options.items():
                        parts.append(f"- **{opt_k})** {opt_v}")
                    parts.append("\n")
                
                correct_opt = duplicate.get('correct_option', '')
                if correct_opt:
                    parts.append(f"**Correct Option:** {correct_opt}\n\n")

                # FIB
                correct_answer = duplicate.get('correct_answer', '')
                if correct_answer:
                    parts.append(f"**Correct Answer:** {correct_answer}\n\n")

                # Descriptive
                final_answer = duplicate.get('final_answer', '')
                if final_answer:
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
                # Fallback to older text-based markdown blob
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
            
            writer_out = parsed_output['writer_output']
            if 'questions' in writer_out:
                for idx, q_item in enumerate(writer_out['questions'], 1):
                    
                    # === MCQ Handling ===
                    if 'options' in q_item:
                        # MCQ Renderer
                        q_id = q_item.get('question_id', f"Q{idx}")
                        with st.container():
                            st.markdown(f"### ❓ Question {idx} ({q_id})")
                            
                            # Question Text
                            st.markdown(f"**{q_item.get('question_text', '')}**")
                            
                            # Diagram prompt
                            if 'diagram_prompt' in q_item:
                                st.info(f"🖼️ **Diagram Request:** {q_item['diagram_prompt']}")
                                
                            # Options
                            opts = q_item.get('options', {})
                            if opts:
                                st.markdown("#### Options:")
                                for opt_key, opt_val in opts.items():
                                    st.markdown(f"- **{opt_key}:** {opt_val}")
                            
                            render_duplication_controls(batch_key, f'question{idx}', str(idx), render_context)
                            render_generated_duplicates(batch_key, f'question{idx}', render_context)
                            render_regenerated_question(batch_key, f'question{idx}', render_context)
                            # Answer & Solution
                            with st.expander("💡 View Solution & Analysis", expanded=False):
                                # Correct Option
                                correct_opt = q_item.get('correct_option', 'Unknown')
                                st.success(f"**Correct Option:** {correct_opt}")
                                
                                # Solution
                                if 'solution' in q_item:
                                    st.markdown("#### ✅ Solution:")
                                    st.markdown(q_item['solution'])
                                
                                # Key Idea
                                if 'key_idea' in q_item:
                                    st.markdown("#### 🔑 Key Idea:")
                                    st.info(q_item['key_idea'])
                                    
                                # Distractor Analysis
                                if 'distractor_analysis' in q_item:
                                    st.markdown("#### 🚫 Distractor Analysis:")
                                    da_content = q_item['distractor_analysis']
                                    
                                    if isinstance(da_content, list):
                                        # Convert list of dicts to markdown table
                                        # Expecting: [{'Option': '...', 'Misconception': '...'}, ...]
                                        md_table = "| Option | Misconception |\n|---|---|\n"
                                        for da_row in da_content:
                                            if isinstance(da_row, dict):
                                                opt = da_row.get('Option', '') or da_row.get('option', '')
                                                # Handle potential variations in keys
                                                misc = da_row.get('Misconception', '') or da_row.get('misconception', '') or da_row.get('Explanation', '') or da_row.get('explanation', '')
                                                md_table += f"| {opt} | {misc} |\n"
                                            else:
                                                # If row is a string, just append
                                                md_table += f"| - | {da_row} |\n"
                                        st.markdown(md_table)
                                    else:
                                        # Default string rendering
                                        st.markdown(da_content)
                                    
                                # Metadata
                                st.markdown("---")
                                cols = st.columns(4)
                                cols[0].metric("DOK Level", q_item.get('dok_level', 'N/A'))
                                cols[1].metric("Taxonomy", q_item.get('taxonomy', 'N/A'))
                                cols[2].metric("Marks", q_item.get('mark', 'N/A'))
                                cols[3].metric("Type", q_item.get('mcq_type', 'N/A'))
                                
                            st.markdown("---")

                    # === Fill in the Blanks Handling ===
                    elif 'correct_answer' in q_item:
                         # FIB Renderer
                        q_id = q_item.get('question_id', f"Q{idx}")
                        with st.container():
                            st.markdown(f"### 📝 Question {idx} ({q_id})")
                            
                            # Question Text
                            st.markdown(f"**{q_item.get('question_text', '')}**")
                            
                            # Diagram prompt
                            if 'diagram_prompt' in q_item:
                                st.info(f"🖼️ **Diagram Request:** {q_item['diagram_prompt']}")
                            
                            render_duplication_controls(batch_key, f'question{idx}', str(idx), render_context)
                            render_generated_duplicates(batch_key, f'question{idx}', render_context)
                            render_regenerated_question(batch_key, f'question{idx}', render_context)
                            # Answer & Solution
                            with st.expander("💡 View Solution & Analysis", expanded=False):
                                # Correct Answer
                                st.success(f"**Correct Answer:**\n\n{q_item.get('correct_answer', 'N/A')}")
                                
                                # Solution
                                if 'solution' in q_item:
                                    st.markdown("#### ✅ Solution:")
                                    st.markdown(q_item['solution'])
                                
                                # Key Idea
                                if 'key_idea' in q_item:
                                    st.markdown("#### 🔑 Key Idea:")
                                    st.info(q_item['key_idea'])
                                    
                                # Metadata
                                st.markdown("---")
                                cols = st.columns(3)
                                cols[0].metric("DOK Level", q_item.get('dok_level', 'N/A'))
                                cols[1].metric("Taxonomy", q_item.get('taxonomy', 'N/A'))
                                cols[2].metric("Marks", q_item.get('mark', 'N/A'))
                                
                            st.markdown("---")

                    # === Descriptive Handling ===
                    elif 'final_answer' in q_item:
                        # Descriptive Renderer
                        q_id = q_item.get('question_id', f"Q{idx}")
                        with st.container():
                            st.markdown(f"### ✍️ Question {idx} ({q_id})")
                            
                            # Question Text
                            st.markdown(f"**{q_item.get('question_text', '')}**")
                            
                            # Diagram prompt
                            if 'diagram_prompt' in q_item and q_item['diagram_prompt'] != "No diagram":
                                st.info(f"🖼️ **Diagram Request:** {q_item['diagram_prompt']}")
                            
                            render_duplication_controls(batch_key, f'question{idx}', str(idx), render_context)
                            render_generated_duplicates(batch_key, f'question{idx}', render_context)
                            render_regenerated_question(batch_key, f'question{idx}', render_context)
                            # Answer & Solution
                            with st.expander("💡 View Solution & Analysis", expanded=False):
                                # Final Answer
                                st.success(f"**Final Answer:**\n\n{q_item.get('final_answer', 'N/A')}")
                                
                                # Solution
                                if 'solution' in q_item:
                                    st.markdown("#### ✅ Solution:")
                                    st.markdown(q_item['solution'])
                                
                                # Key Idea
                                if 'key_idea' in q_item:
                                    st.markdown("#### 🔑 Key Idea:")
                                    st.info(q_item['key_idea'])
                                    
                                # Metadata (if available separately, otherwise it's in text)
                                st.markdown("---")
                                cols = st.columns(3)
                                cols[0].metric("DOK Level", q_item.get('dok_level', 'N/A'))
                                cols[1].metric("Taxonomy", q_item.get('taxonomy', 'N/A'))
                                cols[2].metric("Marks", q_item.get('mark', 'N/A'))
                                
                            st.markdown("---")

                    # === Descriptive w/ Subquestions Handling ===
                    elif 'questions_list' in q_item:
                         # Descriptive w/ Subquestions (similar to Case Study but slightly different keys)
                        q_id = q_item.get('question_id', f"Q{idx}")
                        
                        # Handle the weird key "scenario_text/question_text"
                        scenario_txt = q_item.get('scenario_text/question_text') or q_item.get('scenario_text') or q_item.get('question_text') or ''
                        
                        with st.container():
                            st.markdown(f"### 📄 Question {idx} ({q_id})")
                            
                            # Scenario/Question Text
                            with st.expander(f"Scenario / Context", expanded=True):
                                st.markdown(scenario_txt)
                                if 'diagram_description' in q_item:
                                    st.info(f"**Diagram:** {q_item['diagram_description']}")
                            
                            # Sub-questions
                            if 'questions_list' in q_item:
                                st.markdown(f"**Sub-questions:**")
                                for sub_idx, sub_q in enumerate(q_item['questions_list'], 1):
                                    st.markdown(f"**({chr(96+sub_idx)})** {sub_q}")
                            
                            # Solution & Key Idea
                            render_duplication_controls(batch_key, f"question{idx}", str(idx), render_context)
                            render_generated_duplicates(batch_key, f"question{idx}", render_context)
                            render_regenerated_question(batch_key, f"question{idx}", render_context)
                            with st.expander("💡 View Solution & Analysis", expanded=False):
                                if 'final_answer' in q_item:
                                    st.success(f"**Final Answer:**\n\n{q_item.get('final_answer', 'N/A')}")

                                if 'solution' in q_item:
                                    st.markdown("#### ✅ Solution:")
                                    st.markdown(q_item['solution'])
                                
                                if 'key_idea' in q_item:
                                    st.markdown("#### 🔑 Key Idea:")
                                    st.info(q_item['key_idea'])
                                    
                                # Metadata
                                st.markdown("---")
                                cols = st.columns(3)
                                cols[0].metric("DOK Level", q_item.get('dok_level', 'N/A'))
                                cols[1].metric("Taxonomy", q_item.get('taxonomy', 'N/A'))
                                cols[2].metric("Marks", q_item.get('mark', 'N/A'))
                                
                        st.markdown("---")

                    # === Case Study Handling (Existing) ===
                    elif 'scenario_text' in q_item:
                        # Render Scenario
                        with st.expander(f"Scenario {idx}", expanded=True):
                            st.markdown(q_item['scenario_text'])
                            if 'diagram_description' in q_item:
                                st.info(f"**Diagram:** {q_item['diagram_description']}")
                        
                        # Render Questions
                        if 'questions_list' in q_item:
                            st.markdown(f"**Questions for Scenario {idx}:**")
                            for sub_idx, sub_q in enumerate(q_item['questions_list'], 1):
                                st.markdown(f"**{sub_idx}.** {sub_q}")
                        
                        # Render Solution
                        if 'solution' in q_item and q_item['solution']:
                            with st.expander(f"💡 Solution", expanded=False):
                                st.markdown(q_item['solution'])

                        # Render Key Idea
                        if 'key_idea' in q_item and q_item['key_idea']:
                            with st.expander(f"🔑 Key Idea", expanded=False):
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
        
        # Render markdown directly - no JSON parsing, no guessing
        render_markdown_question(q_key, markdown_content, batch_key, batch_key, render_context)
    
    # Add spacing at the end
    st.markdown("")
    st.markdown("")

