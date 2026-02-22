
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from pipeline_builder import build_math_core_prompt, build_writer_prompt
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_core_skill_injection():
    questions = [{'topic': 'Algebra', 'type': 'MCQ'}]
    general_config = {
        'grade': '10',
        'subject': 'Math',
        'new_concept': 'Quadratic Equations',
        'old_concept': 'Linear Equations'
    }
    
    # 1. Test Math Core Prompt Injection
    metadata = {'topics': ['Polynomials', 'Trigonometry']}
    
    logger.info("Testing Math Core Prompt Injection...")
    result_core = build_math_core_prompt(questions, general_config, previous_batch_metadata=metadata)
    prompt_core = result_core['prompt']
    
    if "<already_seen_topics>" in prompt_core:
        logger.info("✅ <already_seen_topics> tag found in Math Core prompt")
    else:
        logger.error("❌ <already_seen_topics> tag NOT found in Math Core prompt")
        
    if "Polynomials" in prompt_core and "Trigonometry" in prompt_core:
        logger.info("✅ Topics found in Math Core prompt")
    else:
        logger.error("❌ Topics NOT found in Math Core prompt")

    # 2. Test Writer Prompt Injection
    metadata_writer = {'scenarios': ['Market Scene', 'Space Force']}
    math_core_data = {'math_cores': []}
    
    logger.info("\nTesting Writer Prompt Injection...")
    result_writer = build_writer_prompt(math_core_data, questions, general_config, previous_batch_metadata=metadata_writer)
    prompt_writer = result_writer['prompt']
    
    if "<already_seen_scenarios>" in prompt_writer:
        logger.info("✅ <already_seen_scenarios> tag found in Writer prompt")
    else:
        logger.error("❌ <already_seen_scenarios> tag NOT found in Writer prompt")
        
    if "Market Scene" in prompt_writer and "Space Force" in prompt_writer:
        logger.info("✅ Scenarios found in Writer prompt")
    else:
        logger.error("❌ Scenarios NOT found in Writer prompt")

if __name__ == "__main__":
    test_core_skill_injection()
