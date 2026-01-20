"""
Simplified Result Renderer for Streamlit Question Display
Renders questions in the new simplified format: { "question1": "markdown", "question2": "markdown" }
Question type is inferred from batch_key parameter.
"""
import streamlit as st
import json
import re
from typing import Dict, List, Any, Optional


def extract_json_objects(text: str) -> List[Dict[str, Any]]:
    """
    Robustly extract JSON objects from text by finding top-level brace pairs.
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
                        pass  # Ignore invalid blocks
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
    
    emoji = type_emoji_map.get(question_type, "❓")
    
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
        
        with col4:
            # Add copy-to-clipboard button with markdown stripping
            import streamlit.components.v1 as components
            import json
            
            copy_button_key = f"copy_{render_context}_{batch_key}_{question_key}"
            
            copy_html = f"""
            <div style="display: flex; align-items: center; justify-content: center; height: 50px;">
                <textarea id="text_{copy_button_key}" style="position: absolute; left: -9999px;">{markdown_content}</textarea>
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
                    
                    function stripMarkdownExceptTables(text) {{
                        const lines = text.split('\\n');
                        const processedLines = lines.map(line => {{
                            // Preserve table lines (contain |)
                            if (line.includes('|')) {{
                                return line;
                            }}
                            
                            // Remove markdown from other lines
                            let cleaned = line;
                            
                            // Remove headers (# ## ### etc.)
                            cleaned = cleaned.replace(/^#{1,6}\\s+/g, '');
                            
                            // Remove bold (**text** or __text__)
                            cleaned = cleaned.replace(/\\*\\*(.+?)\\*\\*/g, '$1');
                            cleaned = cleaned.replace(/__(.+?)__/g, '$1');
                            
                            // Remove italic (*text* or _text_)
                            cleaned = cleaned.replace(/\\*(.+?)\\*/g, '$1');
                            cleaned = cleaned.replace(/_(.+?)_/g, '$1');
                            
                            // Remove inline code (`code`)
                            cleaned = cleaned.replace(/`([^`]+)`/g, '$1');
                            
                            // Remove links [text](url) -> text
                            cleaned = cleaned.replace(/\\[([^\\]]+)\\]\\([^)]+\\)/g, '$1');
                            
                            // Remove images ![alt](url)
                            cleaned = cleaned.replace(/!\\[([^\\]]+)\\]\\([^)]+\\)/g, '');
                            
                            return cleaned;
                        }});
                        
                        return processedLines.join('\\n');
                    }}
                    
                    btn.addEventListener('click', function() {{
                        try {{
                            // Get original content
                            const originalText = textarea.value;
                            
                            // Strip markdown except tables
                            const cleanedText = stripMarkdownExceptTables(originalText);
                            
                            // Create temporary textarea with cleaned text
                            const tempTextarea = document.createElement('textarea');
                            tempTextarea.value = cleanedText;
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
    st.markdown(markdown_content)
    
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
                
                dup_copy_html = f"""
                <div style="display: flex; align-items: center; justify-content: center; height: 50px; margin-top: 8px;">
                    <textarea id="text_{dup_copy_key}" style="position: absolute; left: -9999px;">{dup_markdown}</textarea>
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
                        
                        function stripMarkdownExceptTables(text) {{
                            const lines = text.split('\\n');
                            const processedLines = lines.map(line => {{
                                // Preserve table lines (contain |)
                                if (line.includes('|')) {{
                                    return line;
                                }}
                                
                                // Remove markdown from other lines
                                let cleaned = line;
                                
                                // Remove headers (# ## ### etc.)
                                cleaned = cleaned.replace(/^#{'{1,6}'}\\s+/g, '');
                                
                                // Remove bold (**text** or __text__)
                                cleaned = cleaned.replace(/\\*\\*(.+?)\\*\\*/g, '$1');
                                cleaned = cleaned.replace(/__(.+?)__/g, '$1');
                                
                                // Remove italic (*text* or _text_)
                                cleaned = cleaned.replace(/\\*(.+?)\\*/g, '$1');
                                cleaned = cleaned.replace(/_(.+?)_/g, '$1');
                                
                                // Remove inline code (`code`)
                                cleaned = cleaned.replace(/`([^`]+)`/g, '$1');
                                
                                // Remove links [text](url) -> text
                                cleaned = cleaned.replace(/\\[([^\\]]+)\\]\\([^)]+\\)/g, '$1');
                                
                                // Remove images ![alt](url)
                                cleaned = cleaned.replace(/!\\[([^\\]]+)\\]\\([^)]+\\)/g, '');
                                
                                return cleaned;
                            }});
                            
                            return processedLines.join('\\n');
                        }}
                        
                        btn.addEventListener('click', function() {{
                            try {{
                                const originalText = textarea.value;
                                const cleanedText = stripMarkdownExceptTables(originalText);
                                
                                const tempTextarea = document.createElement('textarea');
                                tempTextarea.value = cleanedText;
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
    
    
    

def render_batch_results(batch_key: str, result_data: Dict[str, Any], render_context: str = "results"):
    """
    Main entry point to render a batch of results in the new simplified format.
    
    Args:
        batch_key: The question type (e.g., "MCQ", "Case Study", etc.)
        result_data: Dict containing 'text' with the JSON output
        render_context: Context identifier ("progressive" or "results") to prevent duplicate keys
    """
    # Get text content
    text_content = result_data.get('text', '')
    if not text_content:
        st.warning("No content to display.")
        return
    
    # Extract JSON objects
    json_objects = extract_json_objects(text_content)
    
    if not json_objects:
        st.warning(f"⚠️ Could not parse JSON output for {batch_key}. Showing raw text below.")
        with st.expander("Show Raw Output"):
            st.text(text_content)
        return
    
    # The new format should have a single JSON object with question1, question2, etc. keys
    # But handle both old validation wrapper and new format
    questions_dict = {}
    
    for obj in json_objects:
        # Check if this is a validation wrapper (old format)
        if 'CORRECTED_ITEM' in obj or 'corrected_item' in obj:
            corrected = obj.get('CORRECTED_ITEM') or obj.get('corrected_item')
            if isinstance(corrected, dict):
                # Merge corrected items into questions_dict
                for key, value in corrected.items():
                    if key.lower().startswith('question') or key.lower().startswith('q'):
                        questions_dict[key] = value
        else:
            # Direct format - merge all question keys
            for key, value in obj.items():
                if key.lower().startswith('question') or key.lower().startswith('q'):
                    questions_dict[key] = value
    
    # ERROR HANDLING: If standard extraction failed, try fallback extraction
    if not questions_dict:
        st.info(f"ℹ️ Standard format not detected for {batch_key}. Attempting fallback extraction...")
        questions_dict = extract_question_values_fallback(json_objects)
        
        if questions_dict:
            st.warning(f"⚠️ Structural mismatch detected! Extracted {len(questions_dict)} questions using fallback mechanism.")
        else:
            # Final fallback: show JSON
            st.error(f"❌ No questions found in output for {batch_key}. Displaying as JSON below.")
            with st.expander("Show Parsed JSON", expanded=True):
                st.json(json_objects)
            return
    
    # Success message
    st.success(f"✅ Successfully parsed {len(questions_dict)} {batch_key} questions")
    st.markdown("")  # spacing
    
    # Sort questions by number (question1, question2, question3, etc.)
    sorted_keys = sorted(questions_dict.keys(), 
                        key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)
    
    # Render each question
    for i, q_key in enumerate(sorted_keys, 1):
        # Add prominent separator between questions
        if i > 1:
            st.markdown("")
            st.markdown("")
            st.markdown("---")
            st.markdown("---")  # Double divider for prominence
            st.markdown("")
        
        markdown_content = questions_dict[q_key]
        
        # Handle both string and dict content
        if isinstance(markdown_content, dict):
            # Old format detected - convert to markdown
            st.warning(f"⚠️ {q_key}: Old format detected. Please update prompts to use new simplified format.")
            st.json(markdown_content)
        elif isinstance(markdown_content, str):
            # New format - render markdown directly
            render_markdown_question(q_key, markdown_content, batch_key, batch_key, render_context)
        else:
            st.error(f"⚠️ {q_key}: Unexpected content type: {type(markdown_content)}")
    
    # Add spacing at the end
    st.markdown("")
    st.markdown("")
