# AryaBhatta Applications Setup & Run Guide

This directory contains the source code for the frontend and backend applications.

---

## Quick Start (Azure Functions)

### Prerequisites

1. **Azure Functions Core Tools** (v4.x) - [Install Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)
2. **Node.js** (v18+)
3. **Azure CLI** - logged in with `az login`

### Installation

```bash
# Frontend
cd FrontEnd
npm install

# Backend (Azure Functions)
cd ../functions
npm install
npx prisma generate
```

### Starting the Applications

You need **two terminals** running simultaneously:

#### Terminal 1: Azure Functions Backend

```bash
cd apps/functions
npm start
```

This will:
1. Compile TypeScript (`npm run build`)
2. Start the Azure Functions runtime on `http://localhost:7071`

**Available Endpoints:**
| Method | Endpoint |
|--------|----------|
| POST | `http://localhost:7071/api/auth/login` |
| GET | `http://localhost:7071/api/user/resume` |
| GET | `http://localhost:7071/api/practice/dashboard` |
| GET | `http://localhost:7071/api/practice/question` |
| POST | `http://localhost:7071/api/practice/progress` |

#### Terminal 2: Frontend (React/Vite)

```bash
cd apps/FrontEnd
npm run dev
```

Opens at `http://localhost:5173`

### Troubleshooting

- **Port 7071 already in use:** Kill the process or use `func start --port 7072`
- **Database timeout:** Add your IP to Azure PostgreSQL firewall (Azure Portal → PostgreSQL → Networking)
- **CORS errors:** Ensure the Functions host is running before starting the frontend

---

## Legacy Setup (Express Server - Deprecated)

> **Note:** The Express server in `apps/server` has been migrated to Azure Functions in `apps/functions`. The instructions below are kept for reference only.

## Prerequisites

Before starting, ensure you have installed the dependencies for both applications.

1.  **Frontend:**
    ```bash
    cd FrontEnd
    npm install
    ```

2.  **Backend:**
    ```bash
    cd server
    npm install
    ```

## Starting the Applications (Legacy)

You will need two separate terminal instances to run both the frontend and backend simultaneously.

### 1. Frontend Application

*   **Directory:** `apps/FrontEnd`
*   **Command:**
    ```bash
    cd FrontEnd
    npm run dev
    ```
    *   This starts the Vite development server (typically at `http://localhost:5173`).

### 2. Backend Server (Express - Deprecated)

*   **Directory:** `apps/server`
*   **Command:**
    ```bash
    cd server
    npx ts-node src/index.ts
    ```
    *   *Note: Since there is no dedicated start script yet, we use `npx ts-node` to run the TypeScript entry point directly.*
    *   The server runs on port 3000 by default.
    *   **Environment Variables:** Ensure your `.env` file in `apps/server` is configured correctly, as the server checks for Azure Storage connectivity and requires database credentials on startup.
