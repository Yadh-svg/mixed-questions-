"""
Test script to verify per-topic content source implementation
"""

from prompt_builder import build_topics_section

# Test case: Mixed content sources
test_questions = [
    {
        'type': 'MCQ',
        'topic': 'Algebra',
        'content_source': 'new_concept',
        'dok': 1,
        'marks': 1,
        'taxonomy': 'Remembering'
    },
    {
        'type': 'MCQ',
        'topic': 'Algebra',
        'content_source': 'new_concept',
        'dok': 2,
        'marks': 2,
        'taxonomy': 'Understanding'
    },
    {
        'type': 'MCQ',
        'topic': 'Geometry',
        'content_source': 'upload_pdf',
        'pdf_file': type('obj', (object,), {'name': 'geometry_chapter.pdf'})(),
        'dok': 2,
        'marks': 2,
        'taxonomy': 'Applying'
    },
    {
        'type': 'Fill in the Blanks',
        'topic': 'Trigonometry',
        'content_source': 'global_pdf',
        'dok': 1,
        'marks': 1,
        'taxonomy': 'Remembering'
    }
]

print("=" * 80)
print("Testing build_topics_section with mixed content sources")
print("=" * 80)

result = build_topics_section(test_questions)

print("\nGenerated TOPICS_SECTION:")
print(result)

print("\n" + "=" * 80)
print("Expected Output:")
print("=" * 80)
print("""
    - Topic: "Algebra" → Questions: 2, DOK: 1, Marks: 1, Taxonomy: Remembering | Content Source: Use New Concept
    - Topic: "Geometry" → Questions: 1, DOK: 2, Marks: 2, Taxonomy: Applying | Content Source: Refer to PDF (geometry_chapter.pdf)
    - Topic: "Trigonometry" → Questions: 1, DOK: 1, Marks: 1, Taxonomy: Remembering | Content Source: Refer to Global PDF
""")

print("\n" + "=" * 80)
print("Verification:")
print("=" * 80)

# Verify each expected string is present
checks = [
    ('Algebra with Use New Concept', 'Content Source: Use New Concept' in result),
    ('Geometry with PDF reference', 'Content Source: Refer to PDF (geometry_chapter.pdf)' in result),
    ('Trigonometry with Global PDF', 'Content Source: Refer to Global PDF' in result),
]

all_passed = True
for check_name, passed in checks:
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {check_name}")
    if not passed:
        all_passed = False

if all_passed:
    print("\n🎉 All checks passed! Per-topic content source is working correctly.")
else:
    print("\n⚠️ Some checks failed. Please review the implementation.")
