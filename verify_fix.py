import logging
from batch_processor import extract_core_skill_metadata
from pathlib import Path

# Configure logging to show info
logging.basicConfig(level=logging.INFO)

def verify():
    log_path = Path(r"c:\Users\trial\projects\my git\mixed-questions-\response_logs\20260204_171944_generation_MCQ_-_Batch_2.txt")
    
    if not log_path.exists():
        print(f"Error: Log file not found at {log_path}")
        return

    with open(log_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    print(f"Reading content from {log_path.name}...")
    
    # Run the extraction
    metadata = extract_core_skill_metadata(content, expected_count=4)
    
    print("\n--- Extraction Result ---")
    print(metadata)
    
    if metadata and 'batch_summary' in metadata:
        print("\nSUCCESS: Metadata extracted!")
        print(f"Batch Summary: {metadata['batch_summary'][:100]}...")
    else:
        print("\nFAILURE: Could not extract metadata.")

if __name__ == "__main__":
    verify()
