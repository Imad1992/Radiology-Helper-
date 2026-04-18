import base64
import io
import json
import os
import re
from typing import Dict, List, Tuple

import numpy as np
import requests
import streamlit as st
from PIL import Image

st.set_page_config(page_title="Radiology Helper (Non-diagnostic)", layout="wide")

DISCLAIMER = """
**Important:** This app provides **non-diagnostic support only**. It does not replace radiologists,
clinicians, or emergency care. Imaging diagnosis requires full clinical context and original studies.
If severe or worsening symptoms are present, seek urgent medical care immediately.
"""


def apply_custom_theme() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,700&family=Space+Grotesk:wght@400;500;700&display=swap');

            :root {
                --bg-0: #f3f5f7;
                --bg-1: #e8f1f4;
                --ink-0: #11212a;
                --ink-1: #274252;
                --accent: #d65a31;
                --accent-soft: #fef0e8;
                --panel: #ffffff;
                --line: #d7e2e7;
                --ok: #1f8f5f;
                --warn: #ab3e16;
            }

            .stApp {
                background:
                    radial-gradient(1200px 500px at 2% -10%, #d7edf3 0%, transparent 65%),
                    radial-gradient(1000px 500px at 102% 0%, #fde7d8 0%, transparent 60%),
                    linear-gradient(180deg, var(--bg-0), var(--bg-1));
                color: var(--ink-0);
            }

            .block-container {
                padding-top: 1.2rem;
                padding-bottom: 2rem;
            }

            h1, h2, h3 {
                font-family: 'Fraunces', Georgia, serif !important;
                letter-spacing: 0.1px;
                color: var(--ink-0);
            }

            p, li, div, label, input, textarea, .stMarkdown {
                font-family: 'Space Grotesk', 'Segoe UI', sans-serif !important;
            }

            .hero {
                background: linear-gradient(135deg, #123647 0%, #2a4f63 55%, #3f6a7b 100%);
                color: #fff;
                border-radius: 18px;
                padding: 1.2rem 1.4rem;
                border: 1px solid rgba(255, 255, 255, 0.14);
                box-shadow: 0 14px 30px rgba(8, 30, 40, 0.22);
                margin-bottom: 0.9rem;
            }

            .hero h2 {
                color: #fff;
                margin: 0;
                font-size: 1.7rem;
            }

            .hero p {
                margin: 0.5rem 0 0 0;
                color: #d6ebf4;
                max-width: 920px;
            }

            .chip {
                display: inline-block;
                margin-top: 0.7rem;
                padding: 0.2rem 0.65rem;
                border-radius: 999px;
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.22);
                font-size: 0.8rem;
                color: #fff;
            }

            .glass {
                background: rgba(255, 255, 255, 0.72);
                border: 1px solid var(--line);
                border-radius: 14px;
                padding: 0.9rem 1rem;
            }

            .urgency {
                display: inline-flex;
                align-items: center;
                gap: 0.35rem;
                padding: 0.35rem 0.8rem;
                border-radius: 999px;
                font-weight: 700;
                border: 1px solid transparent;
            }

            .urgency.low { background: #edf7f1; color: #146c45; border-color: #bfe3ce; }
            .urgency.moderate { background: #fff8e8; color: #9d6200; border-color: #f0d7a0; }
            .urgency.high { background: #ffeedd; color: #a54800; border-color: #f3c29c; }
            .urgency.emergency { background: #ffe8e8; color: #9b1d1d; border-color: #f2b5b5; }

            [data-testid="stSidebar"] {
                border-right: 1px solid #d8e3e9;
                background: linear-gradient(180deg, #fbfeff, #f4f8fa);
            }

            .stButton > button {
                border-radius: 12px;
                border: 0;
                background: linear-gradient(135deg, #d65a31, #b94622);
                color: white;
                font-weight: 700;
                box-shadow: 0 8px 20px rgba(175, 72, 35, 0.35);
            }

            .stButton > button:hover {
                transform: translateY(-1px);
            }

            [data-testid="stMetricValue"] {
                color: var(--ink-1);
                font-weight: 700;
            }

            @media (max-width: 900px) {
                .hero h2 { font-size: 1.35rem; }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_urgency_badge(urgency: str) -> None:
    class_name = urgency.lower()
    st.markdown(
        f"<div class='urgency {class_name}'>Priority: {urgency}</div>",
        unsafe_allow_html=True,
    )


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def keyword_score(text: str, keywords: List[str]) -> int:
    return sum(1 for kw in keywords if kw in text)


def urgency_rank(level: str) -> int:
    return {"LOW": 1, "MODERATE": 2, "HIGH": 3, "EMERGENCY": 4}.get(level, 1)


def clamp_confidence(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def analyze_image_quality(image: Image.Image) -> Dict[str, object]:
    gray = np.array(image.convert("L"), dtype=np.float32)
    h, w = gray.shape
    total = float(h * w)

    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))

    gx = np.diff(gray, axis=1)
    gy = np.diff(gray, axis=0)
    edge_strength = float(np.mean(np.abs(gx)) + np.mean(np.abs(gy))) / 2.0

    very_dark_ratio = float(np.sum(gray < 15.0) / total)
    very_bright_ratio = float(np.sum(gray > 240.0) / total)

    quality_flags = []
    quality_suggestions = []

    if brightness < 50:
        quality_flags.append("Image appears underexposed (too dark).")
        quality_suggestions.append("Retake or export a brighter image if available.")
    elif brightness > 205:
        quality_flags.append("Image appears overexposed (too bright).")
        quality_suggestions.append("Retake or export with lower exposure/brightness.")

    if contrast < 25:
        quality_flags.append("Low contrast may hide important structures.")
        quality_suggestions.append("Use original study viewer settings and avoid compressed screenshots.")

    if edge_strength < 8:
        quality_flags.append("Image may be blurry or low detail.")
        quality_suggestions.append("Use a sharper image with higher resolution if possible.")

    if very_dark_ratio > 0.45:
        quality_flags.append("Large dark regions detected; field of view may be incomplete.")
        quality_suggestions.append("Center the target anatomy and include full region of interest.")

    if very_bright_ratio > 0.45:
        quality_flags.append("Large bright regions detected; details may be clipped.")
        quality_suggestions.append("Adjust capture/export windowing to preserve detail.")

    if min(h, w) < 512:
        quality_flags.append("Low resolution image.")
        quality_suggestions.append("Upload a higher-resolution image or original report/study export.")

    return {
        "metrics": {
            "size": f"{w} x {h}",
            "brightness": round(brightness, 1),
            "contrast": round(contrast, 1),
            "edge_strength": round(edge_strength, 1),
        },
        "flags": quality_flags,
        "suggestions": quality_suggestions,
        "usable_for_screening": len(quality_flags) <= 2,
    }


def local_visual_observations(image: Image.Image) -> List[str]:
    gray = np.array(image.convert("L"), dtype=np.float32)
    h, w = gray.shape

    center = gray[h // 4 : (3 * h) // 4, w // 4 : (3 * w) // 4]
    periphery_mask = np.ones_like(gray, dtype=bool)
    periphery_mask[h // 4 : (3 * h) // 4, w // 4 : (3 * w) // 4] = False
    periphery = gray[periphery_mask]

    center_mean = float(np.mean(center))
    periphery_mean = float(np.mean(periphery))
    dynamic_range = float(np.percentile(gray, 95) - np.percentile(gray, 5))

    observations = []

    if center_mean - periphery_mean > 18:
        observations.append("Central region appears denser/brighter than periphery.")
    elif periphery_mean - center_mean > 18:
        observations.append("Periphery appears brighter than central region.")

    if dynamic_range < 40:
        observations.append("Limited grayscale range; subtle findings may be hard to distinguish.")
    elif dynamic_range > 120:
        observations.append("Wide grayscale range detected.")

    if not observations:
        observations.append("No strong global visual pattern detected by local heuristics.")

    return observations


def analyze_symptoms(symptoms: str, body_part: str, modality: str) -> Dict[str, object]:
    text = normalize_text(symptoms)

    issue_rules: List[Tuple[str, List[str], str]] = [
        (
            "Possible respiratory infection/inflammation",
            ["fever", "cough", "chest pain", "shortness of breath", "phlegm"],
            "MODERATE",
        ),
        (
            "Possible trauma-related injury",
            ["fall", "accident", "injury", "trauma", "hit", "fracture", "pain after"],
            "HIGH",
        ),
        (
            "Possible neurologic emergency pattern",
            ["slurred speech", "facial droop", "weakness", "numbness", "confusion", "seizure"],
            "EMERGENCY",
        ),
        (
            "Possible severe infection/systemic illness",
            ["high fever", "chills", "very sick", "sepsis", "persistent vomiting"],
            "HIGH",
        ),
        (
            "Possible degenerative or inflammatory musculoskeletal issue",
            ["chronic pain", "stiffness", "swelling", "limited movement", "joint pain"],
            "MODERATE",
        ),
    ]

    matched_issues = []
    urgency_rank = {"LOW": 1, "MODERATE": 2, "HIGH": 3, "EMERGENCY": 4}
    top_urgency = "LOW"

    for issue_name, keys, severity in issue_rules:
        score = keyword_score(text, keys)
        if score > 0:
            confidence = min(0.35 + score * 0.15, 0.9)
            matched_issues.append(
                {
                    "label": issue_name,
                    "confidence": round(confidence, 2),
                    "reason": f"Matched {score} symptom keyword(s).",
                    "severity": severity,
                }
            )
            if urgency_rank[severity] > urgency_rank[top_urgency]:
                top_urgency = severity

    if not matched_issues:
        matched_issues.append(
            {
                "label": "No clear symptom pattern recognized",
                "confidence": 0.25,
                "reason": "Symptoms are non-specific or absent.",
                "severity": "LOW",
            }
        )

    body_modality_notes = []
    if body_part == "Chest" and modality == "MRI":
        body_modality_notes.append("Chest MRI is less common for first-line lung evaluation than chest X-ray/CT.")
    if body_part == "Head/Brain" and modality == "X-ray":
        body_modality_notes.append("Head/brain X-ray has limited value for many neurologic causes.")

    red_flags = [
        "Severe chest pain or trouble breathing",
        "New one-sided weakness, facial droop, slurred speech, or confusion",
        "Loss of consciousness, seizure, or major trauma",
        "Persistent high fever with worsening condition",
        "Rapidly worsening pain, swelling, or inability to move a limb",
    ]

    return {
        "issues": matched_issues,
        "urgency": top_urgency,
        "red_flags": red_flags,
        "notes": body_modality_notes,
    }


def build_recommendations(urgency: str, quality_data: Dict[str, object], has_symptoms: bool) -> List[str]:
    recs = []

    if urgency == "EMERGENCY":
        recs.append("Seek emergency care now (ER/emergency services).")
    elif urgency == "HIGH":
        recs.append("Arrange urgent same-day clinical evaluation.")
    elif urgency == "MODERATE":
        recs.append("Book a clinician/radiology review soon (within 24-72 hours if symptoms persist).")
    else:
        recs.append("Monitor symptoms and arrange a routine clinician review if symptoms continue.")

    if not quality_data["usable_for_screening"]:
        recs.append("Image quality is limited; provide original study files/reports or a better image for review.")

    if has_symptoms:
        recs.append("Share full symptom timeline, prior reports, and medications during the appointment.")

    recs.append("This app output is non-diagnostic and should not be used as a final medical decision.")
    return recs


def to_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def extract_json_object(text: str) -> Dict[str, object]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)

    return json.loads(cleaned)


def build_vision_prompts(modality: str, body_part: str, symptoms: str) -> Tuple[str, str]:
    system_prompt = (
        "You are a radiology support assistant. You MUST stay non-diagnostic and safety-first. "
        "You may provide suspected issue categories only, never definitive diagnoses. "
        "Respond in strict JSON only."
    )

    user_prompt = f"""
Analyze this uploaded medical image with context.

Context:
- Modality: {modality}
- Body part: {body_part}
- Symptoms/context: {symptoms if symptoms.strip() else "Not provided"}

Return only valid JSON with this exact schema:
{{
  "summary": "short non-diagnostic summary",
  "possible_issues": [
    {{"label": "string", "confidence": 0.0, "reason": "string", "severity": "LOW|MODERATE|HIGH|EMERGENCY"}}
  ],
  "urgency": "LOW|MODERATE|HIGH|EMERGENCY",
  "suggested_next_steps": ["string"],
  "image_observations": ["string"],
  "limitations": ["string"]
}}

Rules:
- Never claim a confirmed diagnosis.
- Mention uncertainty when appropriate.
- If image quality is poor, say so in limitations.
- Keep confidence realistic and conservative.
"""

    return system_prompt, user_prompt


def parse_llm_json_response(response: requests.Response, provider_name: str) -> Dict[str, object]:
    if not response.ok:
        detail = response.text
        try:
            error_payload = response.json()
            detail = error_payload.get("error", {}).get("message", detail)
        except Exception:
            pass
        raise RuntimeError(f"{provider_name} API error {response.status_code}: {detail}")

    data = response.json()
    message_text = data["choices"][0]["message"]["content"]
    parsed = extract_json_object(message_text)

    return {
        "summary": str(parsed.get("summary", "No summary returned.")),
        "possible_issues": parsed.get("possible_issues", []),
        "urgency": str(parsed.get("urgency", "LOW")).upper(),
        "suggested_next_steps": parsed.get("suggested_next_steps", []),
        "image_observations": parsed.get("image_observations", []),
        "limitations": parsed.get("limitations", []),
    }


def call_openrouter_vision(
    image: Image.Image,
    modality: str,
    body_part: str,
    symptoms: str,
    api_key: str,
    model_name: str,
) -> Dict[str, object]:
    image_url = to_data_url(image)
    system_prompt, user_prompt = build_vision_prompts(modality, body_part, symptoms)

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": 1000,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Radiology Helper Non-Diagnostic",
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        data=json.dumps(payload),
        timeout=60,
    )

    return parse_llm_json_response(response, "OpenRouter")


def call_github_models_vision(
    image: Image.Image,
    modality: str,
    body_part: str,
    symptoms: str,
    api_key: str,
    model_name: str,
) -> Dict[str, object]:
    image_url = to_data_url(image)
    system_prompt, user_prompt = build_vision_prompts(modality, body_part, symptoms)

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": 1000,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        "https://models.inference.ai.azure.com/chat/completions",
        headers=headers,
        data=json.dumps(payload),
        timeout=60,
    )

    return parse_llm_json_response(response, "GitHub Models")


def merge_issues(local_issues: List[Dict[str, object]], llm_issues: List[Dict[str, object]]) -> List[Dict[str, object]]:
    merged = []
    seen = set()

    for src, source_name in [(llm_issues, "LLM"), (local_issues, "Local")]:
        for issue in src:
            label = str(issue.get("label", "Unknown issue")).strip()
            key = label.lower()
            if key in seen:
                continue

            seen.add(key)
            conf = clamp_confidence(float(issue.get("confidence", 0.35)))
            severity = str(issue.get("severity", "LOW")).upper()
            if severity not in {"LOW", "MODERATE", "HIGH", "EMERGENCY"}:
                severity = "LOW"

            merged.append(
                {
                    "label": label,
                    "confidence": conf,
                    "reason": str(issue.get("reason", "No reason provided.")),
                    "severity": severity,
                    "source": source_name,
                }
            )

    if not merged:
        merged.append(
            {
                "label": "No clear issue category identified",
                "confidence": 0.25,
                "reason": "Insufficient distinctive findings in current inputs.",
                "severity": "LOW",
                "source": "Local",
            }
        )

    return merged


def analyze_case(
    image: Image.Image,
    modality: str,
    body_part: str,
    symptoms: str,
    api_key: str,
    model_name: str,
    provider: str,
    enable_llm: bool,
) -> Dict[str, object]:
    quality = analyze_image_quality(image)
    symptom_result = analyze_symptoms(symptoms, body_part, modality)
    visual_notes = local_visual_observations(image)

    llm_output = None
    llm_error = ""
    if enable_llm and api_key.strip():
        try:
            if provider == "GitHub Models":
                llm_output = call_github_models_vision(
                    image=image,
                    modality=modality,
                    body_part=body_part,
                    symptoms=symptoms,
                    api_key=api_key.strip(),
                    model_name=model_name.strip(),
                )
            else:
                llm_output = call_openrouter_vision(
                    image=image,
                    modality=modality,
                    body_part=body_part,
                    symptoms=symptoms,
                    api_key=api_key.strip(),
                    model_name=model_name.strip(),
                )
        except Exception as ex:
            llm_error = str(ex)

    urgency = symptom_result["urgency"]
    if llm_output and urgency_rank(llm_output["urgency"]) > urgency_rank(urgency):
        urgency = llm_output["urgency"]
    if len(quality["flags"]) >= 4 and urgency == "LOW":
        urgency = "MODERATE"

    recommendations = build_recommendations(urgency, quality, has_symptoms=bool(symptoms.strip()))
    if llm_output:
        recommendations = llm_output["suggested_next_steps"] + recommendations

    merged_issues = merge_issues(symptom_result["issues"], llm_output["possible_issues"] if llm_output else [])

    if llm_output:
        summary = (
            f"{llm_output['summary']} "
            "Combined with local quality and symptom triage checks. Final interpretation still requires clinician review."
        )
    else:
        summary = (
            "Local non-diagnostic analysis complete. Add a free OpenRouter API key for image-specific LLM findings. "
            "Final interpretation requires clinician/radiologist review."
        )

    return {
        "summary": summary,
        "possible_issues": merged_issues,
        "urgency": urgency,
        "quality": quality,
        "recommendations": recommendations,
        "red_flags": symptom_result["red_flags"],
        "notes": symptom_result["notes"],
        "visual_observations": (llm_output["image_observations"] if llm_output else []) + visual_notes,
        "limitations": (llm_output["limitations"] if llm_output else []) + [
            "This output is non-diagnostic and cannot replace radiologist interpretation.",
        ],
        "llm_used": bool(llm_output),
        "llm_error": llm_error,
    }


apply_custom_theme()

st.markdown(
    """
    <section class="hero">
        <h2>Radiology Helper</h2>
        <p>
            Upload an image, add clinical context, and get a non-diagnostic triage summary with urgency and next-step suggestions.
            This tool supports decision support only and is not a medical diagnosis.
        </p>
        <span class="chip">Educational support tool</span>
    </section>
    """,
    unsafe_allow_html=True,
)

st.markdown(DISCLAIMER)

with st.sidebar:
    st.header("AI Model Settings")
    use_llm = st.checkbox("Use vision LLM analysis", value=True)
    provider = st.selectbox("Provider", ["OpenRouter", "GitHub Models"], index=1)

    if provider == "GitHub Models":
        default_api_key = os.getenv("GITHUB_TOKEN", "")
        default_model = "openai/gpt-4.1-mini"
        key_env_name = "GITHUB_TOKEN"
        key_label = "GitHub Token"
        model_help = "Use a GitHub Models vision-capable model your account can access."
    else:
        default_api_key = os.getenv("OPENROUTER_API_KEY", "")
        default_model = "meta-llama/llama-3.2-11b-vision-instruct:free"
        key_env_name = "OPENROUTER_API_KEY"
        key_label = "OpenRouter API Key"
        model_help = "Use an OpenRouter vision-capable model, including free-tier variants."

    if default_api_key:
        st.caption(f"API key source: environment variable {key_env_name}")
    else:
        st.caption(f"API key source: not found in {key_env_name}")
    openrouter_key = st.text_input(
        key_label,
        value=default_api_key,
        type="password",
        help=f"Reads {key_env_name} automatically if set. You can still paste manually.",
    )
    model_name = st.text_input(
        "Model",
        value=default_model,
        help=model_help,
    )
    st.caption("No key? App will run local analysis only.")

st.markdown("<div class='glass'>", unsafe_allow_html=True)

with st.container(border=True):
    st.subheader("Case Details")
    modality = st.selectbox("Modality", ["X-ray", "MRI"], index=0)
    body_part = st.selectbox("Body part", ["Chest", "Head/Brain", "Spine", "Knee", "Other"], index=0)
    symptoms = st.text_area(
        "Symptoms / context",
        placeholder="e.g., fever + cough 3 days, recent fall, chest pain, weakness on one side...",
        help="Include duration, severity, and any relevant events (trauma, surgery, infection).",
    )

st.markdown("</div>", unsafe_allow_html=True)

uploaded = st.file_uploader("Upload image (PNG/JPG)", type=["png", "jpg", "jpeg"])

if uploaded:
    img = Image.open(uploaded).convert("RGB")

    c_img, c_meta = st.columns([1.45, 1], gap="large")
    with c_img:
        st.image(img, caption="Uploaded image", width="stretch")
    with c_meta:
        w, h = img.size
        st.metric("Resolution", f"{w} x {h}")
        st.metric("Color Mode", img.mode)
        st.caption("Tip: clearer, higher-resolution images generally produce better analysis support.")

    if st.button("Analyze Case", type="primary"):
        with st.spinner("Running non-diagnostic analysis..."):
            result = analyze_case(
                image=img,
                modality=modality,
                body_part=body_part,
                symptoms=symptoms,
                api_key=openrouter_key,
                model_name=model_name,
                provider=provider,
                enable_llm=use_llm,
            )

        if use_llm and not openrouter_key.strip():
            st.warning(f"Vision LLM is enabled but no {key_label} was provided. Showing local analysis only.")
        if result["llm_error"]:
            st.warning(f"LLM call failed, so local analysis was used: {result['llm_error']}")
        if result["llm_used"]:
            st.success("Image-specific LLM analysis was used for this result.")

        st.subheader("Summary")
        st.write(result["summary"])

        st.subheader("Urgency")
        render_urgency_badge(result["urgency"])

        tab1, tab2, tab3, tab4 = st.tabs(["Issue Signals", "Quality", "Actions", "Safety"])

        with tab1:
            st.markdown("### Likely Issue Categories")
            for item in result["possible_issues"]:
                st.write(
                    f"- {item['label']} | confidence ~ {item['confidence']:.2f} | severity: {item['severity']} | source: {item['source']} | {item['reason']}"
                )

            st.markdown("### Image Observations")
            for obs in result["visual_observations"]:
                st.write(f"- {obs}")

            if result["notes"]:
                st.markdown("### Context Notes")
                for note in result["notes"]:
                    st.write(f"- {note}")

        with tab2:
            st.markdown("### Image Quality Check")
            metrics = result["quality"]["metrics"]
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Size", metrics["size"])
            col2.metric("Brightness", str(metrics["brightness"]))
            col3.metric("Contrast", str(metrics["contrast"]))
            col4.metric("Edge Detail", str(metrics["edge_strength"]))

            if result["quality"]["flags"]:
                st.write("Detected image-quality issues:")
                for flag in result["quality"]["flags"]:
                    st.write(f"- {flag}")
            else:
                st.success("No major image-quality issue detected.")

        with tab3:
            st.markdown("### Suggested Next Steps")
            for step in result["recommendations"]:
                st.write(f"- {step}")

        with tab4:
            st.markdown("### Red Flags")
            for rf in result["red_flags"]:
                st.write(f"- {rf}")

            st.markdown("### Limitations")
            for item in result["limitations"]:
                st.write(f"- {item}")
else:
    st.info("Upload an image to start analysis.")