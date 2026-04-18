# Radiology Helper (Non-diagnostic)

Radiology Helper is a Streamlit web app for **non-diagnostic imaging support**.
It combines:

- Local heuristic checks (symptom keyword triage + image quality metrics + simple visual heuristics)
- Optional vision LLM analysis (GitHub Models or OpenRouter)

The output is intended for education and triage support only. It is **not** a medical diagnosis and cannot replace clinician/radiologist interpretation.

## 1) What this project does

The app allows a user to:

- Upload a radiology image (`.png`, `.jpg`, `.jpeg`)
- Provide context (modality, body part, symptoms)
- Get a structured, non-diagnostic result including:
  - Summary
  - Possible issue categories with confidence/severity
  - Urgency level (`LOW`, `MODERATE`, `HIGH`, `EMERGENCY`)
  - Recommended next steps
  - Image observations
  - Safety limitations and red flags

## 2) Core safety boundaries

- The app explicitly presents a non-diagnostic disclaimer.
- It never claims a confirmed diagnosis in prompts or UI wording.
- It includes emergency red-flag reminders.
- It can still run without LLM access using local-only analysis.

## 3) Tech stack

- Python 3.9+ (recommended)
- Streamlit (web UI)
- NumPy (image statistics)
- Pillow (image loading/conversion)
- Requests (LLM API calls)

Main code file:

- `app.py`

## 4) High-level architecture

The app has five main layers:

1. UI and theme layer
- Streamlit page setup and custom CSS theme
- Sidebar model/provider controls
- Image upload, analysis trigger, and tabbed result display

2. Local image quality analysis
- Brightness, contrast, edge detail, dark/bright clipping ratios, resolution checks
- Returns flags, suggestions, and a `usable_for_screening` boolean

3. Local symptom triage analysis
- Keyword-based matching for broad issue categories
- Assigns per-issue confidence and severity
- Produces urgency candidate and red-flag list

4. Optional vision LLM analysis
- Supports:
  - GitHub Models endpoint (`https://models.inference.ai.azure.com/chat/completions`)
  - OpenRouter endpoint (`https://openrouter.ai/api/v1/chat/completions`)
- Sends image as base64 data URL plus a strict JSON instruction prompt
- Parses model response to strict expected schema

5. Fusion and recommendation layer
- Merges local and LLM issue signals
- Chooses final urgency from strongest signals with safety guardrails
- Builds combined recommendations and limitations for the final report

## 5) Detailed analysis flow

When the user clicks **Analyze Case**:

1. Image quality checks run locally (`analyze_image_quality`)
- Converts image to grayscale and calculates:
  - Size
  - Mean brightness
  - Contrast (std dev)
  - Edge strength (pixel-difference heuristic)
  - Ratios of near-black and near-white pixels
- Produces warnings and improvement suggestions.

2. Symptom triage runs locally (`analyze_symptoms`)
- Normalizes user symptom text.
- Matches keywords against predefined rule groups (respiratory, trauma, neurologic emergency, etc.).
- Outputs issue candidates and urgency estimate.

3. Local visual heuristic observations run (`local_visual_observations`)
- Compares center vs periphery brightness.
- Measures grayscale dynamic range.
- Emits non-diagnostic visual notes.

4. Optional LLM analysis runs (if enabled + key present)
- Builds system/user prompt (`build_vision_prompts`) with strict JSON schema.
- Calls selected provider:
  - `call_github_models_vision`
  - `call_openrouter_vision`
- Parses and normalizes JSON (`parse_llm_json_response`).

5. Results are merged (`analyze_case`)
- Final urgency is selected conservatively.
- Issue list from local + LLM is deduplicated and normalized (`merge_issues`).
- Recommendations are created (`build_recommendations`).
- UI tabs render issues, quality, actions, and safety content.

## 6) Urgency levels

The app uses four urgency levels:

- `LOW`: monitor and routine follow-up
- `MODERATE`: prompt but non-emergency review
- `HIGH`: urgent same-day clinical evaluation
- `EMERGENCY`: seek emergency care immediately

Urgency can be influenced by:

- Symptom pattern severity
- LLM-reported urgency (if available)
- Very poor image quality safety fallback (can raise low urgency to moderate)

## 7) Local setup

### Prerequisites

- Python 3.9 or newer
- Optional internet/API access for LLM calls

### Install dependencies

Run from project folder:

```powershell
pip install streamlit numpy requests pillow
```

### Run the app

```powershell
streamlit run app.py
```

Then open the local URL printed by Streamlit (usually `http://localhost:8501`).

## 8) Optional API configuration

You can run with no key (local-only mode), or set one of these env vars:

- GitHub Models: `GITHUB_TOKEN`
- OpenRouter: `OPENROUTER_API_KEY`

### Windows PowerShell examples

```powershell
$env:GITHUB_TOKEN = "<your_token_here>"
# or
$env:OPENROUTER_API_KEY = "<your_key_here>"
```

Model defaults in the app:

- GitHub Models: `openai/gpt-4.1-mini`
- OpenRouter: `meta-llama/llama-3.2-11b-vision-instruct:free`

You can edit these in the sidebar at runtime.

## 9) How to use

1. Launch the app.
2. In the sidebar:
- Toggle vision LLM usage.
- Select provider.
- Enter API key if needed.
- Optionally change model name.
3. Enter case details:
- Modality (`X-ray` or `MRI`)
- Body part
- Symptoms/context
4. Upload an image.
5. Click **Analyze Case**.
6. Review output tabs:
- Issue Signals
- Quality
- Actions
- Safety

## 10) Output interpretation guidance

Treat the result as a structured triage aid, not a diagnosis.

Most important sections for safe use:

- **Urgency** and **Red Flags** for escalation decisions
- **Quality warnings** to judge reliability of image-based output
- **Limitations** for uncertainty and context gaps

## 11) Error handling and fallback behavior

- If no API key is provided, the app automatically uses local-only analysis.
- If LLM call fails, the app catches errors and continues with local analysis.
- If model returns malformed text, JSON extraction/parsing attempts recovery.

## 12) Project structure

Current structure:

```text
.
├── app.py
└── README.md
```

## 13) Known limitations

- Not connected to DICOM/PACS workflows.
- Uses simple heuristic rules; not clinically validated.
- LLM outputs can be variable and should be treated cautiously.
- Single-file architecture is easy to run but less modular for large-scale extension.

## 14) Privacy and security notes

- Uploaded images are processed in-memory during app runtime.
- If LLM analysis is enabled, image + context are sent to chosen provider endpoint.
- Do not use this app for production clinical decisions or regulated diagnostic workflows without full compliance controls and validation.

## 15) Suggested improvements

- Add requirements file and lock versions.
- Split code into modules (`ui`, `analysis`, `llm`, `utils`).
- Add unit tests for heuristics and parsing.
- Add stronger input validation and telemetry/logging.
- Add configurable clinical pathways per body part/modality.
- Add secure secrets management for deployment.

## 16) Medical disclaimer

This software is for educational/non-diagnostic support only.
It does not provide medical advice, diagnosis, or treatment.
Always consult qualified healthcare professionals for clinical interpretation and decisions.
