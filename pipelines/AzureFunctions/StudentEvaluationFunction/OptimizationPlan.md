# Cost-Optimized Student Evaluation Pipeline

## Objective
Reduce per-evaluation cost from ₹15–25 to ₹1 or less, while maintaining high-quality feedback for students at scale (10,000+ evaluations/day).

## Answers to Key Questions

**Q1: Is teacher-student distillation contemporary?**

Yes — it's the dominant paradigm (Orca, Phi, DeepSeek-R1-Distill all use it). But in 2026, you should layer in these complementary techniques:

- **Pre-computed reference solutions (RAG-style)** — Eliminates the need for the model to "solve" the problem from scratch. You already have the chapter PDF and problem IDs. Generate correct solutions ONCE per problem, cache them, and provide them as grading rubrics. This makes the eval task much simpler (compare + critique vs. solve + compare + critique), so a smaller model can handle it.
- **Decomposed task distillation** — Don't distill the entire monolithic evaluation. Distill each sub-task separately: (a) handwriting extraction/OCR, (b) solution comparison, (c) feedback generation. Smaller, specialized models outperform one general model.
- **DPO/RLHF refinement** — After initial SFT distillation, use human preference data (you'll have this from students flagging bad feedback) to align the model further.
- **Confidence-based routing** — Cheap model handles 70-80% of evaluations; expensive model only for low-confidence cases (complex diagrams, chemistry structures, ambiguous handwriting).

**Q2: Can you hit ₹1/eval (25× reduction)?**

Yes, comfortably. Here's the math for three paths:

| Approach | Per-eval cost | Reduction | When |
|----------|--------------|-----------|------|
| Phase A: Cache solutions + Gemini Flash | ₹3-5 | 5-8× | Weeks 1-2 |
| Phase B: Distilled 72B VLM on Azure GPU | ₹0.50-1.50 | 15-30× | Weeks 3-8 |
| Phase C: Distilled 7-14B + quantized | ₹0.10-0.50 | 50-100× | Weeks 8-14 |

---

## Phased Strategy

### Phase A: Quick Wins (5–8× Reduction)

1. **Pre-compute Reference Solutions**
   - Generate and cache step-by-step solutions for all textbook problems using Gemini Pro.
   - Store in a `problem_solutions` table or blob.
   - Use cached solutions as grading rubrics instead of sending full chapter PDFs to the model.

2. **Modify Evaluation Pipeline**
   - Update `evaluate_batch` to use cached solutions for context.
   - Remove PDF from Gemini input, reducing input tokens by 50–70%.

3. **Switch to Cheaper Model**
   - Use `gemini-2.5-flash` for evaluation (10–20× cheaper than Pro).
   - Test quality on sample evaluations before full rollout.

4. **Tiered Feedback**
   - First pass: classify answers (Correct/Acceptable/Incorrect/Not Found).
   - Second pass: generate detailed feedback only for incorrect/acceptable answers.
   - Use templated feedback for correct answers.

5. **Optimize Image Handling**
   - Compress student images before sending to Gemini.
   - Increase batch size to 5 if quality remains acceptable.

**Expected Cost:** ₹3–5 per evaluation

---

### Phase B: Distillation to Open VLM (15–30× Reduction)

6. **Dataset Generation**
   - Run current pipeline on 8,000–12,000 diverse examples.
   - Store input/output pairs for fine-tuning.

7. **Model Selection**
   - Use open-source multimodal models (e.g., Qwen2.5-VL-72B, InternVL3-78B).
   - Benchmark zero-shot performance before fine-tuning.

8. **Fine-Tuning**
   - Use LoRA/QLoRA for efficient training.
   - Decompose tasks: classification, error pinpointing, feedback generation.

9. **Deployment**
   - Host on Azure GPU VMs (A100 80GB).
   - Use vLLM/TGI for efficient inference.
   - Add confidence-based routing: fallback to Gemini for low-confidence cases.

**Expected Cost:** ₹0.50–1.50 per evaluation

---

### Phase C: Deep Optimization (50–100× Reduction)

10. **Further Distillation**
    - Distill to 7B–14B models for simpler tasks.
    - Quantize to 4-bit for single T4 GPU hosting.

11. **Batch Inference**
    - Use micro-batching for maximum GPU utilization.

12. **Pre-compute Everything Possible**
    - Cache solutions, feedback templates, and context summaries.
    - Model focuses on handwriting extraction and delta feedback.

**Expected Cost:** ₹0.10–0.50 per evaluation

---

## Key Decisions
- Multi-phase approach: each phase delivers standalone value.
- Decomposed task distillation: higher quality, easier training.
- Solution pre-computation (RAG): foundational for all phases.
- Azure GPU self-hosting: most cost-effective at scale.
- Confidence-based routing: ensures quality for edge cases.

---

## Verification & Validation
- Automated metrics: classification accuracy, error pinpoint precision.
- Human evaluation: blind A/B tests with students.
- Latency and throughput benchmarks for deployment.

---

## Next Steps
- Implement Phase A optimizations immediately.
- Begin dataset generation for Phase B.
- Evaluate open-source model candidates and plan fine-tuning.
- Monitor cost and quality at each phase before scaling further.
