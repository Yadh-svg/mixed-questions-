import re

with open('result_renderer.py', 'r', encoding='utf-8') as f:
    content = f.read()

helpers = '''
def render_duplication_controls(batch_key: str, question_key: str, q_num: str, render_context: str = "results"):
    """Render duplication checkboxes and input fields for a given question."""
    if render_context != "results":
        return
        
    import streamlit as st
    
    checkbox_key = f"duplicate_{render_context}_{batch_key}_{question_key}"
    count_key = f"duplicate_count_{render_context}_{batch_key}_{question_key}"
    
    # We add columns closely matching the old layout but adaptable to 3-stage
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
            # The duplication response gives us a json object with question_code and question1 containing the markdown
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

'''

# Inject the helper functions just before render_batch_results
content = content.replace('def render_batch_results(', helpers + '\ndef render_batch_results(')

# Inject the render_duplication_controls and render_generated_duplicates into the rendering loops
# We need to find the sections for MCQ, FIB, Descriptive, etc.

replacements = {
    # MCQ Handling
    "                            # Answer & Solution": "                            render_duplication_controls(batch_key, f'question{idx}', str(idx), render_context)\n                            render_generated_duplicates(batch_key, f'question{idx}', render_context)\n                            # Answer & Solution",
}

for old, new in replacements.items():
    content = content.replace(old, new)


with open('result_renderer.py', 'w', encoding='utf-8') as f:
    f.write(content)
