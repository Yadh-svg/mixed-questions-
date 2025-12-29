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
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'question_types_config' not in st.session_state:
    st.session_state.question_types_config = {}
if 'generated_output' not in st.session_state:
    st.session_state.generated_output = None
if 'global_pdf' not in st.session_state:
    st.session_state.global_pdf = None

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
        help="Select the grade level"
    )
    
    chapter = st.text_input(
        "Chapter/Unit Name",
        placeholder="e.g., Arithmetic Progressions",
        help="Enter the chapter or unit name"
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        old_concept = st.text_area(
            "Old Concepts (Prerequisites)",
            placeholder="Enter prerequisite knowledge the student already has...",
            height=150,
            help="Concepts students should already know"
        )
    
    with col2:
        new_concept = st.text_area(
            "New Concepts (Current Chapter)",
            placeholder="Enter the concepts being taught in this chapter...",
            height=150,
            help="New concepts being taught"
        )
    
    additional_notes = st.text_area(
        "Additional Notes (Optional)",
        placeholder="Any special instructions for question generation...",
        height=100,
        help="Extra instructions or configuration"
    )
    
    st.markdown("---")
    st.markdown("### 📎 Global PDF Upload (Optional)")
    st.info("Upload a PDF here to use it across multiple questions. You can select this PDF when configuring individual questions.")
    
    global_pdf = st.file_uploader(
        "Upload Global PDF",
        type=['pdf'],
        key="global_pdf_uploader",
        help="This PDF can be reused for multiple questions"
    )
    
    if global_pdf:
        st.session_state.global_pdf = global_pdf
        st.success(f"✅ Global PDF uploaded: {global_pdf.name} ({global_pdf.size / 1024:.1f} KB)")
    else:
        st.session_state.global_pdf = None
    
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
                'content_source': 'new_concept',
                'pdf_file': None,
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
            num_questions = st.number_input(
                f"Number of {qtype} Questions",
                min_value=1,
                max_value=20,
                value=st.session_state.question_types_config[qtype].get('count', 1),
                key=f"count_{qtype}"
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
                            'content_source': 'new_concept',  # Default to new concept
                            'pdf_file': None
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
                    
                    # Content source selection
                    st.markdown("**Content Source:**")
                    content_source = st.radio(
                        "Select content source",
                        options=["new_concept", "global_pdf", "upload_pdf"],
                        format_func=lambda x: {
                            "new_concept": "📝 Use New Concept",
                            "global_pdf": "📎 Use Already Uploaded PDF",
                            "upload_pdf": "📤 Upload New PDF"
                        }[x],
                        key=f"mcq_source_{i}",
                        index=["new_concept", "global_pdf", "upload_pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('content_source', 'new_concept')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['content_source'] = content_source
                    
                    # Show PDF uploader only if "upload_pdf" is selected
                    if content_source == 'upload_pdf':
                        pdf = st.file_uploader(
                            "Upload PDF for this question",
                            type=['pdf'],
                            key=f"mcq_pdf_{i}"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['pdf_file'] = pdf
                    elif content_source == 'global_pdf' and not st.session_state.global_pdf:
                        st.warning("⚠️ No global PDF uploaded. Please upload one in the General Information section.")
                    
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
                    
                    st.markdown("**Content Source:**")
                    content_source = st.radio(
                        "Select content source",
                        options=["new_concept", "global_pdf", "upload_pdf"],
                        format_func=lambda x: {
                            "new_concept": "📝 Use New Concept",
                            "global_pdf": "📎 Use Already Uploaded PDF",
                            "upload_pdf": "📤 Upload New PDF"
                        }[x],
                        key=f"ar_source_{i}",
                        index=["new_concept", "global_pdf", "upload_pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('content_source', 'new_concept')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['content_source'] = content_source
                    
                    if content_source == 'upload_pdf':
                        pdf = st.file_uploader(
                            "Upload PDF for this question",
                            type=['pdf'],
                            key=f"ar_pdf_{i}"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['pdf_file'] = pdf
                    elif content_source == 'global_pdf' and not st.session_state.global_pdf:
                        st.warning("⚠️ No global PDF uploaded. Please upload one in the General Information section.")
                    
                    st.markdown("---")
            
            elif qtype in ["Fill in the Blanks", "Descriptive", "Descriptive w/ Subquestions"]:
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
                    
                    # Content source selection
                    st.markdown("**Content Source:**")
                    content_source = st.radio(
                        "Select content source",
                        options=["new_concept", "global_pdf", "upload_pdf"],
                        format_func=lambda x: {
                            "new_concept": "📝 Use New Concept",
                            "global_pdf": "📎 Use Already Uploaded PDF",
                            "upload_pdf": "📤 Upload New PDF"
                        }[x],
                        key=f"{qtype}_source_{i}",
                        index=["new_concept", "global_pdf", "upload_pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('content_source', 'new_concept')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['content_source'] = content_source
                    
                    if content_source == 'upload_pdf':
                        pdf = st.file_uploader(
                            "Upload PDF for this question",
                            type=['pdf'],
                            key=f"{qtype}_pdf_{i}"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['pdf_file'] = pdf
                    elif content_source == 'global_pdf' and not st.session_state.global_pdf:
                        st.warning("⚠️ No global PDF uploaded. Please upload one in the General Information section.")
                    
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
                    
                    st.markdown("**Content Source:**")
                    content_source = st.radio(
                        "Select content source",
                        options=["new_concept", "global_pdf", "upload_pdf"],
                        format_func=lambda x: {
                            "new_concept": "📝 Use New Concept",
                            "global_pdf": "📎 Use Already Uploaded PDF",
                            "upload_pdf": "📤 Upload New PDF"
                        }[x],
                        key=f"case_source_{i}",
                        index=["new_concept", "global_pdf", "upload_pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('content_source', 'new_concept')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['content_source'] = content_source
                    
                    if content_source == 'upload_pdf':
                        pdf = st.file_uploader(
                            "Upload PDF for this question",
                            type=['pdf'],
                            key=f"case_pdf_{i}"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['pdf_file'] = pdf
                    elif content_source == 'global_pdf' and not st.session_state.global_pdf:
                        st.warning("⚠️ No global PDF uploaded. Please upload one in the General Information section.")
                    
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
                
                # Number of sub-parts per question (shared across all questions)
                num_subparts = st.number_input(
                    "Number of Sub-Parts per Question",
                    min_value=2,
                    max_value=5,
                    value=st.session_state.question_types_config[qtype].get('num_subparts', 3),
                    key=f"multipart_subparts"
                )
                st.session_state.question_types_config[qtype]['num_subparts'] = num_subparts
                
                # Initialize subparts config
                if 'subparts_config' not in st.session_state.question_types_config[qtype]:
                    st.session_state.question_types_config[qtype]['subparts_config'] = []
                
                # Adjust subparts config length
                current_subparts = len(st.session_state.question_types_config[qtype]['subparts_config'])
                if num_subparts != current_subparts:
                    if num_subparts > current_subparts:
                        for i in range(current_subparts, num_subparts):
                            st.session_state.question_types_config[qtype]['subparts_config'].append({
                                'part': chr(97 + i),
                                'dok': 1,
                                'marks': 1.0,
                                'taxonomy': 'Remembering'
                            })
                    else:
                        st.session_state.question_types_config[qtype]['subparts_config'] = \
                            st.session_state.question_types_config[qtype]['subparts_config'][:num_subparts]
                
                st.markdown("**Subparts Configuration** (Shared across all Multi-Part questions)")
                for i in range(num_subparts):
                    cols = st.columns([1, 1, 1, 2])
                    
                    with cols[0]:
                        st.markdown(f"**Part ({chr(97 + i)})**")
                    
                    with cols[1]:
                        dok = st.selectbox(
                            "DOK",
                            [1, 2, 3],
                            key=f"multipart_subpart_dok_{i}",
                            index=st.session_state.question_types_config[qtype]['subparts_config'][i].get('dok', 1) - 1
                        )
                        st.session_state.question_types_config[qtype]['subparts_config'][i]['dok'] = dok
                    
                    with cols[2]:
                        marks = st.number_input(
                            "Marks",
                            min_value=0.5,
                            max_value=10.0,
                            step=0.5,
                            key=f"multipart_subpart_marks_{i}",
                            value=st.session_state.question_types_config[qtype]['subparts_config'][i].get('marks', 1.0)
                        )
                        st.session_state.question_types_config[qtype]['subparts_config'][i]['marks'] = marks
                    
                    with cols[3]:
                        taxonomy = st.selectbox(
                            "Taxonomy",
                            taxonomy_options,
                            key=f"multipart_subpart_taxonomy_{i}",
                            index=taxonomy_options.index(
                                st.session_state.question_types_config[qtype]['subparts_config'][i].get('taxonomy', 'Remembering')
                            )
                        )
                        st.session_state.question_types_config[qtype]['subparts_config'][i]['taxonomy'] = taxonomy
                
                st.markdown("---")
                
                # Per-question config (topic and content source)
                st.markdown("**Per-Question Configuration**")
                for i in range(num_questions):
                    st.markdown(f"**Question {i+1}**")
                    
                    # Add Topic field for Multi-Part questions
                    topic = st.text_input(
                        "Topic",
                        key=f"multipart_topic_{i}",
                        value=st.session_state.question_types_config[qtype]['questions'][i].get('topic', ''),
                        placeholder="e.g., nth term of AP"
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['topic'] = topic
                    
                    st.markdown("**Content Source:**")
                    content_source = st.radio(
                        "Select content source",
                        options=["new_concept", "global_pdf", "upload_pdf"],
                        format_func=lambda x: {
                            "new_concept": "📝 Use New Concept",
                            "global_pdf": "📎 Use Already Uploaded PDF",
                            "upload_pdf": "📤 Upload New PDF"
                        }[x],
                        key=f"multipart_source_{i}",
                        index=["new_concept", "global_pdf", "upload_pdf"].index(
                            st.session_state.question_types_config[qtype]['questions'][i].get('content_source', 'new_concept')
                        ),
                        horizontal=True
                    )
                    st.session_state.question_types_config[qtype]['questions'][i]['content_source'] = content_source
                    
                    if content_source == 'upload_pdf':
                        pdf = st.file_uploader(
                            "Upload PDF for this question",
                            type=['pdf'],
                            key=f"multipart_pdf_{i}"
                        )
                        st.session_state.question_types_config[qtype]['questions'][i]['pdf_file'] = pdf
                    elif content_source == 'global_pdf' and not st.session_state.global_pdf:
                        st.warning("⚠️ No global PDF uploaded. Please upload one in the General Information section.")
                    
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
                needs_global_pdf = False
                
                for qtype, config in st.session_state.question_types_config.items():
                    for i, q in enumerate(config.get('questions', []), 1):
                        if not q.get('topic', '').strip():
                            missing_topics.append(f"{qtype} Question {i}")
                        
                        # Check if any question needs global PDF but it's not uploaded
                        if q.get('content_source') == 'global_pdf':
                            needs_global_pdf = True
                
                if missing_topics:
                    st.error(f"❌ Please specify topics for: {', '.join(missing_topics)}")
                elif needs_global_pdf and not st.session_state.global_pdf:
                    st.error("❌ Some questions are configured to use the global PDF, but no global PDF has been uploaded. Please upload a global PDF in the General Information section.")
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
                                'global_pdf': st.session_state.global_pdf  # Pass global PDF
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
                            st.balloons()
                            
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
                            
                        except Exception as e:
                            st.error(f"❌ Error during generation: {str(e)}")
                            st.exception(e)


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
