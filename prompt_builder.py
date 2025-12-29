"""
Prompt Builder for Question Generation
Constructs prompts from templates with proper placeholder replacement.
"""

import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load prompts.yaml
PROMPTS_FILE = Path(__file__).parent / "prompts.yaml"

with open(PROMPTS_FILE, 'r', encoding='utf-8') as f:
    PROMPTS = yaml.safe_load(f)

# Mapping from UI question types to prompt template keys
QUESTION_TYPE_MAPPING = {
    "MCQ": "mcq_questions",
    "Fill in the Blanks": "FIB",
    "Case Study": "case_study_maths",
    "Multi-Part": "multi_part_maths",
    "Assertion-Reasoning": "assertion_reasoning",
    "Descriptive": "descriptive",
    "Descriptive w/ Subquestions": "descriptive_subq"
}


def build_topics_section(questions: List[Dict[str, Any]]) -> str:
    """
    Build the {{TOPICS_SECTION}} string from a list of questions.
    
    Format:
    - Topic: "Topic Name" → Questions: X, DOK: Y, Marks: Z, Taxonomy: ..., Content Source: ...
    """
    # Group by topic
    topics_dict = {}
    
    for q in questions:
        topic = q.get('topic', 'Unnamed Topic')
        content_source = q.get('content_source', 'new_concept')
        pdf_file = q.get('pdf_file')
        
        if topic not in topics_dict:
            # Taxonomy is now a single string, not a list
            taxonomy = q.get('taxonomy', 'Remembering')
            # Handle legacy list format if it exists
            if isinstance(taxonomy, list):
                taxonomy = taxonomy[0] if taxonomy else 'Remembering'
            
            # Determine content source label
            if content_source == 'upload_pdf' and pdf_file:
                filename = getattr(pdf_file, 'name', 'uploaded_file.pdf')
                content_source_label = f'Refer to PDF ({filename})'
            elif content_source == 'global_pdf':
                content_source_label = 'Refer to Global PDF'
            else:
                content_source_label = 'Use New Concept'
            
            topics_dict[topic] = {
                'count': 0,
                'dok': q.get('dok', 1),
                'marks': q.get('marks', 1),
                'taxonomy': taxonomy,
                'content_source': content_source_label
            }
        topics_dict[topic]['count'] += 1
    
    # Build the section
    lines = []
    for topic_name, topic_data in topics_dict.items():
        taxonomy = topic_data['taxonomy']  # Already a string
        content_source = topic_data['content_source']
        line = f'    - Topic: "{topic_name}" → Questions: {topic_data["count"]}, DOK: {topic_data["dok"]}, Marks: {topic_data["marks"]}, Taxonomy: {taxonomy} | Content Source: {content_source}'
        lines.append(line)
    
    return "\n".join(lines)


def get_pdf_files(questions: List[Dict[str, Any]], general_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract PDF files from ALL questions in the batch.
    Each question can have one PDF, and we collect all of them.
    
    Returns:
        Dictionary with 'pdf_files' (list), 'source_type', and 'filenames'
    """
    pdf_files = []
    filenames = []
    source_types = set()
    
    # Collect PDFs from ALL questions in the batch
    for q in questions:
        content_source = q.get('content_source', 'new_concept')
        
        # Check for per-question PDF upload
        if content_source == 'upload_pdf':
            pdf_file = q.get('pdf_file')
            if pdf_file:
                pdf_files.append(pdf_file)
                filename = getattr(pdf_file, 'name', 'uploaded_file.pdf')
                filenames.append(filename)
                source_types.add('Per-Question PDF')
        
        # Check for global PDF usage
        elif content_source == 'global_pdf':
            global_pdf = general_config.get('global_pdf')
            if global_pdf and global_pdf not in pdf_files:  # Avoid duplicates
                pdf_files.append(global_pdf)
                filename = getattr(global_pdf, 'name', 'global_pdf.pdf')
                filenames.append(filename)
                source_types.add('Global PDF')
    
    # Determine overall source type
    if pdf_files:
        if len(source_types) > 1:
            source_type = 'Mixed PDFs'
        else:
            source_type = list(source_types)[0]
        logger.info(f"Collected {len(pdf_files)} PDF(s) from batch: {', '.join(filenames)}")
    else:
        source_type = 'New Concept'
        logger.info("Using New Concept text (no PDFs)")
    
    return {
        'pdf_files': pdf_files,
        'source_type': source_type,
        'filenames': filenames
    }


def build_prompt_for_batch(
    batch_key: str,
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    type_config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Build a complete prompt for a batch of questions.
    
    Args:
        batch_key: Question type identifier
        questions: List of question configurations (all same type)
        general_config: General configuration
        type_config: Type-specific configuration (e.g., subparts for Multi-Part)
    
    Returns:
        Dictionary with 'prompt' (str), 'pdf_files' (list), and 'pdf_metadata' (dict)
    """
    logger.info(f"Building prompt for batch: {batch_key}")
    
    # Determine if we're using PDF and get metadata
    pdf_info = get_pdf_files(questions, general_config)
    pdf_files = pdf_info['pdf_files']
    source_type = pdf_info['source_type']
    filenames = pdf_info['filenames']
    
    # Get the appropriate template key
    template_key = QUESTION_TYPE_MAPPING.get(batch_key, "mcq_questions")
    
    # Add _pdf suffix if using PDF
    if pdf_files:
        template_key += "_pdf"
    
    # Get the template
    if template_key not in PROMPTS:
        logger.warning(f"Template {template_key} not found, using mcq_questions")
        template_key = "mcq_questions"
    
    template = PROMPTS[template_key]
    
    # Comprehensive logging
    file_info = f" | Files: {', '.join(filenames)}" if filenames else ""
    logger.info(f"Building prompt | Template: {template_key} | Source: {source_type}{file_info} | Questions: {len(questions)}")
    
    # Build topics section
    topics_section = build_topics_section(questions)
    
    # Calculate total questions
    total_questions = len(questions)
    number_of_topics = len(set(q.get('topic', '') for q in questions if q.get('topic')))
    
    # Build reference instruction based on content source
    reference_instruction = ""
    if source_type == 'New Concept':
        reference_instruction = """
    
    ## CONTENT REFERENCE INSTRUCTION:
    **IMPORTANT**: Each topic in the TOPICS_SECTION below specifies its content source.
    - For topics marked "Use New Concept" → Refer to the New Concepts section provided in this prompt
    - Use the concepts, definitions, formulas, and examples from the New Concepts to create contextually relevant questions
    - Do not use external knowledge beyond what is provided in the New Concepts section
    
    **New Concepts to Reference:**
    {{New_Concept}}
    """
    elif source_type in ['Global PDF', 'Per-Question PDF', 'Mixed PDFs']:
        pdf_names = ', '.join(filenames) if filenames else "the uploaded PDF(s)"
        reference_instruction = """
    
    ## CONTENT REFERENCE INSTRUCTION:
    **IMPORTANT**: Each topic in the TOPICS_SECTION below specifies its content source. Follow it strictly for each topic.
    - For topics marked "Refer to PDF" → Extract concepts from the uploaded PDF document(s): {pdf_names}
    - For topics marked "Use New Concept" → Refer to the New Concepts section provided below
    
    **PDF Content Guidelines:**
    - Extract relevant concepts, examples, definitions, and problem-solving approaches from the PDF content
    - Base questions on the material covered in the PDF, ensuring alignment with the topics specified
    - Use the PDF as the primary source of information for creating contextually accurate questions
    
    **New Concepts (Additional Context):**
    {{{{New_Concept}}}}
    
    Note: The New Concepts section provides additional context about what is being taught in this chapter.
    For PDF-based topics, use it to understand learning objectives, but prioritize the PDF content for question generation.
    """.format(pdf_names=pdf_names)

    
    # Prepare replacements
    replacements = {
        '{{Grade}}': general_config.get('grade', 'Grade 10'),
        '{{Curriculum}}': general_config.get('curriculum', 'NCERT'),
        '{{Subject}}': general_config.get('subject', 'Mathematics'),
        '{{Chapter}}': general_config.get('chapter', 'Chapter'),
        '{{Old_Concept}}': general_config.get('old_concept', 'N/A'),
        '{{New_Concept}}': general_config.get('new_concept', 'N/A'),
        '{{Additional_Notes}}': general_config.get('additional_notes', 'None'),
        '{{TOPICS_SECTION}}': topics_section,
        '{{TOTAL_QUESTIONS}}': str(total_questions),
        '{{NUMBER_OF_TOPICS}}': str(number_of_topics)
    }
    
    # Special handling for multi-part questions
    if 'multi_part' in template_key.lower() and type_config:
        subparts_config = type_config.get('subparts_config', [])
        
        if subparts_config:
            num_subparts = len(subparts_config)
            replacements['{{Number_of_subparts}}'] = str(num_subparts)
            
            # Build subparts section dynamically
            subparts_lines = ["    Subpart Configuration:"]
            for subpart in subparts_config:
                part = subpart.get('part', 'a')
                dok = subpart.get('dok', 1)
                marks = subpart.get('marks', 1.0)
                taxonomy = subpart.get('taxonomy', 'Remembering')
                line = f"      {part} → DOK {dok}, Marks: {marks}, Taxonomy: {taxonomy}"
                subparts_lines.append(line)
            
            replacements['{{SUBPARTS_SECTION}}'] = "\n".join(subparts_lines)
        else:
            # Fallback to default if no config provided
            replacements['{{Number_of_subparts}}'] = '3'
            replacements['{{SUBPARTS_SECTION}}'] = """    Subpart Configuration:
      a → DOK 1, Marks: 1.0, Taxonomy: Remembering
      b → DOK 2, Marks: 1.0, Taxonomy: Understanding
      c → DOK 3, Marks: 1.0, Taxonomy: Applying"""
    
    # Special handling for case study questions
    if 'case_study' in template_key.lower():
        # For case study, we need to inject per-question subpart configuration
        # This will be handled differently - we'll add it to additional notes
        case_study_configs = []
        for idx, q in enumerate(questions, 1):
            if 'subparts' in q:
                subparts = q['subparts']
                subpart_strs = []
                for sp in subparts:
                    part = sp.get('part', 'a')
                    dok = sp.get('dok', 1)
                    marks = sp.get('marks', 1.0)
                    subpart_strs.append(f"({part}) DOK {dok}, Marks {marks}")
                
                config_str = f"Question {idx}: {len(subparts)} sub-parts - {', '.join(subpart_strs)}"
                case_study_configs.append(config_str)
        
        if case_study_configs:
            case_study_note = "\n\nCase Study Sub-parts Configuration:\n" + "\n".join(case_study_configs)
            replacements['{{Additional_Notes}}'] = replacements['{{Additional_Notes}}'] + case_study_note
    
    # Replace placeholders
    prompt = template
    
    # IMPORTANT: Replace {{New_Concept}} in reference_instruction FIRST
    # before injecting it into the prompt
    new_concept_text = general_config.get('new_concept', 'N/A')
    if reference_instruction:
        reference_instruction = reference_instruction.replace('{{New_Concept}}', new_concept_text)
    
    # Inject reference instruction at the beginning
    # Try multiple injection points to handle different template formats
    if reference_instruction:
        # Try injection point 1: After "## INPUT DETAILS:"
        if '## INPUT DETAILS:' in prompt:
            prompt = prompt.replace('## INPUT DETAILS:', reference_instruction + '\n\n    ## INPUT DETAILS:')
        # Try injection point 2: After "### Inputs (Provided by User)" (for assertion_reasoning)
        elif '### Inputs (Provided by User)' in prompt:
            prompt = prompt.replace('### Inputs (Provided by User)', reference_instruction + '\n\n  ### Inputs (Provided by User)')
        # Fallback: inject at the very beginning after the first line
        else:
            lines = prompt.split('\n', 1)
            if len(lines) > 1:
                prompt = lines[0] + '\n' + reference_instruction + '\n\n' + lines[1]
    
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    
    logger.info(f"Prompt built: {len(prompt)} characters, PDF: {len(pdf_files) > 0}")
    
    # Log topics for debugging
    topics_list = [q.get('topic', 'NO_TOPIC') for q in questions]
    logger.info(f"Topics in this batch: {topics_list}")
    
    return {
        'prompt': prompt,
        'pdf_files': pdf_files,
        'pdf_metadata': {
            'source_type': source_type,
            'filenames': filenames
        }
    }

