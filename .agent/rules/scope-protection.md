# Aryabhata Project Safety Rules

## 1. Primary Scope
- **Active Workspace:** You are only authorized to create, modify, or delete files within the `/apps/FrontEnd` directory.
- **Project Goal:** Build a React 18 + Vite frontend based on the Google Stitch designs.

## 2. Strict Restrictions (Read-Only)
- **Data Pipelines:** The `/pipelines` directory (including `ExtractionPipeline`, `DataCollection`, and `AzureFunctions`) is **READ-ONLY**. You may read these files to understand data structures, but you must NEVER modify or delete them.
- **Root Files:** Do not modify root configuration files like `AryaBhatta.code-workspace` or `package-lock.json` unless specifically asked.

## 3. Command Safety
- Never run broad deletion commands (e.g., `git clean`, `rm -rf`).
- All terminal commands (like `npm install`) must be executed specifically inside the `/apps/FrontEnd` folder.

## 4. Preservation
- Do not attempt to "refactor" or "clean up" existing folders outside of `/apps/FrontEnd`. Your job is purely the User Experience (UX) layer.
