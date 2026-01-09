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
                    cols = st.columns([2, 1, 1, 2])
                    
                    with cols[0]:
                        topic = st.text_input(
                            "Topic",
                            key=f"mcq_topic_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('topic', ''),
                            placeholder="e.g., nth term of AP"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['topic'] = topic
                    
                    with cols[1]:
                        dok = st.selectbox(
                            "DOK",
                            [1, 2, 3],
                            key=f"mcq_dok_{i}",
                            index=st.session_state.question_types_config[qtype]['questions'][i].get('dok', 1) - 1
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['dok'] = dok
                    
                    with cols[2]:
                        marks = st.number_input(
                            "Marks",
                            min_value=0.5,
                            max_value=10.0,
                            step=0.5,
                            key=f"mcq_marks_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('marks', 1.0)
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['marks'] = marks
                    
                    with cols[3]:
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
                    
                    # Additional Notes Source Selection (OPTIONAL)
                    st.markdown("**Additional Notes Source (Optional):**")
                    additional_notes_source = st.radio(
                        "Select additional notes source",
                        options=["none", "text", "pdf"],
                        format_func=lambda x: {
                            "none": "🚫 None",
                            "text": "📝 Additional Notes Text",
                            "pdf": "📄 Additional Notes File (PDF/Image)"
                        }[x],
                        key=f"mcq_additional_notes_source_{i}",
                        index=["none", "text", "pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_source', 'none')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = additional_notes_source
                    
                    # Show text area if text is selected
                    if additional_notes_source == 'text':
                        additional_notes_text = st.text_area(
                            "Additional Notes for this question",
                            key=f"mcq_additional_notes_text_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                            placeholder="Enter specific notes/instructions for this question...",
                            height=100
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                    # Show PDF uploader if PDF is selected
                    elif additional_notes_source == 'pdf':
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
                            
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = an_final
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                        if an_final:
                            st.success(f"✅ Ready: {an_final.name}")
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                    
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
                    
                    # Additional Notes Source Selection (OPTIONAL)
                    st.markdown("**Additional Notes Source (Optional):**")
                    additional_notes_source = st.radio(
                        "Select additional notes source",
                        options=["none", "text", "pdf"],
                        format_func=lambda x: {
                            "none": "🚫 None",
                            "text": "📝 Additional Notes Text",
                            "pdf": "📄 Additional Notes File (PDF/Image)"
                        }[x],
                        key=f"ar_additional_notes_source_{i}",
                        index=["none", "text", "pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_source', 'none')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = additional_notes_source
                    
                    if additional_notes_source == 'text':
                        additional_notes_text = st.text_area(
                            "Additional Notes for this question",
                            key=f"ar_additional_notes_text_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                            placeholder="Enter specific notes/instructions for this question...",
                            height=100
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                    elif additional_notes_source == 'pdf':
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
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                        if an_final:
                            st.success(f"✅ Ready: {an_final.name}")
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                    
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
                    
                    # Additional Notes Source Selection (OPTIONAL)
                    st.markdown("**Additional Notes Source (Optional):**")
                    additional_notes_source = st.radio(
                        "Select additional notes source",
                        options=["none", "text", "pdf"],
                        format_func=lambda x: {
                            "none": "🚫 None",
                            "text": "📝 Additional Notes Text",
                            "pdf": "📄 Additional Notes File (PDF/Image)"
                        }[x],
                        key=f"fib_additional_notes_source_{i}",
                        index=["none", "text", "pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_source', 'none')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = additional_notes_source
                    
                    if additional_notes_source == 'text':
                        additional_notes_text = st.text_area(
                            "Additional Notes for this question",
                            key=f"fib_additional_notes_text_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                            placeholder="Enter specific notes/instructions for this question...",
                            height=100
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                    elif additional_notes_source == 'pdf':
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
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                        if an_final:
                            st.success(f"✅ Ready: {an_final.name}")
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                    
                    st.markdown("---")
            
            elif qtype in ["Descriptive", "Descriptive w/ Subquestions"]:
                st.markdown(f"#### {qtype} Configuration")
                for i in range(num_questions):
                    st.markdown(f"**Question {i+1}**")
                    cols = st.columns([2, 1, 1, 2])
                    
                    with cols[0]:
                        topic = st.text_input(
                            "Topic",
                            key=f"{qtype}_topic_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('topic', ''),
                            placeholder="e.g., nth term of AP"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['topic'] = topic
                    
                    with cols[1]:
                        dok = st.selectbox(
                            "DOK",
                            [1, 2, 3],
                            key=f"{qtype}_dok_{i}",
                            index=st.session_state.question_types_config[qtype]['questions'][i].get('dok', 1) - 1
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['dok'] = dok
                    
                    with cols[2]:
                        marks = st.number_input(
                            "Marks",
                            min_value=0.5,
                            max_value=10.0,
                            step=0.5,
                            key=f"{qtype}_marks_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('marks', 1.0)
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['marks'] = marks
                    
                    with cols[3]:
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
                    
                    # Additional Notes Source Selection (OPTIONAL)
                    st.markdown("**Additional Notes Source (Optional):**")
                    additional_notes_source = st.radio(
                        "Select additional notes source",
                        options=["none", "text", "pdf"],
                        format_func=lambda x: {
                            "none": "🚫 None",
                            "text": "📝 Additional Notes Text",
                            "pdf": "📄 Additional Notes File (PDF/Image)"
                        }[x],
                        key=f"{qtype}_additional_notes_source_{i}",
                        index=["none", "text", "pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_source', 'none')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = additional_notes_source
                    
                    if additional_notes_source == 'text':
                        additional_notes_text = st.text_area(
                            "Additional Notes for this question",
                            key=f"{qtype}_additional_notes_text_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                            placeholder="Enter specific notes/instructions for this question...",
                            height=100
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                    elif additional_notes_source == 'pdf':
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
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                        if an_final:
                            st.success(f"✅ Ready: {an_final.name}")
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                    
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
                    
                    # Additional Notes Source Selection (OPTIONAL)
                    st.markdown("**Additional Notes Source (Optional):**")
                    additional_notes_source = st.radio(
                        "Select additional notes source",
                        options=["none", "text", "pdf"],
                        format_func=lambda x: {
                            "none": "🚫 None",
                            "text": "📝 Additional Notes Text",
                            "pdf": "📄 Additional Notes File (PDF/Image)"
                        }[x],
                        key=f"case_additional_notes_source_{i}",
                        index=["none", "text", "pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_source', 'none')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = additional_notes_source
                    
                    if additional_notes_source == 'text':
                        additional_notes_text = st.text_area(
                            "Additional Notes for this question",
                            key=f"case_additional_notes_text_{i}",
                            value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                            placeholder="Enter specific notes/instructions for this question...",
                            height=100
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                    elif additional_notes_source == 'pdf':
                        additional_notes_pdf = st.file_uploader(
                            "Upload Additional Notes File (PDF/Image)",
                            type=['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'],
                            key=f"case_additional_notes_pdf_{i}"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = additional_notes_pdf
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                        if additional_notes_pdf:
                            st.success(f"✅ Uploaded: {additional_notes_pdf.name}")
                    else:
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                    
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
                        
                        # Additional Notes Source Selection
                        st.markdown("**Additional Notes Source (Optional):**")
                        additional_notes_source = st.radio(
                            "Select additional notes source",
                            options=["none", "text", "pdf"],
                            format_func=lambda x: {
                                "none": "🚫 None",
                                "text": "📝 Additional Notes Text",
                                "pdf": "📄 Additional Notes File (PDF/Image)"
                            }[x],
                            key=f"multipart_additional_notes_source_{i}",
                            index=["none", "text", "pdf"].index(
                                st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_source', 'none')
                            ),
                            horizontal=True
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_source'] = additional_notes_source
                        
                        if additional_notes_source == 'text':
                            additional_notes_text = st.text_area(
                                "Additional Notes for this question",
                                key=f"multipart_additional_notes_text_{i}",
                                value=st.session_state.question_types_config[qtype]['questions'][i].get('additional_notes_text', ''),
                                placeholder="Enter specific notes/instructions for this question...",
                                height=100
                            )
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = additional_notes_text
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                        elif additional_notes_source == 'pdf':
                            additional_notes_pdf = st.file_uploader(
                                "Upload Additional Notes File (PDF/Image)",
                                type=['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'],
                                key=f"multipart_additional_notes_pdf_{i}"
                            )
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = additional_notes_pdf
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                            if additional_notes_pdf:
                                st.success(f"✅ Uploaded: {additional_notes_pdf.name}")
                        else:
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_pdf'] = None
                            st.session_state.question_types_config[qtype]['questions'][i]['additional_notes_text'] = ''
                        
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
                    with st.spinner("🔄 Generating questions... This may take a moment."):
                        try:
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
                            results = {}
                            
                            for qtype, type_config in st.session_state.question_types_config.items():
                                questions = type_config.get('questions', [])
                                
                                if questions:
                                    # Import here to avoid circular imports
                                    from batch_processor import process_single_batch
                                    
                                    # Run async function
                                    result = asyncio.run(
                                        process_single_batch(
                                            batch_key=qtype,
                                            questions=questions,
                                            general_config=config,
                                            type_config=type_config  # Pass type-specific config
                                        )
                                    )
                                    
                                    results[qtype] = result
                            
                            st.session_state.generated_output = results
                            st.success("✅ Questions generated successfully!")
                            
                        except Exception as e:
                            st.error(f"❌ Error during generation: {str(e)}")
                            st.exception(e)

        if st.session_state.generated_output:
            results = st.session_state.generated_output
            
            # Show results immediately below
            st.markdown("---")
            st.markdown('<div class="section-header">Generated Questions</div>', unsafe_allow_html=True)
            
            # Display results for each batch
            for batch_key, batch_result in results.items():
                with st.expander(f"📋 {batch_key}", expanded=True):
                    if batch_result.get('error'):
                        st.error(f"❌ Error: {batch_result['error']}")
                    else:
                        st.markdown(batch_result.get('text', 'No output'))
                        
                        # Show metadata
                        st.markdown("---")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("Questions", batch_result.get('question_count', 'N/A'))
                        with col2:
                            st.metric("Time Taken", f"{batch_result.get('elapsed', 0):.2f}s")
            
            # Download option
            st.markdown("---")
            
            # Combine all results
            combined_output = ""
            for batch_key, batch_result in results.items():
                combined_output += f"\n\n{'='*80}\n"
                combined_output += f"BATCH: {batch_key}\n"
                combined_output += f"{'='*80}\n\n"
                combined_output += batch_result.get('text', 'No output')
            
            st.download_button(
                label="📥 Download All Questions",
                data=combined_output,
                file_name="generated_questions.md",
                mime="text/markdown",
                use_container_width=True,
                key="download_saved_results"
            )


with tab2:
    st.markdown('<div class="section-header">Previously Generated Questions</div>', unsafe_allow_html=True)
    
    if st.session_state.generated_output:
        results = st.session_state.generated_output
        
        
        # Display results for each batch
        for batch_key, batch_result in results.items():
            with st.expander(f"📋 {batch_key}", expanded=True):
                if batch_result.get('error'):
                    st.error(f"❌ Error: {batch_result['error']}")
                else:
                    st.markdown(batch_result.get('text', 'No output'))
                    
                    # Show metadata
                    st.markdown("---")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Questions", batch_result.get('question_count', 'N/A'))
                    with col2:
                        st.metric("Time Taken", f"{batch_result.get('elapsed', 0):.2f}s")
        
        # Download option
        st.markdown("---")
        
        # Combine all results
        combined_output = ""
        for batch_key, batch_result in results.items():
            combined_output += f"\n\n{'='*80}\n"
            combined_output += f"BATCH: {batch_key}\n"
            combined_output += f"{'='*80}\n\n"
            combined_output += batch_result.get('text', 'No output')
        
        st.download_button(
            label="📥 Download All Questions",
            data=combined_output,
            file_name="generated_questions.md",
            mime="text/markdown",
            use_container_width=True,
            key="download_inline_results"
        )
    else:
        st.info("👈 Configure and generate questions to see results here")


# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #6b7280; padding: 1rem;">
    <p>Built with ❤️ using Streamlit and Gemini AI</p>
</div>
""", unsafe_allow_html=True)
