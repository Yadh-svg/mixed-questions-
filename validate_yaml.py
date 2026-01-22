import yaml
try:
    with open(r'c:\Users\trial\projects\my git\mixed-questions-\prompts.yaml', 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    print("YAML is valid.")
    print(f"Keys found: {len(data.keys())}")
except Exception as e:
    print(f"YAML Error: {e}")
