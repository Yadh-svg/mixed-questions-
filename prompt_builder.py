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

# Core Skill Extraction Instructions (appended to prompts when enabled)
CORE_SKILL_EXTRACTION = """

## CORE SKILL METADATA EXTRACTION (MANDATORY)

Finally, verify the global list of generated questions.
Ouput a JSON block containing the **CUMULATIVE** metadata (The "Existing Knowledge Base" provided above PLUS the metadata for the NEW questions you just generated).

Structure:
- Return a JSON object where each key maps to a SINGLE STRING containing comma-separated values.
- The order must follow the sequence of generation (Old questions first, then New questions).

```json
{
  "core_equation": "old_eq1, old_eq2, ..., new_eq1, new_eq2",
  "solution_pattern": "old_pat1, old_pat2, ..., new_pat1, new_pat2",
  "scenario_signature": "old_sig1, old_sig2, ..., new_sig1, new_sig2",
  "context_domain": "old_dom1, old_dom2, ..., new_dom1, new_dom2",
  "answer_form": "old_form1, old_form2, ..., new_form1, new_form2"
}
```

Rules:
1. **Concatenate**: Take the "Existing Knowledge Base" values and append your new values (comma-separated).
2. Format: lowercase snake_case only.
3. No numbers in values.
4. Values must be short (1–3 words).
5. Ensure the list grows with each batch.
"""


# Previous Batch Metadata Template (injected when previous batch metadata exists)
PREVIOUS_BATCH_METADATA_TEMPLATE = """

## PREVIOUS BATCH METADATA (CUMULATIVE CONTEXT)

The following represents the metadata for ALL questions generated so far in this sequence.
You must APPEND your new questions' metadata to this list.

Existing Knowledge Base:
{previous_metadata}

Generate NEW questions that are distinct from the above.
"""


def build_topics_section(questions: List[Dict[str, Any]], batch_key: str = "") -> str:
    """
    Build the {{TOPICS_SECTION}} string from a list of questions.
    
    Format:
    - Topic: "Topic Name" → Questions: 1, DOK: Y, Marks: Z, Taxonomy: ..., New Concept Source: ..., Additional Notes Source: ...
      Additional Notes for this question: [per-question notes if applicable]
    
    Each question is listed individually with its own metadata.
    """
    lines = []
    
    for q in questions:
        topic = q.get('topic', 'Unnamed Topic')
        new_concept_source = q.get('new_concept_source', 'text')
        new_concept_file = q.get('new_concept_pdf')  # Keep key name for backward compatibility
        additional_notes_source = q.get('additional_notes_source', 'none')
        additional_notes_file = q.get('additional_notes_pdf')  # Keep key name for backward compatibility
        additional_notes_text = q.get('additional_notes_text', '')
        
        # Taxonomy is now a single string, not a list
        taxonomy = q.get('taxonomy', 'Remembering')
        # Handle legacy list format if it exists
        if isinstance(taxonomy, list):
            taxonomy = taxonomy[0] if taxonomy else 'Remembering'
        
        # Determine new concept source label
        if new_concept_source == 'pdf' and new_concept_file:
            filename = getattr(new_concept_file, 'name', 'uploaded_file')
            new_concept_label = f'File ({filename})'
        else:
            new_concept_label = 'Text'
        
        # Determine additional notes source label
        additional_notes_sources = []
        if additional_notes_text:
            additional_notes_sources.append('Text')
        
        if additional_notes_file:
            filename = getattr(additional_notes_file, 'name', 'uploaded_file')
            additional_notes_sources.append(f'File ({filename})')
            
        if additional_notes_sources:
            additional_notes_label = ' & '.join(additional_notes_sources)
        else:
             additional_notes_label = 'None'
        
        # Check for subpart configuration (supports both 'subparts_config' and legacy 'subparts')
        subparts_config = q.get('subparts_config', [])
        if not subparts_config:
            subparts_config = q.get('subparts', [])
            
        # Handle FIB Type (applies to both single and multi-part)
        fib_type = q.get('fib_type', 'Auto')
        fib_type_str = f", FIB Type: {fib_type}" if fib_type != 'Auto' else ""

        # Handle Multi-Part Type
        multipart_type = q.get('multipart_type', 'Auto')
        multipart_type_str = f", Multi-Part Type: {multipart_type}" if multipart_type != 'Auto' else ""

        # Handle Descriptive Type
        descriptive_type = q.get('descriptive_type', 'Auto')
        descriptive_type_str = f", Descriptive Type: {descriptive_type}" if descriptive_type != 'Auto' else ""

        # Use subparts_config if present and non-empty
        if subparts_config and len(subparts_config) > 0:
            # Inline subpart configuration
            parts_details = []
            for sp in subparts_config:
                part_label = sp.get('part', '?')
                pdok = sp.get('dok', 1)
                pmarks = sp.get('marks', 1)
                # Helper to handle taxonomy regardless of where it defaults
                ptax = sp.get('taxonomy', 'Remembering') 
                parts_details.append(f"{part_label}: DOK {pdok}, Marks {pmarks}, Taxonomy {ptax}")
            
            subparts_str = f"Sub-parts: {len(subparts_config)} [{', '.join(parts_details)}]"
            
            # Format WITHOUT top-level DOK/Marks/Taxonomy as they are irrelevant
            line = f'    - Topic: "{topic}" → Questions: 1{fib_type_str}{multipart_type_str}{descriptive_type_str} | {subparts_str} | New Concept Source: {new_concept_label} | Additional Notes Source: {additional_notes_label}'
            
        else:
            # Standard single-part question format with top-level DOK/Marks/Taxonomy
            dok = q.get('dok', 1)
            marks = q.get('marks', 1)
            
            # Handle MCQ Type if present
            mcq_type = q.get('mcq_type', 'Auto')
            mcq_type_str = f", MCQ Type: {mcq_type}" if mcq_type != 'Auto' else ""
            
            # Handle Statement Based
            statement_based = q.get('statement_based', False)
            sb_str = ", Statement Based: YES" if statement_based else ", Statement Based: NO"
            
            if batch_key == "Assertion-Reasoning":
                # For Assertion-Reasoning, exclude DOK and Taxonomy, but KEEP Marks
                line = f'    - Topic: "{topic}" → Questions: 1, Marks: {marks} | New Concept Source: {new_concept_label} | Additional Notes Source: {additional_notes_label}'
            else:
                line = f'    - Topic: "{topic}" → Questions: 1{mcq_type_str}{sb_str}{fib_type_str}{descriptive_type_str}, DOK: {dok}, Marks: {marks}, Taxonomy: {taxonomy} | New Concept Source: {new_concept_label} | Additional Notes Source: {additional_notes_label}'
        
        
        # Add regeneration reason if present (shown before original content)
        regeneration_reason = q.get('regeneration_reason', '')
        if regeneration_reason:
            lines.append(f'      [USER FEEDBACK / REGENERATION REASON]:')
            lines.append(f'      "{regeneration_reason}"')
            lines.append('')
        
        # Add original text if present (Regeneration Context)
        original_text = q.get('original_text', '')
        if original_text:
            lines.append(f'      [ORIGINAL QUESTION CONTENT for Context]:')
            # Indent the original text for clarity
            indented_text = '\n'.join([f'      {l}' for l in original_text.split('\n')])
            lines.append(indented_text)
            lines.append(f'      [END ORIGINAL CONTENT]')
            lines.append('')
        # Add per-question additional notes if present
        if additional_notes_text:
            # For questions with subparts (compact mode), add notes inline
            if subparts_config:
                # Sanitize newlines to keep it on one line
                clean_notes = additional_notes_text.replace('\n', '  ')
                line += f" | Additional Notes: {clean_notes}"
                lines.append(line)
            else:
                lines.append(line)
                lines.append(f'      Additional Notes for this question: {additional_notes_text}')
        else:
            lines.append(line)
    
    return "\n".join(lines)


def get_files(questions: List[Dict[str, Any]], general_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract PDF and image files from questions in the batch.
    - Universal file is used for all questions with 'pdf' as new concept source
    - Per-question files are only for additional notes
    
    Returns:
        Dictionary with 'files' (list), 'source_type', and 'filenames'
    """
    files = []
    filenames = []
    source_types = set()
    
    # Check if we have a universal file and if any question uses file as new concept source
    universal_file = general_config.get('universal_pdf')  # Keep key name for backward compatibility
    has_file_new_concept = any(q.get('new_concept_source') == 'pdf' for q in questions)
    
    # Add universal file if it exists and at least one question uses file as new concept source
    if universal_file and has_file_new_concept:
        files.append(universal_file)
        filename = getattr(universal_file, 'name', 'universal_new_concept_file')
        filenames.append(filename)
        source_types.add('Universal New Concept File')
        logger.info(f"Using universal file: {filename}")
    
    # Collect additional notes files from questions
    for q in questions:
        # Check for additional notes file
        additional_notes_file = q.get('additional_notes_pdf')  # Keep key name for backward compatibility
        if additional_notes_file and additional_notes_file not in files:  # Avoid duplicates
            files.append(additional_notes_file)
            filename = getattr(additional_notes_file, 'name', 'uploaded_file')
            filenames.append(filename)
            source_types.add('Additional Notes File')
    
    # Determine overall source type
    if files:
        if len(source_types) > 1:
            source_type = 'Mixed Files'
        else:
            source_type = list(source_types)[0]
        logger.info(f"Collected {len(files)} file(s) from batch: {', '.join(filenames)}")
    else:
        source_type = 'Text Only'
        logger.info("Using text only (no files)")
    
    return {
        'files': files,
        'source_type': source_type,
        'filenames': filenames
    }


def build_prompt_for_batch(
    batch_key: str,
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    type_config: Dict[str, Any] = None,
    previous_batch_metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Build a complete prompt for a batch of questions.
    
    Args:
        batch_key: Question type identifier
        questions: List of question configurations (all same type)
        general_config: General configuration
        type_config: Type-specific configuration (e.g., subparts for Multi-Part)
        previous_batch_metadata: Metadata from previous batches for core skill extraction
    
    Returns:
        Dictionary with 'prompt' (str), 'files' (list), and 'file_metadata' (dict)
    """
    logger.info(f"Building prompt for batch: {batch_key}")
    
    # Determine if we're using files and get metadata
    file_info = get_files(questions, general_config)
    files = file_info['files']
    source_type = file_info['source_type']
    filenames = file_info['filenames']
    
    # Get the appropriate template key
    template_key = QUESTION_TYPE_MAPPING.get(batch_key, "mcq_questions")
    
    # Add _pdf suffix if using files (keeping _pdf suffix for backward compatibility with templates)
    if files:
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
    topics_section = build_topics_section(questions, batch_key)
    
    # Calculate total questions
    total_questions = len(questions)
    number_of_topics = len(set(q.get('topic', '') for q in questions if q.get('topic')))
    
    # Build reference instruction based on content sources
    reference_instruction = ""
    
    # Determine if we have files and what types
    has_new_concept_file = any(q.get('new_concept_source') == 'pdf' and q.get('new_concept_pdf') for q in questions)
    has_new_concept_file = any(q.get('new_concept_source') == 'pdf' and q.get('new_concept_pdf') for q in questions)
    has_additional_notes_file = any(q.get('additional_notes_pdf') for q in questions)
    has_new_concept_text = any(q.get('new_concept_source') == 'text' for q in questions)
    has_additional_notes_text = any(q.get('additional_notes_text') for q in questions)
    
    if files:
        # We have at least one file
        file_names = ', '.join(filenames) if filenames else "the uploaded file(s)"
        
        # Base instruction without Global Notes
        reference_instruction = f"""
    
    ## CONTENT REFERENCE INSTRUCTION:
    **IMPORTANT**: Each topic in the TOPICS_SECTION below specifies its content sources. Follow them strictly for each topic.
    
    **New Concept Sources:**
    - For topics marked with "New Concept Text" → Refer to the New Concepts section provided below
    - For topics marked with "New Concept File" → Extract concepts from the corresponding uploaded file: {file_names}
    
    **Additional Notes Sources:**
    - **Global Additional Notes** (apply to ALL questions)
    - **Per-Question Additional Notes** are shown directly in the TOPICS_SECTION for specific questions
    - For topics with "Additional Notes File" → Extract additional context from the corresponding uploaded file: {file_names}
    - For topics with "None" → No per-question additional notes for this topic (global notes still apply)
    
    **File Content Guidelines:**
    - Extract relevant concepts, examples, definitions, and problem-solving approaches from the file content
    - Base questions on the material covered in the file, ensuring alignment with the topics specified
    - Use the file as the primary source of information for creating contextually accurate questions
    - Pay attention to the filename mentioned in each topic to use the correct file
    
    **New Concepts (for text-based topics):**
    {{{{New_Concept}}}}
    """
    
        # Only inject Global Notes block if NOT in template to avoid duplication
        if '{{Additional_Notes}}' not in template:
             reference_instruction += """
    **Global Additional Notes (applies to ALL questions):**
    {{Additional_Notes}}
    """
        
        reference_instruction += """
    **Per-Question Additional Notes:**
    Some topics may have specific additional notes shown directly in the TOPICS_SECTION below.
    These per-question notes supplement the global notes for that specific question.
    
    Note: The New Concepts and Additional Notes sections provide context for topics using text sources.
    For file-based topics, prioritize the file content for question generation.
    """
    else:
        # Text only, no PDFs
        # Base instruction without Global Notes
        reference_instruction = """
    
    ## CONTENT REFERENCE INSTRUCTION:
    **IMPORTANT**: Each topic in the TOPICS_SECTION below specifies its content sources.
    - All topics use "New Concept Text" → Refer to the New Concepts section provided in this prompt
    - Topics may have per-question "Additional Notes Text" → These are shown directly in the TOPICS_SECTION
    - Topics with "None" for Additional Notes → Do not use per-question additional notes for those topics
    
    **New Concepts to Reference:**
    {{New_Concept}}
    """
    
        # Only inject Global Notes block if NOT in template
        if '{{Additional_Notes}}' not in template:
             reference_instruction += """
    **Global Additional Notes (applies to ALL questions):**
    {{Additional_Notes}}
    """
        
        reference_instruction += """
    **Per-Question Additional Notes:**
    Some topics may have specific additional notes shown directly in the TOPICS_SECTION below.
    These per-question notes take precedence over global notes for that specific question.
    
    Use the concepts, definitions, formulas, and examples from the New Concepts to create contextually relevant questions.
    Apply global Additional Notes to all questions, and per-question notes where specified.
    """

    
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
    if 'multi_part' in template_key.lower():
        # Check if we have per-question subpart configuration
        has_per_question_subparts = any('subparts_config' in q for q in questions)
        
        if has_per_question_subparts:
            # Per-question configuration takes precedence
            replacements['{{Number_of_subparts}}'] = 'Variable (see TOPICS section)'
            replacements['{{SUBPARTS_SECTION}}'] = '    Subpart Configuration: Refer to the specific sub-part configuration provided for each question in the TOPICS section above.'
        elif type_config:
            # Fallback to global configuration if provided
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
                # Fallback default
                replacements['{{Number_of_subparts}}'] = '3'
                replacements['{{SUBPARTS_SECTION}}'] = """    Subpart Configuration:
      a → DOK 1, Marks: 1.0, Taxonomy: Remembering
      b → DOK 2, Marks: 1.0, Taxonomy: Understanding
      c → DOK 3, Marks: 1.0, Taxonomy: Applying"""
        else:
             # Fallback default if neither per-question nor type_config exists
            replacements['{{Number_of_subparts}}'] = '3'
            replacements['{{SUBPARTS_SECTION}}'] = """    Subpart Configuration:
      a → DOK 1, Marks: 1.0, Taxonomy: Remembering
      b → DOK 2, Marks: 1.0, Taxonomy: Understanding
      c → DOK 3, Marks: 1.0, Taxonomy: Applying"""
    
    # Special handling for FIB questions with per-question subparts
    if 'fib' in template_key.lower():
        # Clean up the placeholder if it exists in the template, but don't inject anything
        # The subpart info is now in the TOPICS_SECTION
        replacements['{{FIB_SUBPART_SPECS}}'] = ""
    

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
    
    # IMPORTANT: Replace {{New_Concept}} and {{Additional_Notes}} in reference_instruction FIRST
    # before injecting it into the prompt
    new_concept_text = general_config.get('new_concept', 'N/A')
    additional_notes_text = general_config.get('additional_notes', 'None')
    
    if reference_instruction:
        reference_instruction = reference_instruction.replace('{{New_Concept}}', new_concept_text)
        reference_instruction = reference_instruction.replace('{{Additional_Notes}}', additional_notes_text)
    
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
    
    # Core Skill Extraction: Append instructions if enabled
    core_skill_enabled = general_config.get('core_skill_enabled', False)
    if core_skill_enabled:
        # Inject previous batch metadata if available
        if previous_batch_metadata:
            # Format metadata as cleanly as possible (comma separated lines)
            # Input: {"key": "val1, val2", "key2": "v1, v2"} or {"key": ["v1", "v2"]}
            # We standardize to comma separated string
            formatted_lines = []
            for k, v in previous_batch_metadata.items():
                val_str = ""
                if isinstance(v, list):
                    val_str = ", ".join(str(x) for x in v)
                else:
                    val_str = str(v)
                formatted_lines.append(f"{k}: {val_str}")
            
            metadata_str = "\n".join(formatted_lines)
            prompt += PREVIOUS_BATCH_METADATA_TEMPLATE.format(previous_metadata=metadata_str)
        
        # Append core skill extraction instructions
        prompt += CORE_SKILL_EXTRACTION
        logger.info(f"Core skill extraction enabled for batch: {batch_key}")
    
    logger.info(f"Prompt built: {len(prompt)} characters, Files: {len(files) > 0}")
    
    # Log topics for debugging
    topics_list = [q.get('topic', 'NO_TOPIC') for q in questions]
    logger.info(f"Topics in this batch: {topics_list}")
    
    return {
        'prompt': prompt,
        'files': files,
        'file_metadata': {
            'source_type': source_type,
            'filenames': filenames
        }
    }

