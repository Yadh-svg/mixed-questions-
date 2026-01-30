
import json
from typing import List, Dict, Any

def extract_json_objects(text: str) -> List[Dict[str, Any]]:
    """
    Robustly extract JSON objects from text using json.JSONDecoder.
    This handles braces inside strings correctly, unlike simple stack counting.
    """
    objects = []
    decoder = json.JSONDecoder()
    pos = 0
    length = len(text)
    
    while pos < length:
        # Find the next opening brace
        try:
            # Skip whitespace
            while pos < length and text[pos].isspace():
                pos += 1
            if pos >= length:
                break
                
            if text[pos] != '{':
                # Skip until next brace
                pos = text.find('{', pos)
                if pos == -1:
                    break
            
            # Attempt to decode from this position
            obj, end_pos = decoder.raw_decode(text, idx=pos)
            if isinstance(obj, dict):
                objects.append(obj)
            pos = end_pos
            
        except json.JSONDecodeError:
            # If decoding failed, advance past the current '{' and try again
            # efficiently advance to next '{'
            pos += 1
            
    return objects

# Test cases
test_1 = '{"q": "Simple"}' 
test_2 = '{"q": "With braces {inside} balanced"}' 
test_3 = '{"q": "With braces } unbalanced inside"}' 
test_4 = '{"q": "With LaTeX \\frac{1}{2}"}' 
test_5 = '''{
  "question1": "Mixed Problems... Then PO = 2 * OQ. Solution: Set {x}"
}''' 

results = {
    "test_1": extract_json_objects(test_1),
    "test_2": extract_json_objects(test_2),
    "test_3": extract_json_objects(test_3),
    "test_4": extract_json_objects(test_4),
    "test_5": extract_json_objects(test_5),
    "test_6_mixed": 'text before {"q": 1} text inside {"q": 2} text after'
}

for k, v in results.items():
    if k == "test_6_mixed":
        # special handling for list
        extracted = extract_json_objects(v)
        print(f"{k}: {len(extracted)} objects found: {extracted}")
    else:
        print(f"{k}: {len(v)} objects found. {v}")
