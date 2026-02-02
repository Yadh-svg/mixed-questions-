# 📚 AI Question Generator

A sophisticated educational question generation system powered by Google's Gemini AI. Built with Streamlit for a modern, intuitive interface, the system generates high-quality questions across multiple types with intelligent batch processing and validation.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Question Types](#question-types)
- [Batch Processing](#batch-processing)
- [Validation Pipeline](#validation-pipeline)
- [File Structure](#file-structure)
- [Usage Guide](#usage-guide)
- [Technical Details](#technical-details)
- [Troubleshooting](#troubleshooting)

---

## Overview

This system generates educational questions for **Grades 1-12** following the **NCERT curriculum** for **Mathematics**. It supports multiple question types, each with configurable difficulty (DOK levels), marks, and taxonomy classification. Questions are generated using Google's Gemini 2.5 Flash model with intelligent batching and validation.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Multi-Question Types** | 7 question types: MCQ, FIB, Case Study, Multi-Part, Assertion-Reasoning, Descriptive, Descriptive w/ Subquestions |
| **Batch Processing** | Questions grouped into batches of **4** for optimal processing |
| **Parallel Execution** | Different question types processed simultaneously |
| **Parallel Validation** | Each question validated independently in parallel |
| **PDF/Image Support** | Upload PDFs or images as concept sources |
| **Priority Packing** | Smart algorithm groups same-topic questions together |
| **Real-time Progress** | Live feedback during generation |
| **Question Regeneration** | Selectively regenerate specific questions |
| **Copy & Export** | Copy individual questions or download all as Markdown |

---

## 🏗️ Architecture

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           STREAMLIT UI (streamlit_app.py)                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ Configure Tab   │  │ Generate Tab    │  │ Results Tab     │                  │
│  │ - Grade         │  │ - Generate All  │  │ - View Output   │                  │
│  │ - Chapter       │  │ - Progress Bar  │  │ - Copy/Download │                  │
│  │ - Questions     │  │ - Live Status   │  │ - Regenerate    │                  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        BATCH PROCESSOR (batch_processor.py)                      │
│                                                                                  │
│  1. Group by Type ─→ 2. Priority Packing ─→ 3. Create Batches (Size: 4)         │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐            │
│  │                    PARALLEL BATCH FLOWS                          │            │
│  │  ┌─────────────────────────────────────────────────────────┐    │            │
│  │  │ MCQ Batch 1 ─→ Generate ─→ Split ─→ Parallel Validate  │    │            │
│  │  └─────────────────────────────────────────────────────────┘    │            │
│  │  ┌─────────────────────────────────────────────────────────┐    │            │
│  │  │ MCQ Batch 2 ─→ Generate ─→ Split ─→ Parallel Validate  │    │            │
│  │  └─────────────────────────────────────────────────────────┘    │            │
│  │  ┌─────────────────────────────────────────────────────────┐    │            │
│  │  │ FIB Batch 1 ─→ Generate ─→ Split ─→ Parallel Validate  │    │            │
│  │  └─────────────────────────────────────────────────────────┘    │            │
│  └─────────────────────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
┌───────────────────────────────┐    ┌───────────────────────────────┐
│ PROMPT BUILDER                │    │ LLM ENGINE                    │
│ (prompt_builder.py)           │    │ (llm_engine.py)               │
│                               │    │                               │
│ • Load templates from YAML   │    │ • Gemini API integration      │
│ • Replace placeholders       │    │ • File upload handling        │
│ • Build topic sections       │    │ • Async/await support         │
│ • Handle PDF/image files     │    │ • Error handling & retry      │
└───────────────────────────────┘    └───────────────────────────────┘
                    │                                   │
                    └─────────────────┬─────────────────┘
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          YAML CONFIGURATION FILES                                │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────┐       │
│  │ prompts.yaml (10,000+ lines)   │  │ validation.yaml (530 lines)    │       │
│  │                                 │  │                                 │       │
│  │ • Question templates for each  │  │ • Validation rules             │       │
│  │   question type                │  │ • DOK level checking           │       │
│  │ • DOK level guidelines         │  │ • Structure preservation       │       │
│  │ • Scenario rules               │  │ • Distractor analysis          │       │
│  │ • Output format specs          │  │ • Realism validation           │       │
│  └─────────────────────────────────┘  └─────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Processing Pipeline

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        SINGLE BATCH PROCESSING FLOW                               │
│                                                                                   │
│  ┌────────────┐    ┌────────────┐    ┌────────────────────────────────────────┐  │
│  │ STAGE 1:   │    │ STAGE 2:   │    │ STAGE 3: PARALLEL VALIDATION          │  │
│  │ GENERATION │ →  │ SPLIT      │ →  │                                        │  │
│  │            │    │            │    │  ┌──────────────────────────────────┐  │  │
│  │ Call       │    │ Parse by   │    │  │  question1 ──→ Validate ──┐     │  │  │
│  │ Gemini     │    │ delimiter  │    │  │  question2 ──→ Validate ──┼──→  │  │  │
│  │ with       │    │ |||        │    │  │  question3 ──→ Validate ──┘     │  │  │
│  │ prompt     │    │            │    │  │  question4 ──→ Validate ──→ AGG │  │  │
│  └────────────┘    └────────────┘    │  └──────────────────────────────────┘  │  │
│                                       └────────────────────────────────────────┘  │
│                                                                                   │
│  Delimiter Used: |||QUESTION_START|||                                             │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Installation

### Prerequisites

- **Python**: 3.8 or higher
- **Gemini API Key**: [Get one here](https://aistudio.google.com/app/apikey)

### Steps

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd mixed-questions-
   ```

2. **Create virtual environment** (recommended):
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # Linux/Mac
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up API key**:
   
   Create a `.env` file:
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```
   
   Or enter directly in the app sidebar.

5. **Run the application**:
   ```bash
   streamlit run streamlit_app.py
   ```

6. **Access the app**: Open `http://localhost:8501` in your browser

---

## ⚙️ Configuration

### Required Dependencies (requirements.txt)

| Package | Version | Purpose |
|---------|---------|---------|
| `streamlit` | ≥1.28.0 | Web UI framework |
| `google-genai` | ≥0.2.0 | Gemini AI SDK |
| `python-dotenv` | ≥1.0.0 | Environment variables |
| `pyyaml` | ≥6.0 | YAML parsing |
| `st-img-pastebutton` | latest | Image paste support |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Your Google Gemini API key |

---

## 📝 Question Types

The system supports **7 question types**, each with specialized templates:

| Question Type | Template Key | Description |
|---------------|--------------|-------------|
| **MCQ** | `MCQ` | Multiple Choice Questions with 4 options, distractor analysis |
| **Fill in the Blanks** | `FIB` | Questions with blank spaces to fill |
| **Case Study** | `case_study_maths` | Scenario-based questions with multiple sub-parts |
| **Multi-Part** | `multi_part_maths` | Questions with multiple related sub-questions |
| **Assertion-Reasoning** | `assertion_reasoning` | A & R format with standard options |
| **Descriptive** | `descriptive` | Long-form answer questions |
| **Descriptive w/ Subquestions** | `descriptive_subq` | Descriptive with sub-parts |

### Question Configuration Options

Each question can be configured with:

| Parameter | Options | Description |
|-----------|---------|-------------|
| **DOK Level** | 1, 2, 3 | Depth of Knowledge (1=Recall, 2=Application, 3=Strategic Thinking) |
| **Marks** | 0.5 - 10 | Question weightage |
| **Taxonomy** | Remembering, Understanding, Applying, Analyzing, Evaluating, Creating | Bloom's Taxonomy level |
| **Topic** | Free text | Specific topic within the chapter |
| **New Concept Source** | Text / PDF | Where to get concept information |

---

## 📦 Batch Processing

### Batch Size Configuration

```python
DEFAULT_BATCH_SIZE = 4  # Questions per batch
```

Each batch contains **exactly 4 questions** (or fewer for the last batch).

### Priority Packing Algorithm

The system uses a **Priority Packing** algorithm to group questions optimally:

```
PRIORITY PACKING STRATEGY
─────────────────────────

1. GROUP BY TYPE
   └── All MCQs together, all FIBs together, etc.

2. GROUP BY TOPIC (within type)
   └── Questions about "nth term" stay together
   └── Questions about "sum of AP" stay together

3. EXTRACT FULL BATCHES
   └── If Topic A has 6 questions → Extract [4] + [2 remaining]
   └── Full batches of 4 ensure topic coherence

4. PACK REMAINDERS
   └── Leftover questions combined into mixed batches
   └── Still keeps same topics together when possible
```

### Batch Processing Flow

```
Example: 10 MCQs (6 on "nth term", 4 on "sum of AP")

Step 1: Group by Type
        └── MCQ: [10 questions]

Step 2: Group by Topic
        └── "nth term": [6 questions]
        └── "sum of AP": [4 questions]

Step 3: Extract Full Batches
        └── MCQ Batch 1: [4 "nth term" questions]
        └── MCQ Batch 2: [4 "sum of AP" questions]
        └── Remainder: [2 "nth term" questions]

Step 4: Pack Remainders
        └── MCQ Batch 3: [2 "nth term" questions]

Final: 3 batches processed in parallel
```

### Parallel Execution Model

```
┌─ MCQ Type ─────────────────────────────────────────────────────────────┐
│  Batch 1 → [Gen→Split→Val] ─┐                                          │
│  Batch 2 → [Gen→Split→Val] ─┼─→ ALL BATCHES RUN IN PARALLEL           │
│  Batch 3 → [Gen→Split→Val] ─┘                                          │
└────────────────────────────────────────────────────────────────────────┘
           ║
           ║ PARALLEL
           ║
┌─ FIB Type ─────────────────────────────────────────────────────────────┐
│  Batch 1 → [Gen→Split→Val] ─→  RUNS SIMULTANEOUSLY WITH MCQ           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## ✅ Validation Pipeline

### Validation Process

Each generated question undergoes validation to ensure quality:

1. **DOK Level Verification**: Ensures cognitive demand matches declared DOK
2. **Structure Preservation**: Maintains question format and metadata
3. **Distractor Analysis**: Verifies MCQ options have distinct error types
4. **Realism Check**: Validates scenario plausibility
5. **Duplicate Detection**: Identifies solving-pattern duplicates

### Validation Rules (from validation.yaml)

| Rule | Description |
|------|-------------|
| **Structure Lock** | Cannot change question type, parts count, marks |
| **Metadata Immutable** | DOK, Taxonomy, Topic cannot be modified |
| **DOK Handling** | Questions upgraded/downgraded via in-stem edits |
| **Distractor Diversity** | Each wrong option maps to unique error type |
| **Textbook Reuse** | Detects and rewrites NCERT-copied content |
| **Realism Validator** | Fixes unrealistic scenarios |

### Distractor Error Types

| Error Type | Description | Example |
|------------|-------------|---------|
| **Conceptual** | Wrong method or understanding | Using wrong formula |
| **Computational** | Correct method, wrong calculation | 3×4=11 instead of 12 |
| **Communicational** | Wrong units/notation | m² instead of m |
| **Comprehension** | Misread the question | Found area instead of perimeter |

---

## 📁 File Structure

```
mixed-questions-/
├── streamlit_app.py        # Main UI (1933 lines)
│                           # - Streamlit page configuration
│                           # - Input forms for questions
│                           # - Results display and export
│
├── batch_processor.py      # Batch processing logic (798 lines)
│                           # - group_questions_by_type_and_topic()
│                           # - process_batches_pipeline()
│                           # - process_single_batch_flow()
│                           # - split_generated_content()
│                           # - regenerate_specific_questions_pipeline()
│
├── prompt_builder.py       # Prompt construction (471 lines)
│                           # - build_topics_section()
│                           # - build_prompt_for_batch()
│                           # - get_files()
│
├── llm_engine.py           # Gemini API integration (308 lines)
│                           # - run_gemini_async()
│                           # - upload_files_to_gemini()
│                           # - duplicate_questions_async()
│
├── result_renderer.py      # Output rendering (576 lines)
│                           # - normalize_llm_output_to_questions()
│                           # - render_markdown_question()
│                           # - render_batch_results()
│
├── prompts.yaml            # Generation prompts (10,362 lines)
│                           # - Templates for all 7 question types
│                           # - DOK level guidelines
│                           # - Scenario and diagram rules
│
├── validation.yaml         # Validation prompts (530 lines)
│                           # - Validation rules and checks
│                           # - Output structure definitions
│
├── requirements.txt        # Python dependencies
├── .env                    # API key configuration (create this)
└── .gitignore              # Git ignore rules
```

---

## 📖 Usage Guide

### Step 1: Configure General Information

| Field | Description | Example |
|-------|-------------|---------|
| **Grade** | Student grade level (1-12) | Grade 10 |
| **Chapter** | Chapter or unit name | Arithmetic Progressions |
| **Old Concept** | Previously learned concepts | Sequences, Patterns |
| **New Concept** | Current chapter concepts | nth term formula, Sum of AP |

### Step 2: Configure Questions

1. Set **Total Number of Questions**
2. For each question, configure:
   - **Question Type**: MCQ, FIB, Case Study, etc.
   - **Topic**: Specific topic within chapter
   - **DOK Level**: 1, 2, or 3
   - **Marks**: 0.5 to 10
   - **Taxonomy**: Bloom's level

### Step 3: Generate

1. Switch to **Generate** tab
2. Click **"Generate All Questions"**
3. Watch progress as batches complete

### Step 4: Review Results

1. Switch to **Results** tab
2. Questions organized by batch: `MCQ - Batch 1`, `MCQ - Batch 2`, etc.
3. Each question shows:
   - Topic, Marks, DOK Level
   - Question content
   - Options (for MCQ)
   - Solution with steps
   - Key Idea
   - Distractor Analysis (for MCQ/AR)

### Step 5: Export

- **Copy Individual**: Click copy button on any question
- **Download All**: Export as Markdown file

---

## 🔬 Technical Details

### LLM Configuration

| Setting | Value |
|---------|-------|
| **Model** | Gemini 2.5 Flash |
| **Thinking Budget** | 5000 tokens |
| **File Upload** | Direct bytes transfer |

### Question Delimiter

Questions are separated using:
```
|||QUESTION_START|||
```

This delimiter is used by `split_generated_content()` to parse individual questions.

### Output Format

Validated questions are returned as JSON:
```json
{
  "question1": "<markdown content>",
  "question2": "<markdown content>",
  "question3": "<markdown content>",
  "question4": "<markdown content>"
}
```

### Async Processing

The system uses Python's `asyncio` for concurrent processing:

```python
# All batches run in parallel
all_results = await asyncio.gather(*all_batch_tasks)
```

---

## 🐛 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "Please enter your Gemini API key" | Add key to `.env` file or sidebar |
| "Error during generation" | Check API key validity and quota |
| Questions not generating | Ensure all required fields are filled |
| Slow generation | Normal for large batches; watch progress |
| Validation errors | Check if prompts.yaml is complete |

### Logs

Enable debug logging by checking terminal output where Streamlit runs.

### File Upload Issues

- **Supported formats**: PDF, PNG, JPG, JPEG, GIF, WEBP
- **Max size**: Depends on Gemini API limits
- **Paste images**: Use the paste button for clipboard images

---

## 📊 Performance Notes

| Metric | Typical Value |
|--------|---------------|
| **Batch Size** | 4 questions |
| **Generation Time** | 15-45 seconds per batch |
| **Validation Time** | 10-30 seconds per question |
| **Total (10 questions)** | 2-5 minutes |

---

## 🔄 Regeneration

To regenerate specific questions:

1. Select checkboxes next to questions to regenerate
2. Click **"Regenerate Selected"**
3. Only selected questions are re-generated
4. Original questions are replaced in-place

---

## 📝 Adding New Question Types

1. **Add template** to `prompts.yaml`:
   ```yaml
   new_question_type: |
     Your prompt template here...
   ```

2. **Update mapping** in `prompt_builder.py`:
   ```python
   QUESTION_TYPE_MAPPING = {
       ...
       "New Type": "new_question_type",
   }
   ```

3. **Add to UI** in `streamlit_app.py`:
   ```python
   question_types = [..., "New Type"]
   ```

---

## 📄 License

Educational question generation system.

---

## 🤝 Support

For issues, check:
1. Terminal logs where Streamlit runs
2. Gemini API console for quota/errors
3. Verify all YAML files are properly formatted

---

Built with ❤️ using **Streamlit** and **Google Gemini AI**
