# Gemini Model Reference Audit

Date: 2026-05-29
Scope: Full workspace scan including ignored files and log folders.

## Requested model IDs

- gemini-2.5-flash
- gemini-2.5-flash-lite
- gemini-3-flash-preview
- gemini-2.5-flash-lite-preview-09-2025
- gemini-2.5-flash-preview-09-2025
- gemini-2.5-flash-preview-05-20
- gemini-3.1-flash-lite-preview

## Summary table

| Model ID | Active code/config references | Historical/docs/log references | Status |
|---|---|---|---|
| gemini-2.5-flash | pipelines/ModelEngineering/launch_tuning_job.py:54, pipelines/ExtractionPipeline/shared/FigureExtraction/figure_detector.py:71, pipelines/ExtractionPipeline/shared/exercise_detector.py:72, pipelines/ExtractionPipeline/shared/exercise_detector.py:327, pipelines/ExtractionPipeline/ImageBasedExtraction/config.json:14 | Design/Architecture/M3_TuningLoop_Plan.md:13, pipelines/ModelEngineering/runs/tuning_jobs.json:6, pipelines/ModelEngineering/runs/_launch_tune_v2.log:10, pipelines/AzureFunctions/StudentEvaluationFunction/OptimizationPlan.md:43 | In use |
| gemini-2.5-flash-lite | pipelines/AzureFunctions/StudentEvaluationFunction/utils/gemini_client.py:18, pipelines/ExtractionPipeline/JSONBasedExtraction/run_json_extraction.py:13 | pipelines/AzureFunctions/StudentEvaluationFunction/README.md:101, pipelines/AzureFunctions/StudentEvaluationFunction/PLAN.md:90, pipelines/AzureFunctions/StudentEvaluationFunction/tests/HOW_TO_TEST.md:61, pipelines/AzureFunctions/StudentEvaluationFunction/tests/output/*/meta.json:2, pipelines/AzureFunctions/StudentEvaluationFunction/funcstart.log:820 | In use |
| gemini-3-flash-preview | pipelines/ModelEngineering/verify_solver_accuracy.py:32, pipelines/ModelEngineering/verify_solver_accuracy_ncert.py:28, pipelines/ModelEngineering/batch_evaluator.py:62 | TempLocal/scale_format_11_Chemistry.log:19, TempLocal/scale_format_11_Maths.log:19, TempLocal/scale_format_11_Physics.log:19, TempLocal/scale_format_12_Chemistry.log:19, TempLocal/scale_format_12_Maths.log:19, TempLocal/scale_format_12_Physics.log:19, pipelines/ModelEngineering/runs/_verify_solver_ncert.log:7, pipelines/ModelEngineering/runs/_verify_solver_ncert_RESULT.md:1, Design/Architecture/M3_Ship_Plan.md:3 | In use |
| gemini-3.1-flash-lite-preview | pipelines/JEEAscentPipeline/jee_jsonleak_repair.py:336, pipelines/JEEAscentPipeline/subject_auditor.py:345, pipelines/JEEAscentPipeline/subject_auditor_perq.py:294 | pipelines/JEEAscentPipeline/logs/audit_perq_2024_dry.log:9, pipelines/JEEAscentPipeline/logs/audit_perq_2024_apply.log:9, plus additional JEEAscentPipeline log files | In use in JEE Ascent scripts |
| gemini-2.5-flash-lite-preview-09-2025 | None | None | No matches |
| gemini-2.5-flash-preview-09-2025 | None | None | No matches |
| gemini-2.5-flash-preview-05-20 | None | None | No matches |

## Detailed references

### gemini-2.5-flash

Active
- pipelines/ModelEngineering/launch_tuning_job.py:54
- pipelines/ExtractionPipeline/shared/FigureExtraction/figure_detector.py:71
- pipelines/ExtractionPipeline/shared/exercise_detector.py:72
- pipelines/ExtractionPipeline/shared/exercise_detector.py:327
- pipelines/ExtractionPipeline/ImageBasedExtraction/config.json:14

Historical/docs/logs
- Design/Architecture/M3_TuningLoop_Plan.md:13
- Design/Architecture/M3_TuningLoop_Plan.md:267
- Design/Architecture/M3_TuningLoop_Plan.md:294
- pipelines/ModelEngineering/runs/tuning_jobs.json:6
- pipelines/ModelEngineering/runs/tuning_jobs.json:19
- pipelines/ModelEngineering/runs/_launch_tune_v2.log:10
- pipelines/AzureFunctions/StudentEvaluationFunction/OptimizationPlan.md:43

### gemini-2.5-flash-lite

Active
- pipelines/AzureFunctions/StudentEvaluationFunction/utils/gemini_client.py:18
- pipelines/ExtractionPipeline/JSONBasedExtraction/run_json_extraction.py:13

Historical/docs/logs
- pipelines/AzureFunctions/StudentEvaluationFunction/README.md:101
- pipelines/AzureFunctions/StudentEvaluationFunction/PLAN.md:90
- pipelines/AzureFunctions/StudentEvaluationFunction/PLAN.md:175
- pipelines/AzureFunctions/StudentEvaluationFunction/PLAN.md:475
- pipelines/AzureFunctions/StudentEvaluationFunction/tests/HOW_TO_TEST.md:61
- pipelines/AzureFunctions/StudentEvaluationFunction/tests/HOW_TO_TEST.md:345
- pipelines/AzureFunctions/StudentEvaluationFunction/tests/HOW_TO_TEST.md:399
- pipelines/AzureFunctions/StudentEvaluationFunction/tests/output/*/meta.json:2 (multiple files)
- pipelines/AzureFunctions/StudentEvaluationFunction/funcstart.log:820
- pipelines/AzureFunctions/StudentEvaluationFunction/funcstart_2.log:776

### gemini-3-flash-preview

Active
- pipelines/ModelEngineering/verify_solver_accuracy.py:32
- pipelines/ModelEngineering/verify_solver_accuracy_ncert.py:28
- pipelines/ModelEngineering/batch_evaluator.py:62

Historical/docs/logs
- Design/Architecture/M3_Ship_Plan.md:3
- Design/Architecture/M3_Ship_Plan.md:8
- Design/Architecture/M3_Ship_Plan.md:12
- Design/Architecture/M3_Ship_Plan.md:13
- pipelines/ModelEngineering/runs/_verify_solver_ncert_RESULT.md:1
- pipelines/ModelEngineering/runs/_verify_solver_ncert.log:7
- TempLocal/scale_format_11_Chemistry.log:19
- TempLocal/scale_format_11_Maths.log:19
- TempLocal/scale_format_11_Physics.log:19
- TempLocal/scale_format_12_Chemistry.log:19
- TempLocal/scale_format_12_Maths.log:19
- TempLocal/scale_format_12_Physics.log:19

### gemini-3.1-flash-lite-preview

Active
- pipelines/JEEAscentPipeline/jee_jsonleak_repair.py:336
- pipelines/JEEAscentPipeline/subject_auditor.py:345
- pipelines/JEEAscentPipeline/subject_auditor_perq.py:294

Historical/logs
- pipelines/JEEAscentPipeline/logs/audit_perq_2024_dry.log:9 (many repeated calls)
- pipelines/JEEAscentPipeline/logs/audit_perq_2024_apply.log:9 (many repeated calls)
- pipelines/JEEAscentPipeline/logs/jsonleak_dryrun_2024_full.log (multiple)
- pipelines/JEEAscentPipeline/logs/jsonleak_dryrun_2023.log (multiple)
- pipelines/JEEAscentPipeline/logs/jsonleak_apply_2024.log (multiple)
- pipelines/JEEAscentPipeline/logs/jsonleak_apply_2023.log (multiple)

### No-match models

- gemini-2.5-flash-lite-preview-09-2025: no references found
- gemini-2.5-flash-preview-09-2025: no references found
- gemini-2.5-flash-preview-05-20: no references found
