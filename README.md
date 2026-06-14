# AryaBhatta

AryaBhatta is an AI-powered education app for Class 11–12 CBSE/JEE students. It combines a modern web frontend, an Azure Functions backend, data pipelines for NCERT/JEE content, and an AI-based handwritten-solution evaluation workflow.

## What this repository contains

This monorepo includes:

- **Frontend app** for student practice, dashboards, and feedback flows
- **Primary backend** built with **Azure Functions v4**
- **Supplementary and legacy backends** for older or support workflows
- **Content pipelines** for NCERT extraction and JEE paper collection
- **Database schema** definitions in both raw SQL and Prisma
- **Design artifacts** for architecture, branding, and wireframes

## High-level architecture

At a high level, the system works like this:

1. Content is extracted and prepared using Python pipelines.
2. The frontend serves practice questions and collects student work.
3. The Azure Functions backend handles API requests and database access.
4. Student handwritten answers are uploaded to Azure Blob Storage.
5. An async AI evaluation pipeline processes submissions and stores structured feedback.
6. The frontend displays generated solutions, progress, and feedback to students.

## Repository structure

```text
AryaBhatta/
├── apps/
│   ├── FrontEnd/          # React 18 + TypeScript + Vite frontend
│   ├── functions/         # Primary backend: Azure Functions v4
│   ├── server/            # Legacy Express backend (deprecated)
│   └── backend/           # Supplementary backend utilities
├── pipelines/
│   ├── ExtractionPipeline/SchoolDataExtraction/MultiStep/
│   │                      # Python NCERT extraction pipeline
│   ├── DataCollection/    # JEE paper collection/downloader utilities
│   └── AzureFunctions/    # Durable/async evaluation pipeline components
├── Design/                # Architecture, branding, and wireframes
├── Scripts/
│   └── DB_Master.sql      # Source-of-truth PostgreSQL schema
└── apps/functions/prisma/
    └── schema.prisma      # Source-of-truth Prisma ORM schema
```

## Main application areas

### `apps/FrontEnd/`
Student-facing web application built with React, TypeScript, and Vite.

Typical responsibilities:
- Practice dashboards
- Question solving flows
- Feedback and evaluation views
- State management and routing

### `apps/functions/`
Primary backend application.

This is the main API surface for the product and contains:
- Azure Functions endpoints
- Prisma-based database access
- Azure Blob Storage helpers
- Evaluation submission and retrieval flows

### `apps/server/`
Legacy Express backend kept for older code paths.

> New backend work should generally go into `apps/functions/` instead.

### `apps/backend/`
Supplementary backend utilities and supporting logic.

### `pipelines/`
Offline and asynchronous processing workflows, including:
- NCERT data extraction
- JEE paper collection
- Durable evaluation pipeline orchestration

### `Scripts/`
Operational and database scripts, including the master SQL schema.

### `Design/`
Product design and architecture references.

## Backend API overview

The Azure Functions app exposes endpoints for:

- Authentication bootstrap/login flow
- User resume/progress
- Practice dashboard data
- Practice question delivery
- Practice progress updates
- Evaluation submission
- Evaluation history and detail retrieval
- Chapter/exercise question mapping

## Data model overview

The application stores:

- **Chapter and exercise metadata**
- **Question content and solutions** (often JSONB)
- **User profiles and progress**
- **Exercise attempt history**
- **AI evaluation jobs and feedback artifacts**

Primary schema sources:
- `apps/functions/prisma/schema.prisma` for Prisma models
- `Scripts/DB_Master.sql` for raw PostgreSQL schema

## Tech stack

- **Frontend:** React 18, TypeScript, Vite, TailwindCSS, Zustand
- **Backend:** Azure Functions v4 (Node.js/TypeScript)
- **Database:** PostgreSQL
- **ORM:** Prisma
- **Storage/Queue:** Azure Blob Storage, Azure Storage Queue
- **AI:** Google Gemini models
- **Pipelines:** Python

## Development notes

- Prefer **Azure Functions** under `apps/functions/` for backend changes.
- Treat `apps/server/` as legacy unless there is a specific reason to touch it.
- Use Prisma schema and SQL schema together to understand the data model.
- Expect both online request/response code and offline pipeline code in this repository.

## Who this repo is for

This repository is useful for contributors working on:
- Student practice and feedback experiences
- AI-assisted evaluation workflows
- Educational content ingestion pipelines
- Backend APIs and data models
- Operational tooling for the AryaBhatta platform