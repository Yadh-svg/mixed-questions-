"""Test script to verify regex-based key normalization"""
import re
from typing import Dict, Any

def normalize_question(q: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize keys and infer Q_TYPE to handle inconsistent JSON output.
    Uses regex patterns for flexible key matching.
    """
    normalized = {}
    
    # Regex-based key patterns (pattern -> standard key)
    # These patterns are case-insensitive and flexible with spaces/underscores
    key_patterns = [
        # Topic variations
        (r'^topic$', 'TOPIC'),
        (r'^topic[\s_]*used$', 'TOPIC'),
        
        # Question variations
        (r'^question$', 'QUESTION'),
        
        # Options variations
        (r'^options?$', 'OPTION'),
        
        # Answer variations
        (r'^(?:correct[\s_]*)?(?:answer|option)$', 'CORRECT_ANSWER'),
        (r'^answer[\s_]*key$', 'ANSWER_KEY'),
        
        # Solution variations - THIS IS THE KEY FIX
        (r'^solution(?:[\s_]*explanation)?$', 'SOLUTION'),
        
        # Distractor Analysis variations
        (r'^distractor[\s_]*analysis$', 'DISTRACTOR_ANALYSIS'),
        
        # Key Idea variations
        (r'^key[\s_-]*idea$', 'KEY_IDEA'),
        
        # Scenario variations
        (r'^scenario$', 'SCENARIO'),
        
        # Diagram variations
        (r'^diagram[\s_]*prompt$', 'DIAGRAM_PROMPT'),
        
        # DOK variations
        (r'^dok(?:[\s_]*level)?$', 'DOK'),
        
        # Taxonomy variations
        (r'^taxonomy$', 'TAXONOMY'),
        
        # Marks variations
        (r'^(?:marking[\s_]*scheme|marks?)$', 'MARKS'),
        
        # Subquestions variations
        (r'^(?:sub[\s_]*q(?:uestions)?|parts)$', 'SUBQ'),
        
        # Question type variations
        (r'^(?:q[\s_]*type|question[\s_]*type)$', 'Q_TYPE'),
        (r'^fib[\s_]*type$', 'FIB_TYPE'),
        (r'^multipart[\s_]*type$', 'MULTIPART_TYPE'),
    ]

    for k, v in q.items():
        # Normalize the key for pattern matching
        clean_k = str(k).lower().replace('_', ' ').strip()
        clean_k = re.sub(r'\s+', ' ', clean_k)  # Normalize multiple spaces
        
        # Try to match against patterns
        matched = False
        for pattern, standard_key in key_patterns:
            if re.match(pattern, clean_k, re.IGNORECASE):
                normalized[standard_key] = v
                matched = True
                break
        
        # If no pattern matched, keep the original key
        if not matched:
            normalized[k] = v
            
    return normalized


# Test with various key formats
test_keys = [
    "Solution Explanation",
    "solution explanation",
    "Solution",
    "solution",
    "SOLUTION_EXPLANATION",
    "Key Idea",
    "key idea",
    "KeyIdea",
    "key_idea",
    "KEY-IDEA",
    "Answer Key",
    "answer_key",
    "Topic Used",
    "topic used",
    "FIB Type",
    "fib_type",
    "Distractor Analysis",
    "distractor  analysis",  # multiple spaces
]

print("Testing key normalization:\n")
for key in test_keys:
    test_dict = {key: "test_value"}
    result = normalize_question(test_dict)
    normalized_key = list(result.keys())[0]
    print(f"{key:30} -> {normalized_key}")
