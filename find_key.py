
filename = r"c:\Users\trial\projects\my git\mixed-questions-\prompts.yaml"
try:
    with open(filename, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if "mcq_questions" in line:
                print(f"Line {i}: {line.strip()}")
except Exception as e:
    print(f"Error: {e}")
