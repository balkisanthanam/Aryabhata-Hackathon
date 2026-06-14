# Solution Model & Evaluator Architecture

## 1. Executive Summary
This document outlines the architecture for replacing the costly Gemini 3.1 Pro solution generator with a cost-optimized, fine-tuned open-weight model for AryaBhatta. The architecture encompasses a **Hybrid Routing Pipeline**, an **LLM-as-a-Judge Evaluator**, and a **Supervised Fine-Tuning (SFT)** workflow.

---

## 2. Critical Evaluation of the Proposed Approach

Your proposed approach is closely aligned with modern industry best practices. Creating an "Open Source" STEM model using Gemini as a teacher is highly effective. However, a few modifications will drastically improve success and reduce complexity.

### Critique & Modifications

**1. Distillation vs. Fine-tuning vs. Compression:** 
In your proposal, steps 3 (Fine-tuning) and 4 (Distillation) are listed separately. Training a smaller, open-weight model on the outputs of a larger, state-of-the-art model (Gemini 3.1 Pro) *is* the definition of Knowledge Distillation. 
However, for Step 4 ("Distill this fine tuned model"), the best iteration is **Model Compression/Quantization**. To optimize inference costs, we will take the SFT 7B model and apply INT4 or FP8 quantization (e.g., AWQ/vLLM). This halves the required VRAM and drastically speeds up token generation.

**2. The Vision Constraint (Crucial Modification):**
STEM problems frequently include diagrams, circuits, or chemical structures. While open-weight *text* models (like Qwen Maths) are incredible, open-weight *Vision-Language Models (VLMs)* still struggle significantly with complex STEM diagrams. 
* **Recommendation (Hybrid Routing):** Do not try to solve multi-modality with the open-source model in Phase 1. Instead, route text-only questions (~70-80% of your bank) to the new fine-tuned model, and route image-based questions (`has_figure=true`) to Gemini 3.1 Pro. This captures 80% of the cost savings while avoiding the immense complexity of VLM fine-tuning.

**3. Evaluator Pipeline:**
Relying purely on human evaluation or LLM evaluation is inefficient. The most robust evaluator pipeline uses a deterministic "Exact Match" check against the NTA/NCERT official answer key *first*, and only invokes the Gemini Evaluator for the intermediate steps of correct answers.

**4. Hosted vs Serverless Break-even (Azure Foundry):**
Hosting a 7B model on Azure requires a dedicated GPU VM (e.g., NVIDIA L4 or A10G), which costs roughly $500–$800/month regardless of usage. Before hosting, we must ensure your projected monthly API costs exceed this amount. If your volume isn't high enough yet, leveraging Azure's Serverless Endpoints for OSS models is a safer, cost-effective intermediate step.

**5. RLHF Parking:**
Parking RLHF (Reinforcement Learning from Human Feedback) is a highly recommended decision. Modern SFT on a high-quality dataset of ~10k-20k well-formatted Teacher solutions is usually sufficient to enforce formatting constraints and tone.

---

## 3. Model Selection

### Generator (The Solution Model)
Instead of a generalist model (like Llama-3-8B), you should use a model explicitly pre-trained on math and STEM tokens.
* **Top Recommendation:** `Qwen2.5-Math-7B-Instruct` or `DeepSeek-Math-7B-Instruct`. These models punch significantly above their weight class (rivaling GPT-4 on math benchmarks) and are small enough to be hosted cheaply on a single GPU.

### Evaluator (The Judge Model)
* **Top Recommendation:** `Gemini 3.1 Pro`. It has an excellent context window, top-tier reasoning, and you are already utilizing it. It will act as the "LLM-as-a-Judge".

---

## 4. The Evaluator & Data Curation Pipeline

To train the open-source model, we need a flawless dataset. Garbage in, garbage out. The Evaluator pipeline filters existing Gemini solutions to create this "Gold" dataset.

### Evaluation Workflow
1. **Deterministic Check (Answer Key Match):** 
   Extract the `final_answer` from the Gemini generated JSON. Compare it mathematically/symbolically against the `answer_key` from `jee_question_bank` or NCERT answers.
   * *If Match:* Proceed to Step 2.
   * *If Mismatch / Hallucination:* Discard from training dataset entirely.
2. **Domain-Specific Verification (Chemistry Focus):**
   * Since you've noticed anecdotal quality issues in Chemistry, we must avoid polluting the training dataset. We will inject domain-specific validation via external tools (e.g., `rdkit` for chemical validation) or prompt the Evaluator systematically to verify stoichiometry, valency, and IUPAC nomenclature in all Chemistry solutions.
3. **LLM-as-a-Judge (Gemini Pro):**
   For solutions that matched the final answer (and passed domain checks), verify the *steps*. Pass the question + Gemini's steps + a Teacher Rubric to Gemini 3.1 Pro.
   * *Prompt criteria:* "Are the intermediate steps logically sound? Is the LaTeX perfectly formatted? Are there any logical leaps?"
   * *Output:* Score out of 5 + rationale.
   * *If Score >= 4:* Add to the Gold Dataset.
4. **Human Review Queue:**
   Take a random 5% sample of the Gold Dataset (with a higher ~15% sample rate for Chemistry due to known anomalies) and display it to SMEs (Subject Matter Experts) in a basic UI to ensure the LLM Judge isn't passing systematic flaws.

---

## 5. Training Pipeline (Supervised Fine-Tuning)

Once we have ~10,000+ Gold solutions:
1. **Data Formatting:** Convert the Gold dataset into conversational format (OpenAI/ShareGPT format), embedding the exact System Prompt the model will see in production.
2. **Training Framework:** Use `Axolotl` or `HuggingFace TRL` to perform **LoRA (Low-Rank Adaptation)** or **QLoRA**. This allows you to fine-tune a 7B model on a single A100 or L4 GPU in Azure in a matter of hours.
3. **Loss Objective:** Train the model to generate the exact JSON structure (`steps`, `final_answer`, `visual_needed`) to ensure the output can be parsed directly by the AryaBhatta frontend.

---

## 6. Target Architecture & Deployment

### Infrastructure (Azure AI Foundry / ML)
* **Serving Engine:** Deploy the fine-tuned model weights using **vLLM** (an open-source, high-throughput LLM serving engine) on Azure ML Managed Endpoints or an Azure VM.
* **API Compatibility:** vLLM exposes an OpenAI-compatible API, making it trivial to integrate into your existing python pipelines using the standard `openai` python package.

### Runtime Routing Logic (`solver_engine.py`)
Update your pipeline to dynamically route requests based on question metadata.

```python
def generate_solution(question):
    if question.has_figure:
        # Complex multi-modal data -> Expensive, capable model
        return invoke_gemini_3_1_pro(question)
    else:
        # Text-only STEM -> Cheap, fine-tuned OSS model
        return invoke_vllm_local_endpoint(question)
```

---

## 7. Phased Implementation Plan

* **Phase 1: Pipeline Evaluation & Data Generation**
  * Build the Evaluator script pairing the Answer Key check with the Gemini 3.1 Pro Judge.
  * Run the Evaluator over all currently extracted NCERT and JEE solutions.
  * Output: `<10k high-quality JSON training examples.
* **Phase 2: Base Model Prototyping**
  * Stand up `Qwen2.5-Math-7B-Instruct` locally/cloud via vLLM.
  * Evaluate its *zero-shot* capability on 50 JEE questions before fine-tuning, to set a baseline.
* **Phase 3: SFT and Distillation**
  * Fine-tune the model on the Gold dataset using Azure ML.
  * Evaluate the fine-tuned model against Gemini 3.1 Pro.
* **Phase 4: Pipeline Integration**
  * Implement the Hybrid Router in `solver_engine.py`.
  * Deploy the model to an Azure endpoint.

---
*Status: Draft for Review. Await confirmation before creating code modifications.*
