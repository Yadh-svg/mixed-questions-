# 📚 AI Question Generator - Streamlit App

A modern, user-friendly web application for generating educational questions using Google's Gemini AI.

## ✨ Features

- **Multi-Question Type Support**: MCQ, Fill in the Blanks, Case Study, Multi-Part, Assertion-Reasoning, Descriptive, and more
- **Flexible Content Sources**: Use text-based concepts or upload PDF documents
- **Parallel Batch Processing**: Generate multiple question types simultaneously for faster results
- **Customizable Parameters**: Configure DOK levels, marks, and taxonomy for each question
- **Modern UI**: Clean, intuitive interface with real-time feedback
- **Export Results**: Download generated questions in Markdown format

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Gemini API key ([Get one here](https://aistudio.google.com/app/apikey))

### Installation

1. **Install dependencies**:
   ```bash
   pip install -r requirements_streamlit.txt
   ```

2. **Set up your API key**:
   
   Create a `.env` file in the project directory:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```
   
   Or enter it directly in the app's sidebar.

3. **Run the application**:
   ```bash
   streamlit run streamlit_app.py
   ```

4. **Open your browser**:
   
   The app will automatically open at `http://localhost:8501`

## 📖 How to Use

### 1. Configure General Information

- Select **Curriculum**, **Grade**, and **Subject**
- Enter the **Chapter/Unit Name**
- Fill in **Old Concepts** (prerequisites) and **New Concepts** (current chapter content)
- Add any **Additional Notes** for special instructions

### 2. Configure Questions

- Set the **Total Number of Questions** you want to generate
- For each question, configure:
  - **Question Type** (MCQ, FIB, Case Study, etc.)
  - **Topic** (specific topic within the chapter)
  - **Content Source**:
    - Check "Use New Concept" to use the general New Concept field
    - OR upload a PDF for this specific question
  - **DOK Level** (1, 2, or 3)
  - **Marks** (0.5 to 10)
  - **Taxonomy** (Remembering, Understanding, Applying, etc.)

### 3. Generate Questions

- Switch to the **Generate** tab
- Click **"Generate All Questions"**
- Wait for the parallel processing to complete

### 4. View and Download Results

- Switch to the **Results** tab
- Review generated questions organized by type
- Download all questions as a Markdown file

## 🏗️ Architecture

### File Structure

```
mix_proj/
├── streamlit_app.py          # Main Streamlit UI
├── batch_processor.py         # Parallel batch processing logic
├── prompt_builder.py          # Prompt construction from templates
├── llm_engine.py             # Gemini API integration
├── prompts.yaml              # Question generation templates
├── requirements_streamlit.txt # Python dependencies
└── .env                      # API key configuration
```

### Processing Flow

1. **User Input** → Questions configured in UI
2. **Grouping** → Questions grouped by type
3. **Parallel Processing** → Each group processed simultaneously
4. **Prompt Building** → Templates filled with user data
5. **API Calls** → Gemini generates questions (with or without PDF)
6. **Results Display** → Formatted output shown in UI

## 🎨 UI Features

- **Responsive Design**: Works on desktop and tablet devices
- **Real-time Validation**: Instant feedback on configuration errors
- **Progress Tracking**: Visual indicators during generation
- **Batch Statistics**: See question counts and processing times
- **Expandable Sections**: Organized interface with collapsible panels

## 🔧 Technical Details

### Parallel Processing

The app uses Python's `asyncio` to process different question types in parallel:

```python
# Example: 5 MCQs and 3 FIBs are processed simultaneously
MCQ Batch (5 questions) ──┐
                          ├──> Parallel Execution
FIB Batch (3 questions) ──┘
```

### PDF Handling

PDFs are passed directly to Gemini without text extraction:

```python
# PDF bytes are sent as-is to the API
pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
```

### Template System

Questions are generated using templates from `prompts.yaml`:

- Each question type has a dedicated template
- Templates support both text-only and PDF modes
- Placeholders are replaced with user-provided values

## 🛠️ Customization

### Adding New Question Types

1. Add the template to `prompts.yaml`
2. Update `QUESTION_TYPE_MAPPING` in `prompt_builder.py`
3. Add the type to `question_types` list in `streamlit_app.py`

### Modifying UI Styling

Edit the CSS in the `st.markdown()` section of `streamlit_app.py`:

```python
st.markdown("""
<style>
    /* Your custom CSS here */
</style>
""", unsafe_allow_html=True)
```

## 📝 Example Usage

**Scenario**: Generate 3 questions - 2 MCQs and 1 Case Study

1. Set Total Questions = 3
2. Configure Question 1:
   - Type: MCQ
   - Topic: "nth term of AP"
   - Use New Concept: ✓
   - DOK: 2, Marks: 1, Taxonomy: Understanding
3. Configure Question 2:
   - Type: MCQ
   - Topic: "Sum of n terms"
   - Use New Concept: ✓
   - DOK: 3, Marks: 2, Taxonomy: Applying
4. Configure Question 3:
   - Type: Case Study
   - Topic: "Real-life applications"
   - Upload PDF: ✓ (upload chapter PDF)
   - DOK: 2, Marks: 4, Taxonomy: Analysing
5. Click "Generate All Questions"
6. View results in the Results tab

## 🐛 Troubleshooting

### "Please enter your Gemini API key"
- Make sure you've entered a valid API key in the sidebar or `.env` file

### "Error during generation"
- Check your internet connection
- Verify your API key is valid and has quota remaining
- Ensure PDF files are valid and not corrupted

### Questions not generating
- Verify all required fields are filled (Chapter, Topics)
- Check that at least one question has a topic specified

## 📄 License

This project is part of the educational question generation system.

## 🤝 Support

For issues or questions, please check the logs in the terminal where Streamlit is running.

---

Built with ❤️ using Streamlit and Google Gemini AI
