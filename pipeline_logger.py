"""
Pipeline Prompt Logger
Saves prompts sent to the model for each pipeline stage.
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directory for saved prompts
PROMPTS_DIR = Path(__file__).parent / "pipeline_prompts_sent"


def save_stage_prompt(
    stage_num: int,
    prompt_text: str,
    metadata: Dict[str, Any] = None
) -> Path:
    """
    Save a pipeline stage prompt to a file.
    
    Args:
        stage_num: Stage number (1-4)
        prompt_text: The full prompt text sent to the model
        metadata: Optional metadata (stage name, question count, config, etc.)
        
    Returns:
        Path to the saved file
    """
    # Create directory if it doesn't exist
    PROMPTS_DIR.mkdir(exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"stage{stage_num}_prompt_{timestamp}.txt"
    filepath = PROMPTS_DIR / filename
    
    # Prepare metadata header
    metadata = metadata or {}
    stage_names = {
        1: "Scenario Generation",
        2: "Question Generation",
        3: "Solution Generation",
        4: "Educational Analysis"
    }
    
    header = f"""{'=' * 80}
PIPELINE STAGE {stage_num}: {stage_names.get(stage_num, f'Stage {stage_num}')}
{'=' * 80}

Timestamp: {datetime.now().isoformat()}
"""
    
    # Add metadata fields
    if metadata:
        header += "\nMetadata:\n"
        for key, value in metadata.items():
            header += f"  {key}: {value}\n"
    
    header += f"\n{'=' * 80}\nPROMPT TEXT:\n{'=' * 80}\n\n"
    
    # Write to file
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(header)
            f.write(prompt_text)
        
        logger.info(f"Saved Stage {stage_num} prompt to: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Failed to save Stage {stage_num} prompt: {e}")
        raise


def get_latest_prompt(stage_num: int) -> str:
    """
    Retrieve the most recently saved prompt for a given stage.
    
    Args:
        stage_num: Stage number (1-4)
        
    Returns:
        Prompt text (without metadata header) or empty string if not found
    """
    if not PROMPTS_DIR.exists():
        return ""
    
    # Find all prompts for this stage
    pattern = f"stage{stage_num}_prompt_*.txt"
    matching_files = sorted(PROMPTS_DIR.glob(pattern), reverse=True)
    
    if not matching_files:
        return ""
    
    # Read the latest file
    try:
        with open(matching_files[0], 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extract prompt text (after the separator line)
        separator = "PROMPT TEXT:\n" + "=" * 80 + "\n\n"
        if separator in content:
            return content.split(separator, 1)[1]
        else:
            return content
            
    except Exception as e:
        logger.error(f"Failed to read Stage {stage_num} prompt: {e}")
        return ""


def list_saved_prompts(stage_num: int = None) -> list:
    """
    List all saved prompts, optionally filtered by stage.
    
    Args:
        stage_num: Optional stage number to filter by
        
    Returns:
        List of tuples: (filepath, timestamp, stage_num)
    """
    if not PROMPTS_DIR.exists():
        return []
    
    if stage_num:
        pattern = f"stage{stage_num}_prompt_*.txt"
    else:
        pattern = "stage*_prompt_*.txt"
    
    files = []
    for filepath in sorted(PROMPTS_DIR.glob(pattern), reverse=True):
        # Extract stage number and timestamp from filename
        parts = filepath.stem.split('_')
        stage = int(parts[0].replace('stage', ''))
        timestamp = parts[2]
        
        files.append((filepath, timestamp, stage))
    
    return files
