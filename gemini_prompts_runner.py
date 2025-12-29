import yaml
import os

# Helper to load prompts
def load_prompts(file_path='prompts.yaml'):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return {}
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# Helper to generate TOPICS_SECTION string
def generate_topics_section(topics_config):
    """
    topics_config: list of dicts, e.g.
    [
      {
        "topic": "Algebra",
        "number_of_questions": 5,
        "taxonomy": "Understanding",
        "dok": "DOK 2",
        "marks": 2
      },
      ...
    ]
    """
    section = "## TOPICS AND CONFIGURATION:\n"
    total_questions = 0
    for idx, t in enumerate(topics_config, 1):
        section += f"  Topic {idx}: {t['topic']}\n"
        section += f"    - Quantity: {t['number_of_questions']}\n"
        if 'dok' in t:
             section += f"    - DOK Level: {t['dok']}\n"
        if 'marks' in t:
             section += f"    - Marks: {t['marks']}\n"
        if 'taxonomy' in t:
             section += f"    - Taxonomy: {t['taxonomy']}\n"
        section += "\n"
        total_questions += t['number_of_questions']
    
    return section, total_questions

# Runner
def run_prompt_test(prompt_key, topics_config, output_file=None):
    prompts = load_prompts()
    if prompt_key not in prompts:
        print(f"Error: Key {prompt_key} not found in prompts.yaml")
        return

    template = prompts[prompt_key]
    
    topics_section, total_questions = generate_topics_section(topics_config)
    number_of_topics = len(topics_config)
    
    # Example input data
    input_data = {
        "Subject": "Mathematics",
        "Grade": "Grade 10",
        "Chapter": "Arithmetic Progressions",
        "Curriculum": "CBSE",
        "New_Concept": "nth term of an AP: an = a + (n-1)d. Sum of n terms of an AP: Sn = n/2(2a + (n-1)d).",
        "Old_Concept": "Patterns, sequences, basic algebra.",
        "Additional_Notes": "Focus on real-life applications.",
        "TOPICS_SECTION": topics_section,
        "TOTAL_QUESTIONS": total_questions,
        "NUMBER_OF_TOPICS": number_of_topics,
        
        # Default placeholder values if they exist in the prompt but not in topics
        # Note: In multi-topic mode, these might be ignored or used as defaults
        "Marks": "See Topic Config",
        "DOK_Level": "See Topic Config",
        "Taxonomy": "See Topic Config"
    }

    # Replace placeholders
    prompt = template
    for k, v in input_data.items():
        placeholder = "{{" + k + "}}"
        prompt = prompt.replace(placeholder, str(v))
    
    print(f"Successfully generated prompt for key: {prompt_key}")
    
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"Full prompt written to {output_file}")
    
    return prompt

if __name__ == "__main__":
    # Test Config
    test_topics = [
        {
            "topic": "Finding nth term", 
            "number_of_questions": 2,
            "dok": "DOK 1", 
            "marks": 1,
            "taxonomy": "Apply"
        },
        {
            "topic": "Sum of n terms", 
            "number_of_questions": 3,
            "dok": "DOK 2",
            "marks": 2,
            "taxonomy": "Analyze"
        }
    ]
    
    # Run for the modified keys
    print("Testing prompt generation...")
    keys_to_test = [
        "mcq_questions", 
        "FIB", 
        "multi_part_maths", 
        "descriptive_subq",
        "assertion_reasoning",
        "case_study_maths",
        "case_study_maths_pdf"
    ]
    
    for key in keys_to_test:
        run_prompt_test(key, test_topics, f"test_output_{key}.txt")
