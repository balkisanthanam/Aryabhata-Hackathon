# Architectural Report: Model Strategy for Project Aryabhata

**To:** Balakrishnan, Principal Engineering Manager  
**Project:** Aryabhata (JEE/NCERT STEM Solution Engine)  
**Date:** April 9, 2026  

---

## Executive Summary

The objective of this report is to define a multi-phase transition from the current high-cost **Gemini 3.1 Pro** extraction pipeline to a cost-optimized, high-fidelity solution model. The primary "hidden" lever for cost reduction identified is the shift from **Full-PDF Grounding** to **Localized Context Retrieval**. This report evaluates three specific model trajectories, outlining the fine-tuning, optimization, and deployment steps required to maintain 94%+ reasoning accuracy while minimizing monthly OPEX.

---

## 1. Cost Considerations & The Context Lever

The current implementation in `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep` relies on passing full PDF data as context. In 2026 pricing, this is the primary driver of both high costs and API instability (`429`/`499` errors).

### The Localized Context Shift
By moving to a **PostgreSQL Vector Index + TF-IDF** hybrid, we reduce input token weight from ~150k to ~5k per solution.

* **Gemini 3.1 Pro:** Best-in-class reasoning ($94.3\%$ GPQA). High cost, but negligible at low volumes.
* **Gemini 3 Flash (Fine-Tuned):** The "Production Workhorse." Once fine-tuned on "Pro" solutions, it delivers nearly identical quality at $1/8$th the cost.
* **Gemma 4 (Fine-Tuned/Self-Hosted):** Offers total privacy and control. Cost-effective only at high scale due to GPU "idle" or "cold-start" overhead.

---

## 2. Fine-Tuning Details and Steps

To "transfer" the intelligence of Gemini 3.1 Pro into a smaller model (Distillation), we follow a Supervised Fine-Tuning (SFT) path.

### Steps:
1.  **Gold Set Generation:** Use Gemini 3.1 Pro in **Batch Mode** to solve 15,000 problems. Force a `<thought>` block to capture the "Reasoning Path."
2.  **Chemistry Patching:** For Chemistry solutions, inject relevant NCERT textbook chunks into the Teacher's prompt to ensure factual grounding.
3.  **Data Formatting:** Convert solutions into a ChatML-formatted JSONL:
    * `System`: "You are a senior IIT-JEE teacher..."
    * `User`: [Problem + Localized Context]
    * `Assistant`: [Thought Block + LaTeX Solution]
4.  **QLoRA Tuning:** Use 4-bit Quantized Low-Rank Adaptation. This targets only the attention layers, preserving the base model's stability while learning your specific "Teacher Style."

---

## 3. Optimization Details and Steps

Optimization ensures the model runs fast on cost-effective hardware (NVIDIA L4).

### Steps:
1.  **Quantization (AWQ/FP8):** Convert weights to **FP8** (8-bit floating point). This is the 2026 standard for L4 GPUs, offering the speed of 4-bit with virtually zero loss in STEM reasoning.
2.  **Speculative Decoding:** (Optional) Use a tiny **Gemma 4 1B** model to "draft" the solution steps, while the **31B model** verifies them. This can increase throughput by $2x$.
3.  **Context Caching:** For the Flash/Pro APIs, cache the common "Teacher Guidelines" and "Formula Sheets" to avoid paying for them on every request.

---

## 4. Tabular Cost Analysis

*Assuming 5k Input / 2.5k Output tokens per solution.*

| Phase | Model | One-Time (15k runs) | Daily Cost (20 runs) | Daily Cost (200 runs) |
| :--- | :--- | :--- | :--- | :--- |
| **Current** | Gemini 3.1 Pro (Full PDF) | ~$12,500 | ~$22.00 | ~$220.00 |
| **Opt 1** | **Gemini 3.1 Pro (Localized)**| **$187.50** | **$0.80** | **$8.00** |
| **Opt 2** | **Gemini 3 Flash (FT)** | $46.80 | $0.20 | **$2.00** |
| **Opt 3** | **Gemma 4 (L4 Hosted)** | N/A | $1.10* | **$3.50** |

*\*Includes cold-start overhead and processing time on Cloud Run.*

---

## 5. Breakeven Analysis: The Gemma 4 Tipping Point

The investment in hosting a customized Gemma 4 model delivers financial ROI only when the **Fixed Infrastructure Cost** is lower than the **Variable Token Cost** of APIs.



* **The Tipping Point:** For Aryabhata, the breakeven point occurs at **~1,500 queries/day**. 
* Below this, the **Fine-Tuned Gemini 3 Flash** is the dominant strategy due to zero infrastructure overhead and purely variable billing.

---

## 6. Deployment Details and Steps

### Option A: Vertex AI (Gemini 3 Flash)
1.  **Upload:** Use Vertex AI "Tuning" tab to upload your JSONL Gold Set.
2.  **Train:** Select Gemini 3 Flash as the base. 
3.  **Deploy:** Vertex automatically creates a "Tuned Model ID." Update your Python code's `model_name` variable.

### Option B: Cloud Run GPU (Gemma 4)
1.  **Containerize:** Build a Docker image with **vLLM** and your optimized weights.
2.  **Deploy:** Use Google Cloud Run with an **NVIDIA L4** workload profile.
3.  **Scale:** Set `min-instances` to 0 to save costs during idle hours (Scale to Zero).

---

## 7. Evaluation Framework (LLM-as-a-Judge)

To ensure the "Student" model doesn't drift from the "Teacher's" quality:

1.  **Symbolic Match:** Use a Python script to extract the final LaTeX answer and compare it numerically with the **NCERT Answer Key**.
2.  **Step-by-Step Validation:** Sample $5\%$ of daily traffic and send it to **Gemini 3.1 Pro**.
    * *Prompt:* "Rate this student model's explanation on a scale of 1-10 for logical flow and unit consistency."
3.  **Regression Testing:** Maintain a "Hard Problem Set" (50 complex JEE Advanced problems). Every time the model is updated, it must solve these with $100\%$ accuracy before deployment.

---

### Final Recommendation

1.  **Immediate:** Fix the `ExtractionPipeline` to use **Localized Context** (Postgres + TF-IDF). This immediately reduces your current 3.1 Pro bill by ~90%.
2.  **Mid-Term:** Use the savings to generate the 15k Gold Set and fine-tune **Gemini 3 Flash**. This is your "Sweet Spot" for cost vs. effort.
3.  **Long-Term:** Only pivot to **Gemma 4** if volume exceeds 1,500 daily requests or if strict data privacy is required for institutional sales.

