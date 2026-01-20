"""
Streamlit Question Generator Application
A modern UI for generating educational questions across multiple topics and types.
"""
import streamlit as st
import yaml
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
from st_img_pastebutton import paste
import io
import base64
import re

class PastedFile(io.BytesIO):
    """Wrapper to make pasted images look like UploadedFile objects"""
    def __init__(self, content, name="pasted_image.png", type="image/png"):
        if isinstance(content, str):
            if content.startswith("data:"):
                # Handle Data URI (e.g., data:image/png;base64,...)
                try:
                    header, encoded = content.split(",", 1)
                    content = base64.b64decode(encoded)
                    # Try to extract type from header
                    if "image/" in header:
                        type_match = re.search(r"image/(\w+)", header)
                        if type_match:
                            type = f"image/{type_match.group(1)}"
                            ext = type_match.group(1)
                            if not name.endswith(f".{ext}"):
                                name = f"pasted_image.{ext}"
                except Exception:
                    # Fallback or invalid data uri
                    pass
            else:
                # Try hex (original assumption)
                try:
                    content = bytes.fromhex(content)
                except ValueError:
                    # Try raw base64 as last resort
                    try:
                        content = base64.b64decode(content)
                    except Exception:
                        pass # Keep as is if all fails (likely to error later but allow debug)

        super().__init__(content)
        self.name = name
        self.type = type
        self.size = len(content)

# Page configuration
st.set_page_config(
    page_title="Question Generator",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern, catchy UI
st.markdown("""
<style>
    /* Main theme colors */
    :root {
        --primary-color: #6366f1;
        --secondary-color: #8b5cf6;
        --success-color: #10b981;
    }
    
    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .main-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: 700;
    }
    
    .main-header p {
        margin: 0.5rem 0 0 0;
        font-size: 1.1rem;
        opacity: 0.9;
    }
    
    /* Section headers */
    .section-header {
        background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%);
        color: white;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        margin: 1.5rem 0 1rem 0;
        font-weight: 600;
        font-size: 1.2rem;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 2rem;
        font-weight: 600;
        font-size: 1rem;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
    }
    
    /* Info boxes */
    .info-box {
        background: #eff6ff;
        border-left: 4px solid #3b82f6;
        padding: 1rem;
        border-radius: 4px;
        margin: 1rem 0;
    }
    
    /* Hide copy-to-clipboard buttons */
    button[title="Copy to clipboard"],
    button[data-testid="stCopyButton"],
    .copy-button,
    [data-testid="stMarkdownContainer"] button {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'question_types_config' not in st.session_state:
    st.session_state.question_types_config = {}
if 'generated_output' not in st.session_state:
    st.session_state.generated_output = None
if 'universal_pdf' not in st.session_state:
    st.session_state.universal_pdf = None

# Header
st.markdown("""
<div class="main-header">
    <h1>📚 AI Question Generator</h1>
    <p>Generate high-quality educational questions with advanced AI</p>
</div>
""", unsafe_allow_html=True)

# Sidebar for API configuration
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Enter your Gemini API key"
    )
    
    st.markdown("---")
    st.markdown("### 📊 Statistics")
    total_q = sum(config.get('count', 0) for config in st.session_state.question_types_config.values())
    st.metric("Total Questions", total_q)
    
    if st.session_state.question_types_config:
        st.markdown("**Question Types:**")
        for qtype, config in st.session_state.question_types_config.items():
            st.write(f"• {qtype}: {config.get('count', 0)}")

# Main content area
tab1, tab2 = st.tabs(["📝 Configure & Generate", "📄 Results"])

with tab1:
    st.markdown('<div class="section-header">General Information</div>', unsafe_allow_html=True)
    
    # Curriculum and Subject are hardcoded
    curriculum = "NCERT"
    subject = "Mathematics"
    
    grade = st.selectbox(
        "Grade",
        [f"Grade {i}" for i in range(1, 13)],
        help="Select the grade level",
        key="general_grade"
    )
    
    chapter = st.text_input(
        "Chapter/Unit Name",
        placeholder="e.g., Arithmetic Progressions",
        help="Enter the chapter or unit name",
        key="general_chapter"
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        old_concept = st.text_area(
            "Old Concepts (Prerequisites)",
            placeholder="Enter prerequisite knowledge the student already has...",
            height=150,
            help="Concepts students should already know",
            key="general_old_concept"
        )
    
    with col2:
        new_concept = st.text_area(
            "New Concepts (Current Chapter)",
            placeholder="Enter the concepts being taught in this chapter...",
            height=150,
            help="New concepts being taught",
            key="general_new_concept"
        )
    
    # Universal file upload option (PDF or Image)
    st.markdown("### 📄 Universal New Concept File (Optional)")
    st.info("💡 Upload a PDF or image that will be used for ALL questions that select 'New Concept File' as their source. This is a universal file that applies across all question types.")
    
    col_upload, col_paste = st.columns([3, 1])
    
    with col_upload:
        universal_pdf_upload = st.file_uploader(
            "Upload Universal New Concept File (PDF/Image)",
            type=['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'],
            key="universal_new_concept_pdf",
            help="This file will be used for all questions that select 'pdf' as their new concept source"
        )

    with col_paste:
        st.markdown("<br>", unsafe_allow_html=True)  # Align with uploader
        pasted_content = paste(label="📋 Paste Image", key="universal_paste_btn")
    
    # Logic to handle both upload and paste
    universal_pdf = None
    
    if universal_pdf_upload:
        universal_pdf = universal_pdf_upload
    elif pasted_content:
        # Convert pasted bytes to file-like object
        universal_pdf = PastedFile(pasted_content, name="pasted_universal_image.png")
    
    # Store in session state
    if universal_pdf:
        st.session_state.universal_pdf = universal_pdf
        st.success(f"✅ Universal file ready: {universal_pdf.name}")
    else:
        st.session_state.universal_pdf = None
    
    additional_notes = st.text_area(
        "Additional Notes (Optional)",
        placeholder="Any special instructions for question generation...",
        height=100,
        help="Extra instructions or configuration",
        key="general_additional_notes"
    )
    
    st.markdown("---")
    
    st.markdown('<div class="section-header">Question Types Configuration</div>', unsafe_allow_html=True)
    
    # Question type selection
    question_types = [
        "MCQ",
        "Fill in the Blanks",
        "Case Study",
        "Multi-Part",
        "Assertion-Reasoning",
        "Descriptive",
        "Descriptive w/ Subquestions"
    ]
    
    taxonomy_options = [
        "Remembering",
        "Understanding",
        "Applying",
        "Evaluating",
        "Analysing"
    ]
    
    # Initialize selected_types in session state if not exists
    if 'selected_question_types' not in st.session_state:
        st.session_state.selected_question_types = []
    
    # Add question type selector
    st.markdown("### Select Question Types to Configure")
    
    selected_types = st.multiselect(
        "Choose question types",
        question_types,
        default=st.session_state.selected_question_types,
        key="question_type_selector"
    )
    
    # Update session state with current selection
    st.session_state.selected_question_types = selected_types
    
    # Remove deselected types
    for qtype in list(st.session_state.question_types_config.keys()):
        if qtype not in selected_types:
            del st.session_state.question_types_config[qtype]
    
    # Configure each selected type
    for qtype in selected_types:
        if qtype not in st.session_state.question_types_config:
            # Initialize with 1 default question with empty values
            default_questions = []
            default_questions.append({
                'topic': '',
                'new_concept_source': 'pdf',  # Default to pdf
                'new_concept_pdf': None,
                'additional_notes_source': 'none',  # Default to none
                'additional_notes_text': '',  # Per-question additional notes text
                'additional_notes_pdf': None,
                'dok': 1,
                'marks': 1.0,
                'taxonomy': 'Remembering'
            })
            
            st.session_state.question_types_config[qtype] = {
                'count': 1, 
                'questions': default_questions
            }
        
        with st.expander(f"⚙️ {qtype} Configuration", expanded=True):
            # Number of questions for this type
            # Set max_value based on question type
            if qtype == "MCQ":
                max_questions = 34
            elif qtype in ["Fill in the Blanks", "Multi-Part"]:
                max_questions = 32
            else:
                max_questions = 20
            
            # Create columns for number input and max button
            col_input, col_button = st.columns([4, 1])
            
            # Initialize widget key if Max button was clicked
            widget_key = f"count_{qtype}"
            if widget_key not in st.session_state:
                st.session_state[widget_key] = st.session_state.question_types_config[qtype].get('count', 1)
            
            with col_button:
                # Add some spacing to align with the input
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("📊 Max", key=f"max_btn_{qtype}", help=f"Set to maximum ({max_questions})"):
                    st.session_state[widget_key] = max_questions
                    st.session_state.question_types_config[qtype]['count'] = max_questions
                    st.rerun()
            
            with col_input:
                num_questions = st.number_input(
                    f"Number of {qtype} Questions",
                    min_value=1,
                    max_value=max_questions,
                    key=widget_key
                )
            
            st.session_state.question_types_config[qtype]['count'] = num_questions
            
            # Initialize questions list if needed
            current_count = len(st.session_state.question_types_config[qtype].get('questions', []))
            if num_questions != current_count:
                if num_questions > current_count:
                    # Add new questions
                    for i in range(current_count, num_questions):
                        st.session_state.question_types_config[qtype]['questions'].append({
                            'topic': '',
                            'new_concept_source': 'pdf',  # Default to pdf
                            'new_concept_pdf': None,
                            'additional_notes_source': 'none',  # Default to none
                            'additional_notes_text': '',  # Per-question additional notes text
                            'additional_notes_pdf': None
                        })
                else:
                    # Remove excess
                    st.session_state.question_types_config[qtype]['questions'] = \
                        st.session_state.question_types_config[qtype]['questions'][:num_questions]
            
            # Type-specific configuration
            if qtype == "MCQ":
                st.markdown("#### MCQ Questions Configuration")
                for i in range(num_questions):
                    st.markdown(f"**Question {i+1}**")
                    cols = st.columns([3, 3, 1, 1, 2])
                    
                    with cols[0]:
                        topic = st.text_input(
                            "Topic",
                            key=f"mcq_topic_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('topic', ''),
                            placeholder="e.g., nth term of AP"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['topic'] = topic
                    
                    with cols[1]:
                        mcq_type_options = [
                            "Auto",
                            "Number Based",
                            "Image Based", 
                            "Real-World Word Questions",
                            "Real-World Image-Based Word Questions"
                        ]
                        current_type = st.session_state.question_types_config[qtype]['questions'][i].get('mcq_type', 'Auto')
                        mcq_type = st.selectbox(
                            "MCQ Type",
                            mcq_type_options,
                            key=f"mcq_type_{i}",
                            index=mcq_type_options.index(current_type) if current_type in mcq_type_options else 0
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['mcq_type'] = mcq_type

                    with cols[2]:
                        dok = st.selectbox(
                            "DOK",
                            [1, 2, 3],
                            key=f"mcq_dok_{i}",
                            index=st.session_state.question_types_config[qtype]['questions'][i].get('dok', 1) - 1
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['dok'] = dok
                    
                    with cols[3]:
                        marks = st.number_input(
                            "Marks",
                            min_value=0.5,
                            max_value=10.0,
                            step=0.5,
                            key=f"mcq_marks_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('marks', 1.0)
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['marks'] = marks
                    
                    with cols[4]:
                        taxonomy = st.selectbox(
                            "Taxonomy",
                            taxonomy_options,
                            key=f"mcq_taxonomy_{i}",
                            index=taxonomy_options.index(
                                st.session_state.question_types_config[qtype]['questions'][i].get('taxonomy', 'Remembering')
                            )
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['taxonomy'] = taxonomy
                    
                    # New Concept Source Selection (MANDATORY)
                    st.markdown("**New Concept Source:**")
                    new_concept_source = st.radio(
                        "Select new concept source",
                        options=["text", "pdf"],
                        format_func=lambda x: {
                            "text": "📝 Use Universal Text Concept",
                            "pdf": "📄 Use Universal File (PDF/Image)"
                        }[x],
                        key=f"mcq_new_concept_source_{i}",
                        index=["text", "pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('new_concept_source', 'pdf')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['new_concept_source'] = new_concept_source
                    
                    # Show info message based on selection
                    if new_concept_source == 'pdf':
                        if st.session_state.get('universal_pdf'):
                            st.info(f"ℹ️ Will use universal file: **{st.session_state.universal_pdf.name}**")
                        else:
                            st.warning("⚠️ Please upload a Universal File (PDF/Image) in the General Information section above")
                        st.session_state.question_types_config[qtype]['questions'][i]['new_concept_pdf'] = None
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['new_concept_pdf'] = None
                    
                    # Additional Notes Selection (OPTIONAL)
                    st.markdown("**Additional Notes (Optional):**")
                    col_cb1, col_cb2 = st.columns(2)
                    with col_cb1:
                        has_text_note = st.checkbox("Add Text Note", key=f"mcq_cb_text_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', '')))
                    with col_cb2:
                        has_file_note = st.checkbox("Add File", key=f"mcq_cb_file_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_pdf', None)))
                    
                    # Handle Text Note
                    if has_text_note:
                        additional_notes_text = st.text_area(
                            "Additional Notes Text",
                            key=f"mcq_additional_notes_text_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                            placeholder="Enter specific notes/instructions for this question...",
                            height=100
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                        
                    # Handle File Note
                    if has_file_note:
                        col_u, col_p = st.columns([3, 1])
                        with col_u:
                            an_upload = st.file_uploader(
                                "Upload Additional Notes File (PDF/Image)",
                                type=['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'],
                                key=f"mcq_additional_notes_pdf_{i}"
                            )
                        with col_p:
                            st.markdown("<br>", unsafe_allow_html=True)
                            an_paste = paste(label="📋 Paste", key=f"mcq_paste_{i}")
                        
                        an_final = None
                        if an_upload:
                            an_final = an_upload
                        elif an_paste:
                            an_final = PastedFile(an_paste, name=f"pasted_mcq_{i}.png")
                            
                        # Only update if a new file is provided or keep existing if not explicitly cleared? 
                        # Streamlit file uploader handles persistence usually within the run, but here we are manually mapping.
                        # We should trust the uploader's state for 'an_upload'.
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = an_final
                        
                        if an_final:
                            st.success(f"✅ Ready: {an_final.name}")
                    else:
                         st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                    
                    # Update source for compatibility
                    if has_text_note and has_file_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'both'
                    elif has_text_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'text'
                    elif has_file_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'pdf'
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'none'
                    
                    st.markdown("---")
            
            elif qtype == "Assertion-Reasoning":
                st.markdown("#### Assertion-Reasoning Configuration")
                st.info("ℹ️ Assertion-Reasoning questions have predefined configuration in the prompt. Only specify topics.")
                
                for i in range(num_questions):
                    topic = st.text_input(
                        f"Question {i+1} Topic",
                        key=f"ar_topic_{i}",
                        value=st.session_state.question_types_config[qtype]['questions'][i].get('topic', ''),
                        placeholder="e.g., Properties of AP"
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['topic'] = topic
                    
                    # New Concept Source Selection (MANDATORY)
                    st.markdown("**New Concept Source:**")
                    new_concept_source = st.radio(
                        "Select new concept source",
                        options=["text", "pdf"],
                        format_func=lambda x: {
                            "text": "📝 Use Universal Text Concept",
                            "pdf": "📄 Use Universal File (PDF/Image)"
                        }[x],
                        key=f"ar_new_concept_source_{i}",
                        index=["text", "pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('new_concept_source', 'pdf')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['new_concept_source'] = new_concept_source
                    
                    if new_concept_source == 'pdf':
                        if st.session_state.get('universal_pdf'):
                            st.info(f"ℹ️ Will use universal file: **{st.session_state.universal_pdf.name}**")
                        else:
                            st.warning("⚠️ Please upload a Universal File (PDF/Image) in the General Information section above")
                        st.session_state.question_types_config[qtype]['questions'][i]['new_concept_pdf'] = None
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['new_concept_pdf'] = None
                    
                    # Additional Notes Selection (OPTIONAL)
                    st.markdown("**Additional Notes (Optional):**")
                    col_cb1, col_cb2 = st.columns(2)
                    with col_cb1:
                        has_text_note = st.checkbox("Add Text Note", key=f"ar_cb_text_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', '')))
                    with col_cb2:
                        has_file_note = st.checkbox("Add File", key=f"ar_cb_file_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_pdf', None)))

                    # Handle Text Note
                    if has_text_note:
                        additional_notes_text = st.text_area(
                            "Additional Notes Text",
                            key=f"ar_additional_notes_text_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                            placeholder="Enter specific notes/instructions for this question...",
                            height=100
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''

                    # Handle File Note
                    if has_file_note:
                        col_u, col_p = st.columns([3, 1])
                        with col_u:
                            an_upload = st.file_uploader(
                                "Upload Additional Notes File (PDF/Image)",
                                type=['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'],
                                key=f"ar_additional_notes_pdf_{i}"
                            )
                        with col_p:
                            st.markdown("<br>", unsafe_allow_html=True)
                            an_paste = paste(label="📋 Paste", key=f"ar_paste_{i}")
                            
                        an_final = None
                        if an_upload:
                            an_final = an_upload
                        elif an_paste:
                            an_final = PastedFile(an_paste, name=f"pasted_ar_{i}.png")

                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = an_final
                        if an_final:
                            st.success(f"✅ Ready: {an_final.name}")
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None

                    # Update source for compatibility
                    if has_text_note and has_file_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'both'
                    elif has_text_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'text'
                    elif has_file_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'pdf'
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'none'
                    
                    st.markdown("---")
            
            elif qtype == "Fill in the Blanks":
                st.markdown("#### Fill in the Blanks Configuration")
                
                # Per-question config with subparts
                for i in range(num_questions):
                    st.markdown(f"**Question {i+1}**")
                    
                    # Topic field
                    topic = st.text_input(
                        "Topic",
                        key=f"fib_topic_{i}",
                        value=st.session_state.question_types_config[qtype]['questions'][i].get('topic', ''),
                        placeholder="e.g., nth term of AP"
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['topic'] = topic
                    
                    # Number of subparts for this specific question
                    num_subparts = st.number_input(
                        "Number of Sub-Parts",
                        min_value=1,
                        max_value=5,
                        value=st.session_state.question_types_config[qtype]['questions'][i].get('num_subparts', 1),
                        key=f"fib_subparts_{i}",
                        help="Set to 1 for single-part, or 2-5 for questions with roman numeral subparts (i, ii, iii, etc.)"
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['num_subparts'] = num_subparts
                    
                    # FIB Type Selector
                    fib_types = ["Auto", "Number Based", "Image Based", "Real-World Word Questions", "Real-World Image-Based Word Questions"]
                    fib_type = st.selectbox(
                        "FIB Type",
                        fib_types,
                        key=f"fib_type_select_{i}",
                        index=fib_types.index(st.session_state.question_types_config[qtype]['questions'][i].get('fib_type', 'Auto'))
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['fib_type'] = fib_type
                    
                    # If single-part (num_subparts = 1), show DOK, Marks, Taxonomy directly
                    if num_subparts == 1:
                        cols = st.columns([1, 1, 2])
                        
                        with cols[0]:
                            dok = st.selectbox(
                                "DOK",
                                [1, 2, 3],
                                key=f"fib_dok_{i}",
                                index=st.session_state.question_types_config[qtype]['questions'][i].get('dok', 1) - 1
                            )
                            st.session_state.question_types_config[qtype]['questions'][i]['dok'] = dok
                        
                        with cols[1]:
                            marks = st.number_input(
                                "Marks",
                                min_value=0.5,
                                max_value=10.0,
                                step=0.5,
                                key=f"fib_marks_{i}",
                                value=st.session_state.question_types_config[qtype]['questions'][i].get('marks', 1.0)
                            )
                            st.session_state.question_types_config[qtype]['questions'][i]['marks'] = marks
                        
                        with cols[2]:
                            taxonomy = st.selectbox(
                                "Taxonomy",
                                taxonomy_options,
                                key=f"fib_taxonomy_{i}",
                                index=taxonomy_options.index(
                                    st.session_state.question_types_config[qtype]['questions'][i].get('taxonomy', 'Remembering')
                                )
                            )
                            st.session_state.question_types_config[qtype]['questions'][i]['taxonomy'] = taxonomy
                    
                    else:
                        # Multi-part: show subpart configuration
                        # Initialize subparts for this question
                        if 'subparts_config' not in st.session_state.question_types_config[qtype]['questions'][i]:
                            st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'] = []
                        
                        current_subparts = len(st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'])
                        if num_subparts != current_subparts:
                            if num_subparts > current_subparts:
                                for j in range(current_subparts, num_subparts):
                                    roman_numerals = ['i', 'ii', 'iii', 'iv', 'v']
                                    st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'].append({
                                        'part': roman_numerals[j] if j < len(roman_numerals) else f'part_{j+1}',
                                        'dok': 1,
                                        'marks': 1.0,
                                        'taxonomy': 'Remembering'
                                    })
                            else:
                                st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'] = \
                                    st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][:num_subparts]
                        
                        # Subparts config
                        st.markdown("**Sub-Parts Configuration**")
                        for j in range(num_subparts):
                            cols = st.columns([1, 1, 1, 2])
                            roman_numerals = ['i', 'ii', 'iii', 'iv', 'v']
                            
                            with cols[0]:
                                st.markdown(f"Part ({roman_numerals[j] if j < len(roman_numerals) else j+1})")
                            
                            with cols[1]:
                                dok = st.selectbox(
                                    "DOK",
                                    [1, 2, 3],
                                    key=f"fib_subpart_dok_{i}_{j}",
                                    index=st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j].get('dok', 1) - 1
                                )
                                st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j]['dok'] = dok
                            
                            with cols[2]:
                                marks = st.number_input(
                                    "Marks",
                                    min_value=0.5,
                                    max_value=10.0,
                                    step=0.5,
                                    key=f"fib_subpart_marks_{i}_{j}",
                                    value=st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j].get('marks', 1.0)
                                )
                                st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j]['marks'] = marks
                            
                            with cols[3]:
                                taxonomy = st.selectbox(
                                    "Taxonomy",
                                    taxonomy_options,
                                    key=f"fib_subpart_taxonomy_{i}_{j}",
                                    index=taxonomy_options.index(
                                        st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j].get('taxonomy', 'Remembering')
                                    )
                                )
                                st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j]['taxonomy'] = taxonomy
                    
                    # New Concept Source Selection (MANDATORY)
                    st.markdown("**New Concept Source:**")
                    new_concept_source = st.radio(
                        "Select new concept source",
                        options=["text", "pdf"],
                        format_func=lambda x: {
                            "text": "📝 Use Universal Text Concept",
                            "pdf": "📄 Use Universal File (PDF/Image)"
                        }[x],
                        key=f"fib_new_concept_source_{i}",
                        index=["text", "pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('new_concept_source', 'pdf')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['new_concept_source'] = new_concept_source
                    
                    if new_concept_source == 'pdf':
                        if st.session_state.get('universal_pdf'):
                            st.info(f"ℹ️ Will use universal file: **{st.session_state.universal_pdf.name}**")
                        else:
                            st.warning("⚠️ Please upload a Universal File (PDF/Image) in the General Information section above")
                        st.session_state.question_types_config[qtype]['questions'][i]['new_concept_pdf'] = None
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['new_concept_pdf'] = None
                    
                    # Additional Notes Selection (OPTIONAL)
                    st.markdown("**Additional Notes (Optional):**")
                    col_cb1, col_cb2 = st.columns(2)
                    with col_cb1:
                        has_text_note = st.checkbox("Add Text Note", key=f"fib_cb_text_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', '')))
                    with col_cb2:
                        has_file_note = st.checkbox("Add File", key=f"fib_cb_file_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_pdf', None)))

                    # Handle Text Note
                    if has_text_note:
                        additional_notes_text = st.text_area(
                            "Additional Notes Text",
                            key=f"fib_additional_notes_text_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                            placeholder="Enter specific notes/instructions for this question...",
                            height=100
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''

                    # Handle File Note
                    if has_file_note:
                        col_u, col_p = st.columns([3, 1])
                        with col_u:
                            an_upload = st.file_uploader(
                                "Upload Additional Notes File (PDF/Image)",
                                type=['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'],
                                key=f"fib_additional_notes_pdf_{i}"
                            )
                        with col_p:
                            st.markdown("<br>", unsafe_allow_html=True)
                            an_paste = paste(label="📋 Paste", key=f"fib_paste_{i}")
                            
                        an_final = None
                        if an_upload:
                            an_final = an_upload
                        elif an_paste:
                            an_final = PastedFile(an_paste, name=f"pasted_fib_{i}.png")

                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = an_final
                        if an_final:
                            st.success(f"✅ Ready: {an_final.name}")
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                        
                    # Update source for compatibility
                    if has_text_note and has_file_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'both'
                    elif has_text_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'text'
                    elif has_file_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'pdf'
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'none'
                    
                    st.markdown("---")
            
            elif qtype in ["Descriptive", "Descriptive w/ Subquestions"]:
                st.markdown(f"#### {qtype} Configuration")
                for i in range(num_questions):
                    st.markdown(f"**Question {i+1}**")
                    cols = st.columns([2, 2, 1, 1, 2])
                    
                    with cols[0]:
                        topic = st.text_input(
                            "Topic",
                            key=f"{qtype}_topic_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('topic', ''),
                            placeholder="e.g., nth term of AP"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['topic'] = topic
                    
                    with cols[1]:
                        descriptive_type_options = [
                            "Auto",
                            "Descriptive (Number Based)",
                            "Descriptive (Image Based)",
                            "Descriptive (Real World Word Questions)",
                            "Descriptive (Real World Image-Based Word Questions)"
                        ]
                        descriptive_type = st.selectbox(
                            "Descriptive Type",
                            descriptive_type_options,
                            key=f"{qtype}_type_{i}",
                            index=descriptive_type_options.index(
                                st.session_state.question_types_config[qtype]['questions'][i].get('descriptive_type', 'Auto')
                            )
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['descriptive_type'] = descriptive_type

                    with cols[2]:
                        dok = st.selectbox(
                            "DOK",
                            [1, 2, 3],
                            key=f"{qtype}_dok_{i}",
                            index=st.session_state.question_types_config[qtype]['questions'][i].get('dok', 1) - 1
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['dok'] = dok
                    
                    with cols[3]:
                        marks = st.number_input(
                            "Marks",
                            min_value=0.5,
                            max_value=10.0,
                            step=0.5,
                            key=f"{qtype}_marks_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('marks', 1.0)
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['marks'] = marks
                    
                    with cols[4]:
                        taxonomy = st.selectbox(
                            "Taxonomy",
                            taxonomy_options,
                            key=f"{qtype}_taxonomy_{i}",
                            index=taxonomy_options.index(
                                st.session_state.question_types_config[qtype]['questions'][i].get('taxonomy', 'Remembering')
                            )
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['taxonomy'] = taxonomy
                    
                    # New Concept Source Selection (MANDATORY)
                    st.markdown("**New Concept Source:**")
                    new_concept_source = st.radio(
                        "Select new concept source",
                        options=["text", "pdf"],
                        format_func=lambda x: {
                            "text": "📝 Use Universal Text Concept",
                            "pdf": "📄 Use Universal File (PDF/Image)"
                        }[x],
                        key=f"{qtype}_new_concept_source_{i}",
                        index=["text", "pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('new_concept_source', 'pdf')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['new_concept_source'] = new_concept_source
                    
                    if new_concept_source == 'pdf':
                        if st.session_state.get('universal_pdf'):
                            st.info(f"ℹ️ Will use universal file: **{st.session_state.universal_pdf.name}**")
                        else:
                            st.warning("⚠️ Please upload a Universal File (PDF/Image) in the General Information section above")
                        st.session_state.question_types_config[qtype]['questions'][i]['new_concept_pdf'] = None
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['new_concept_pdf'] = None
                    
                    # Additional Notes Selection (OPTIONAL)
                    st.markdown("**Additional Notes (Optional):**")
                    col_cb1, col_cb2 = st.columns(2)
                    with col_cb1:
                        has_text_note = st.checkbox("Add Text Note", key=f"{qtype}_cb_text_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', '')))
                    with col_cb2:
                        has_file_note = st.checkbox("Add File", key=f"{qtype}_cb_file_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_pdf', None)))

                    # Handle Text Note
                    if has_text_note:
                        additional_notes_text = st.text_area(
                            "Additional Notes Text",
                            key=f"{qtype}_additional_notes_text_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                            placeholder="Enter specific notes/instructions for this question...",
                            height=100
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''

                    # Handle File Note
                    if has_file_note:
                        col_u, col_p = st.columns([3, 1])
                        with col_u:
                            an_upload = st.file_uploader(
                                "Upload Additional Notes File (PDF/Image)",
                                type=['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'],
                                key=f"{qtype}_additional_notes_pdf_{i}"
                            )
                        with col_p:
                            st.markdown("<br>", unsafe_allow_html=True)
                            an_paste = paste(label="📋 Paste", key=f"{qtype}_paste_{i}")
                            
                        an_final = None
                        if an_upload:
                            an_final = an_upload
                        elif an_paste:
                            an_final = PastedFile(an_paste, name=f"pasted_{qtype}_{i}.png")

                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = an_final
                        if an_final:
                            st.success(f"✅ Ready: {an_final.name}")
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                        
                    # Update source for compatibility
                    if has_text_note and has_file_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'both'
                    elif has_text_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'text'
                    elif has_file_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'pdf'
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'none'
                    
                    st.markdown("---")
            
            elif qtype == "Case Study":
                st.markdown("#### Case Study Configuration")
                
                for i in range(num_questions):
                    st.markdown(f"**Case Study {i+1}**")
                    
                    topic = st.text_input(
                        "Topic",
                        key=f"case_topic_{i}",
                        value=st.session_state.question_types_config[qtype]['questions'][i].get('topic', ''),
                        placeholder="e.g., Applications of AP"
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['topic'] = topic
                    
                    # New Concept Source Selection (MANDATORY)
                    st.markdown("**New Concept Source:**")
                    new_concept_source = st.radio(
                        "Select new concept source",
                        options=["text", "pdf"],
                        format_func=lambda x: {
                            "text": "📝 Use Universal Text Concept",
                            "pdf": "📄 Use Universal File (PDF/Image)"
                        }[x],
                        key=f"case_new_concept_source_{i}",
                        index=["text", "pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('new_concept_source', 'pdf')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['new_concept_source'] = new_concept_source
                    
                    if new_concept_source == 'pdf':
                        if st.session_state.get('universal_pdf'):
                            st.info(f"ℹ️ Will use universal file: **{st.session_state.universal_pdf.name}**")
                        else:
                            st.warning("⚠️ Please upload a Universal File (PDF/Image) in the General Information section above")
                        st.session_state.question_types_config[qtype]['questions'][i]['new_concept_pdf'] = None
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['new_concept_pdf'] = None
                    
                    # Additional Notes Selection (OPTIONAL)
                    st.markdown("**Additional Notes (Optional):**")
                    col_cb1, col_cb2 = st.columns(2)
                    with col_cb1:
                        has_text_note = st.checkbox("Add Text Note", key=f"case_cb_text_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', '')))
                    with col_cb2:
                        has_file_note = st.checkbox("Add File", key=f"case_cb_file_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_pdf', None)))

                    # Handle Text Note
                    if has_text_note:
                        additional_notes_text = st.text_area(
                            "Additional Notes Text",
                            key=f"case_additional_notes_text_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                            placeholder="Enter specific notes/instructions for this question...",
                            height=100
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''

                    # Handle File Note
                    if has_file_note:
                        # Use file uploader directly as per original Case Study block (which seemed to miss the paste button in the original code, but I'll add checking the original code again... wait, Case Study specific block in original code didn't have paste button in the reading? Let me check line 1017. It says `additional_notes_pdf = st.file_uploader(...)`. It didn't have paste. I should probably ADD paste for consistency, or keep it simple. I'll stick to original functionality + checkboxes, but wait, the plan implies consistency. I will add paste for consistency as it's better.)
                        # Actually, looking at the previous blocks, paste was added. I'll add paste here too to be consistent with others.
                        col_u, col_p = st.columns([3, 1])
                        with col_u:
                             an_upload = st.file_uploader(
                                "Upload Additional Notes File (PDF/Image)",
                                type=['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'],
                                key=f"case_additional_notes_pdf_{i}"
                            )
                        with col_p:
                            st.markdown("<br>", unsafe_allow_html=True)
                            an_paste = paste(label="📋 Paste", key=f"case_paste_{i}")
                        
                        an_final = None
                        if an_upload:
                            an_final = an_upload
                        elif an_paste:
                            an_final = PastedFile(an_paste, name=f"pasted_case_{i}.png")
                            
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = an_final
                        if an_final:
                            st.success(f"✅ Ready: {an_final.name}")
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None

                    # Update source for compatibility
                    if has_text_note and has_file_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'both'
                    elif has_text_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'text'
                    elif has_file_note:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'pdf'
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'none'
                    
                    # Number of subparts
                    num_subparts = st.number_input(
                        "Number of Sub-Parts",
                        min_value=2,
                        max_value=5,
                        value=st.session_state.question_types_config[qtype]['questions'][i].get('num_subparts', 3),
                        key=f"case_subparts_{i}"
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['num_subparts'] = num_subparts
                    
                    # Initialize subparts
                    if 'subparts' not in st.session_state.question_types_config[qtype]['questions'][i]:
                        st.session_state.question_types_config[qtype]['questions'][i]['subparts'] = []
                    
                    current_subparts = len(st.session_state.question_types_config[qtype]['questions'][i]['subparts'])
                    if num_subparts != current_subparts:
                        if num_subparts > current_subparts:
                            for j in range(current_subparts, num_subparts):
                                st.session_state.question_types_config[qtype]['questions'][i]['subparts'].append({
                                    'part': chr(97 + j),
                                    'dok': 1,
                                    'marks': 1.0
                                })
                        else:
                            st.session_state.question_types_config[qtype]['questions'][i]['subparts'] = \
                                st.session_state.question_types_config[qtype]['questions'][i]['subparts'][:num_subparts]
                    
                    # Subparts config (NO Taxonomy for Case Study)
                    st.markdown("**Sub-Parts Configuration** (No Taxonomy needed)")
                    for j in range(num_subparts):
                        cols = st.columns([1, 1, 1])
                        
                        with cols[0]:
                            st.markdown(f"Part ({chr(97 + j)})")
                        
                        with cols[1]:
                            dok = st.selectbox(
                                "DOK",
                                [1, 2, 3],
                                key=f"case_subpart_dok_{i}_{j}",
                                index=st.session_state.question_types_config[qtype]['questions'][i]['subparts'][j].get('dok', 1) - 1
                            )
                            st.session_state.question_types_config[qtype]['questions'][i]['subparts'][j]['dok'] = dok
                        
                        with cols[2]:
                            marks = st.number_input(
                                "Marks",
                                min_value=0.5,
                                max_value=10.0,
                                step=0.5,
                                key=f"case_subpart_marks_{i}_{j}",
                                value=st.session_state.question_types_config[qtype]['questions'][i]['subparts'][j].get('marks', 1.0)
                            )
                            st.session_state.question_types_config[qtype]['questions'][i]['subparts'][j]['marks'] = marks
                    
                    st.markdown("---")
            
            elif qtype == "Multi-Part":
                st.markdown("#### Multi-Part Configuration")
                st.info("Configure each Multi-Part question individually. You can define specific sub-parts for each question.")
                
                # Per-question config
                for i in range(num_questions):
                    with st.expander(f"Question {i+1} Configuration", expanded=True):
                        
                        # Add Topic field
                        topic = st.text_input(
                            "Topic",
                            key=f"multipart_topic_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('topic', ''),
                            placeholder="e.g., nth term of AP"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['topic'] = topic
                        
                        # New Concept Source Selection
                        st.markdown("**New Concept Source:**")
                        new_concept_source = st.radio(
                            "Select new concept source",
                            options=["text", "pdf"],
                            format_func=lambda x: {
                                "text": "📝 Use Universal Text Concept",
                                "pdf": "📄 Use Universal File (PDF/Image)"
                            }[x],
                            key=f"multipart_new_concept_source_{i}",
                            index=["text", "pdf"].index(
                                st.session_state.question_types_config[qtype]['questions'][i].get('new_concept_source', 'pdf')
                            ),
                            horizontal=True
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['new_concept_source'] = new_concept_source
                        
                        if new_concept_source == 'pdf':
                            if st.session_state.get('universal_pdf'):
                                st.info(f"ℹ️ Will use universal file: **{st.session_state.universal_pdf.name}**")
                            else:
                                st.warning("⚠️ Please upload a Universal File (PDF/Image) in the General Information section above")
                        
                        # Additional Notes Selection (OPTIONAL)
                        st.markdown("**Additional Notes (Optional):**")
                        col_cb1, col_cb2 = st.columns(2)
                        with col_cb1:
                            has_text_note = st.checkbox("Add Text Note", key=f"multipart_cb_text_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', '')))
                        with col_cb2:
                            has_file_note = st.checkbox("Add File", key=f"multipart_cb_file_{i}", value=bool(st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_pdf', None)))

                        # Handle Text Note
                        if has_text_note:
                            additional_notes_text = st.text_area(
                                "Additional Notes Text",
                                key=f"multipart_additional_notes_text_{i}",
                                value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                                placeholder="Enter specific notes/instructions for this question...",
                                height=100
                            )
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                        else:
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''

                        # Handle File Note
                        if has_file_note:
                            col_u, col_p = st.columns([3, 1])
                            with col_u:
                                an_upload = st.file_uploader(
                                    "Upload Additional Notes File (PDF/Image)",
                                    type=['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'],
                                    key=f"multipart_additional_notes_pdf_{i}"
                                )
                            with col_p:
                                st.markdown("<br>", unsafe_allow_html=True)
                                an_paste = paste(label="📋 Paste", key=f"multipart_paste_{i}")
                            
                            an_final = None
                            if an_upload:
                                an_final = an_upload
                            elif an_paste:
                                an_final = PastedFile(an_paste, name=f"pasted_multipart_{i}.png")
                                
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = an_final
                            if an_final:
                                st.success(f"✅ Ready: {an_final.name}")
                        else:
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None

                        # Update source for compatibility
                        if has_text_note and has_file_note:
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'both'
                        elif has_text_note:
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'text'
                        elif has_file_note:
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'pdf'
                        else:
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = 'none'
                        
                        st.markdown("---")
                        
                        # Sub-Part Configuration (Per Question)
                        st.markdown("**Sub-Parts Configuration**")
                        
                        num_subparts = st.number_input(
                            "Number of Sub-Parts",
                            min_value=2,
                            max_value=5,
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('num_subparts', 2),
                            key=f"multipart_subparts_{i}"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['num_subparts'] = num_subparts
                        
                        # Multi-Part Type Selector
                        multipart_types = ["Auto", "Number Based", "Image Based", "Real-World Word Questions", "Real-World Image-Based Word Questions"]
                        multipart_type = st.selectbox(
                            "Multi-Part Type",
                            multipart_types,
                            key=f"multipart_type_select_{i}",
                            index=multipart_types.index(st.session_state.question_types_config[qtype]['questions'][i].get('multipart_type', 'Auto'))
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['multipart_type'] = multipart_type
                        
                        # Initialize subparts config for this question
                        if 'subparts_config' not in st.session_state.question_types_config[qtype]['questions'][i]:
                            st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'] = []
                        
                        # Adjust list length
                        current_subparts = len(st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'])
                        if num_subparts != current_subparts:
                            if num_subparts > current_subparts:
                                for j in range(current_subparts, num_subparts):
                                    st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'].append({
                                        'part': chr(97 + j),
                                        'dok': 1,
                                        'marks': 1.0,
                                        'taxonomy': 'Remembering'
                                    })
                            else:
                                st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'] = \
                                    st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][:num_subparts]
                        
                        # Render subpart inputs
                        for j in range(num_subparts):
                            cols = st.columns([1, 1, 1, 2])
                            
                            with cols[0]:
                                st.markdown(f"**Part ({chr(97 + j)})**")
                            
                            with cols[1]:
                                dok = st.selectbox(
                                    "DOK",
                                    [1, 2, 3],
                                    key=f"multipart_subpart_dok_{i}_{j}",
                                    index=st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j].get('dok', 1) - 1
                                )
                                st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j]['dok'] = dok
                            
                            with cols[2]:
                                marks = st.number_input(
                                    "Marks",
                                    min_value=0.5,
                                    max_value=10.0,
                                    step=0.5,
                                    key=f"multipart_subpart_marks_{i}_{j}",
                                    value=st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j].get('marks', 1.0)
                                )
                                st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j]['marks'] = marks
                            
                            with cols[3]:
                                taxonomy = st.selectbox(
                                    "Taxonomy",
                                    taxonomy_options,
                                    key=f"multipart_subpart_taxonomy_{i}_{j}",
                                    index=taxonomy_options.index(
                                        st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j].get('taxonomy', 'Remembering')
                                    )
                                )
                                st.session_state.question_types_config[qtype]['questions'][i]['subparts_config'][j]['taxonomy'] = taxonomy
                        
                        st.markdown("---")

    # Generate button at the bottom of configuration
    st.markdown('<div class="section-header">Generate Questions</div>', unsafe_allow_html=True)
    
    if not api_key:
        st.warning("⚠️ Please enter your Gemini API key in the sidebar to continue.")
    else:
        
        if st.button("🚀 Generate All Questions", type="primary", use_container_width=True):
            if not chapter:
                st.error("❌ Please enter a chapter name")
            elif not st.session_state.question_types_config:
                st.error("❌ Please configure at least one question type")
            else:
                # Validate that all questions have topics
                missing_topics = []
                
                for qtype, config in st.session_state.question_types_config.items():
                    for i, q in enumerate(config.get('questions', []), 1):
                        if not q.get('topic', '').strip():
                            missing_topics.append(f"{qtype} Question {i}")
                
                if missing_topics:
                    st.error(f"❌ Please specify topics for: {', '.join(missing_topics)}")
                else:
                    # Prepare general config
                    config = {
                        'curriculum': curriculum,
                        'grade': grade,
                        'subject': subject,
                        'chapter': chapter,
                        'old_concept': old_concept,
                        'new_concept': new_concept,
                        'additional_notes': additional_notes,
                        'api_key': api_key,
                        'universal_pdf': st.session_state.get('universal_pdf')  # Pass universal PDF
                    }
                    
                    # Process each question type
                    questions_list = []
                    for qtype, type_config in st.session_state.question_types_config.items():
                        questions = type_config.get('questions', [])
                        for q in questions:
                            # Ensure type is set
                            q['type'] = qtype
                            questions_list.append(q)
                    
                    if questions_list:
                        # Run async pipeline
                        with st.spinner("🔄 Starting question generation pipeline..."):
                            try:
                                # Import here to avoid circular imports
                                from batch_processor import process_batches_pipeline
                                
                                # Run async pipeline without progressive UI callback
                                # Results will be available in Results tab only
                                final_results = asyncio.run(
                                    process_batches_pipeline(
                                        questions_config=questions_list,
                                        general_config=config,
                                        progress_callback=None  # Disable progressive rendering
                                    )
                                )
                                
                                # Clear all duplicate-related session state keys before storing new results
                                # This prevents old duplicates from appearing with new questions
                                keys_to_remove = [key for key in st.session_state.keys() if key.startswith('duplicates_')]
                                for key in keys_to_remove:
                                    del st.session_state[key]
                                
                                # Also clear duplicate checkbox states
                                keys_to_remove = [key for key in st.session_state.keys() if key.startswith('duplicate_results_')]
                                for key in keys_to_remove:
                                    del st.session_state[key]
                                
                                keys_to_remove = [key for key in st.session_state.keys() if key.startswith('duplicate_count_results_')]
                                for key in keys_to_remove:
                                    del st.session_state[key]
                                
                                # Store final results
                                st.session_state.generated_output = final_results
                                
                                st.success("✅ All questions generated successfully! Go to the Results tab to view and manage them.")
                                
                            except Exception as e:
                                st.error(f"❌ Error during generation: {str(e)}")
                                st.exception(e)
                    else:
                        st.warning("No questions found to process.")
        # Progressive rendering already displays results during generation
        # No need to duplicate the display here anymore


with tab2:
    st.markdown('<div class="section-header">Previously Generated Questions</div>', unsafe_allow_html=True)
    
    if st.session_state.generated_output:
        results = st.session_state.generated_output
        
        # Import renderer (if not already imported in scope, but safest to import here too if needed or rely on top level if used)
        from result_renderer import render_batch_results # Safe re-import inside function/block

        # Display results for each batch
        for batch_key, batch_result in results.items():
            with st.expander(f"📋 {batch_key}", expanded=True):
                
                # Extract raw and validated results
                raw_res = batch_result.get('raw', {})
                val_res = batch_result.get('validated', {})
                
                # Display Validated Content
                if val_res and not val_res.get('error'):
                        st.markdown("### ✅ Validated Output")
                        # Use the new renderer with "results" context
                        render_batch_results(batch_key, val_res, render_context="results")
                elif val_res and val_res.get('error'):
                        st.error(f"❌ Validation Error: {val_res['error']}")
                        st.error(val_res.get('text', ''))
                else:
                        st.warning("⚠️ Validation step missing or failed silently.")

                # Show Metadata
                st.markdown("---")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Questions", raw_res.get('question_count', 'N/A'))
                with col2:
                    raw_time = raw_res.get('elapsed', 0)
                    val_time = val_res.get('elapsed', 0) if val_res else 0
                    st.metric("Total Time", f"{raw_time + val_time:.2f}s")

                # Expandable Raw Output
                with st.expander("Show Generated Version (Raw Backend Output)"):
                    st.text_area("Raw Generator Output", value=raw_res.get('text', 'No output'), height=300, disabled=True, key=f"raw_bak_{batch_key}")
                
                with st.expander("Show Validation Response (Raw Backend Output)"):
                    if val_res.get('error'):
                        st.error(f"Validation Error: {val_res['error']}")
                    st.text_area("Raw Validation Output", value=val_res.get('text', 'No output'), height=300, disabled=True, key=f"val_bak_{batch_key}")
        
        # Download option
        st.markdown("---")
        
        # Combine all results
        combined_output = ""
        for batch_key, batch_result in results.items():
            val_res = batch_result.get('validated', {})
            raw_res = batch_result.get('raw', {})
            final_text = val_res.get('text', '') if val_res else raw_res.get('text', 'Error')

            combined_output += f"\n\n{'='*80}\n"
            combined_output += f"BATCH: {batch_key}\n"
            combined_output += f"{'='*80}\n\n"
            combined_output += final_text
        
        st.download_button(
            label="📥 Download All Questions",
            data=combined_output,
            file_name="generated_questions.md",
            mime="text/markdown",
            use_container_width=True,
            key="download_inline_results"
        )
        
        # Add Generate Duplicates section
        st.markdown("---")
        st.markdown('<div class="section-header">🔄 Generate Question Duplicates</div>', unsafe_allow_html=True)
        
        # Collect selected questions from checkbox states
        # This happens only when rendering, not when clicking checkboxes
        selected_questions = {}
        
        # Iterate through all rendered questions and check their checkbox states
        for batch_key, batch_result in results.items():
            val_res = batch_result.get('validated', {})
            text_content = val_res.get('text', '')
            
            if text_content:
                # Extract JSON to get question keys
                from result_renderer import extract_json_objects
                json_objects = extract_json_objects(text_content)
                
                for obj in json_objects:
                    # Handle validation wrapper
                    questions_to_check = {}
                    if 'CORRECTED_ITEM' in obj or 'corrected_item' in obj:
                        corrected = obj.get('CORRECTED_ITEM') or obj.get('corrected_item')
                        if isinstance(corrected, dict):
                            questions_to_check = corrected
                    else:
                        questions_to_check = obj
                    
                    # Check each question
                    for q_key, q_content in questions_to_check.items():
                        if q_key.lower().startswith('question') or q_key.lower().startswith('q'):
                            # Use 'results' context to match the render context
                            checkbox_key = f"duplicate_results_{batch_key}_{q_key}"
                            count_key = f"duplicate_count_results_{batch_key}_{q_key}"
                            
                            # Check if checkbox is selected
                            if st.session_state.get(checkbox_key, False):
                                # Create unique question code with batch type prefix
                                # Extract question number from q_key (e.g., "question1" -> "1")
                                q_num = q_key.replace("question", "").replace("q", "")
                                question_code = f"{batch_key}_q{q_num}" if q_num else f"{batch_key}_{q_key}"
                                
                                selected_questions[f"{batch_key}_{q_key}"] = {
                                    'question_key': q_key,
                                    'question_code': question_code,
                                    'batch_key': batch_key,
                                    'markdown_content': q_content if isinstance(q_content, str) else str(q_content),
                                    'num_duplicates': st.session_state.get(count_key, 1)
                                }
        
        if selected_questions:
            st.info(f"✅ {len(selected_questions)} question(s) selected for duplication")
            
            # Show which questions are selected
            with st.expander("View Selected Questions", expanded=False):
                for key, data in selected_questions.items():
                    st.write(f"• {data['batch_key']} - {data['question_key']} (x{data['num_duplicates']})")
            
            # Generate Duplicates Button
            if st.button("🚀 Generate Duplicates", type="primary", use_container_width=True):
                if not api_key:
                    st.error("❌ Please enter your Gemini API key in the sidebar")
                else:
                    with st.spinner("Generating duplicates... This may take a moment."):
                        import asyncio
                        from collections import defaultdict
                        from llm_engine import duplicate_questions_async
                        
                        # Group selected questions by batch_key (question type)
                        grouped_by_type = defaultdict(list)
                        for key, data in selected_questions.items():
                            grouped_by_type[data['batch_key']].append(data)
                        
                        # Show grouping info
                        status_text = st.empty()
                        total_questions = len(selected_questions)
                        status_text.info(f"Processing {total_questions} question(s) in full parallel...")
                        
                        async def generate_all_duplicates_parallel():
                            """Generate duplicates for ALL questions in parallel"""
                            
                            # Create a task for each individual question (not grouped by type)
                            async def process_single_question(key, data):
                                """Process a single question's duplication"""
                                result = await duplicate_questions_async(
                                    original_question_markdown=data['markdown_content'],
                                    question_code=data['question_code'],
                                    num_duplicates=data['num_duplicates'],
                                    api_key=api_key
                                )
                                return key, result
                            
                            # Create tasks for ALL questions at once
                            tasks = [
                                process_single_question(key, data)
                                for key, data in selected_questions.items()
                            ]
                            
                            # Run ALL questions in parallel
                            results_list = await asyncio.gather(*tasks)
                            
                            # Convert list of tuples to dictionary
                            results = {key: result for key, result in results_list}
                            
                            return results
                        
                        # Run async generation
                        try:
                            dup_results = asyncio.run(generate_all_duplicates_parallel())
                            
                            # Progress tracking
                            progress_bar = st.progress(0)
                            total = len(dup_results)
                            
                            # Store duplicates in session state
                            for idx, (key, result) in enumerate(dup_results.items(), 1):
                                progress_bar.progress(idx / total)
                                
                                if result.get('error'):
                                    st.error(f"❌ Error generating duplicates for {key}: {result['error']}")
                                else:
                                    duplicates = result.get('duplicates', [])
                                    data = selected_questions[key]
                                    
                                    # Store in the appropriate session state key
                                    duplicates_key = f"duplicates_{data['batch_key']}_{data['question_key']}"
                                    st.session_state[duplicates_key] = duplicates
                                    
                                    st.success(f"✅ Generated {len(duplicates)} duplicate(s) for {data['question_key']}")
                            
                            progress_bar.empty()
                            status_text.empty()
                            
                            # Show summary
                            st.success(f"🎉 Generated duplicates for {len(selected_questions)} question(s) in full parallel!")
                            with st.expander("📊 Generation Summary", expanded=True):
                                for key, data in selected_questions.items():
                                    num_dups = data['num_duplicates']
                                    st.write(f"• **{data['question_code']}:** {num_dups} duplicate(s) generated")
                            
                            st.info("Scroll up to view duplicates under each question.")
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"❌ Error during duplication: {str(e)}")
                            st.exception(e)
        else:
            st.info("ℹ️ Select questions using the checkboxes above to generate duplicates")
    else:
        st.info("👈 Configure and generate questions to see results here")


# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #6b7280; padding: 1rem;">
    <p>Built with ❤️ using Streamlit and Gemini AI</p>
</div>
""", unsafe_allow_html=True)
