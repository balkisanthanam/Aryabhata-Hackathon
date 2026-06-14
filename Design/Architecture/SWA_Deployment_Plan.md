# Azure Static Web App Deployment Plan

## Overview

Deploy Aryabhata's React frontend + Azure Functions API to Azure Static Web Apps (SWA).

| Component | Source | Destination |
|-----------|--------|-------------|
| Frontend | `apps/FrontEnd` | Azure SWA (CDN-backed) |
| API | `apps/functions` | SWA Managed Functions |

---

## Prerequisites Checklist

- [ ] GitHub repository with code pushed
- [ ] Azure subscription active
- [ ] Azure CLI installed and logged in (`az login`)
- [ ] Repository URL: `https://github.com/<your-username>/AryaBhatta`

---

## Step 1: Prepare Repository

### 1.1 Ensure Code is Pushed to GitHub

```bash
cd C:\Bala\Coding\AryaBhatta
git add .
git commit -m "Migrate server to Azure Functions"
git push origin main
```

### 1.2 Create Production Environment File

Before deploying, create `apps/FrontEnd/.env.production`:

```env
VITE_API_BASE_URL=/api
```

> **Note:** In SWA, the managed Functions API is automatically available at `/api/*` (same origin), so no full URL needed.

---

## Step 2: Create Static Web App in Azure Portal

### 2.1 Navigate to Azure Portal

1. Go to [https://portal.azure.com](https://portal.azure.com)
2. Click **"+ Create a resource"**
3. Search for **"Static Web App"**
4. Click **Create**

### 2.2 Fill in Basic Settings

| Field | Value |
|-------|-------|
| **Subscription** | Your subscription |
| **Resource Group** | Create new: `rg-aryabhata-prod` (or use existing) |
| **Name** | `swa-aryabhata` (must be globally unique) |
| **Plan Type** | `Free` (for testing) or `Standard` (for production) |
| **Region** | `Central India` or nearest to your users |
| **Source** | `GitHub` |

### 2.3 Connect GitHub Account

1. Click **"Sign in with GitHub"**
2. Authorize Azure to access your GitHub account
3. Select:
   - **Organization:** Your GitHub username/org
   - **Repository:** `AryaBhatta`
   - **Branch:** `main`

### 2.4 Build Configuration

| Field | Value |
|-------|-------|
| **Build Presets** | `React` |
| **App location** | `apps/FrontEnd` |
| **Api location** | `apps/functions` |
| **Output location** | `dist` |

### 2.5 Review and Create

1. Click **"Review + create"**
2. Review the settings
3. Click **"Create"**

Azure will:
- Create the SWA resource
- Add a GitHub Actions workflow file to your repo
- Trigger the first deployment

---

## Step 3: Configure GitHub Actions Workflow

Azure auto-generates `.github/workflows/azure-static-web-apps-<random>.yml`. We need to modify it for our Prisma setup.

### 3.1 Expected Workflow Structure

```yaml
name: Azure Static Web Apps CI/CD

on:
  push:
    branches:
      - main
  pull_request:
    types: [opened, synchronize, reopened, closed]
    branches:
      - main

jobs:
  build_and_deploy_job:
    if: github.event_name == 'push' || (github.event_name == 'pull_request' && github.event.action != 'closed')
    runs-on: ubuntu-latest
    name: Build and Deploy Job
    steps:
      - uses: actions/checkout@v3
        with:
          submodules: true
          lfs: false

      # ADD THIS STEP for Prisma
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      # ADD THIS STEP for Prisma generate in Functions
      - name: Install and Generate Prisma Client
        run: |
          cd apps/functions
          npm ci
          npx prisma generate

      - name: Build And Deploy
        id: builddeploy
        uses: Azure/static-web-apps-deploy@v1
        with:
          azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN_<NAME> }}
          repo_token: ${{ github.token }}
          action: "upload"
          app_location: "apps/FrontEnd"
          api_location: "apps/functions"
          output_location: "dist"
        env:
          # Frontend build environment
          VITE_API_BASE_URL: "/api"

  close_pull_request_job:
    if: github.event_name == 'pull_request' && github.event.action == 'closed'
    runs-on: ubuntu-latest
    name: Close Pull Request Job
    steps:
      - name: Close Pull Request
        id: closepullrequest
        uses: Azure/static-web-apps-deploy@v1
        with:
          azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN_<NAME> }}
          action: "close"
```

### 3.2 Key Modifications Needed

1. **Add Prisma generate step** before the deploy action
2. **Set `VITE_API_BASE_URL`** environment variable for frontend build
3. **Ensure Node 20** is used (for Prisma 7 compatibility)

---

## Step 4: Configure Application Settings (Environment Variables)

After SWA is created, add database credentials:

### 4.1 Navigate to Configuration

1. Go to your SWA resource in Azure Portal
2. Click **"Configuration"** in the left menu
3. Click **"+ Add"** for each variable

### 4.2 Add Application Settings

| Name | Value |
|------|-------|
| `DB_USER` | `<DB_USER>` |
| `DB_HOST` | `<DB_HOST>` |
| `DB_NAME` | `<DB_NAME>` |
| `DB_PORT` | `5432` |
| `AZURE_STORAGE_ACCOUNT_NAME` | `<AZURE_STORAGE_ACCOUNT_NAME>` |
| `AZURE_STORAGE_KEY` | `<AZURE_STORAGE_KEY>` |

Click **"Save"** after adding all variables.

---

## Step 5: Configure Database Access

### 5.1 Allow Azure SWA to Access PostgreSQL

SWA managed functions use **outbound IPs** that change. Options:

**Option A: Allow Azure Services (Recommended for testing)**
1. Go to Azure Portal → `<DB_SERVER_NAME>` PostgreSQL
2. Click **"Networking"**
3. Enable **"Allow public access from any Azure service within Azure to this server"**
4. Click **Save**

**Option B: Use Private Endpoint (Recommended for production)**
- Requires Standard SWA plan
- More secure but complex setup

---

## Step 6: Update CORS for Production

### 6.1 Modify `apps/functions/src/utils/cors.ts`

Update allowed origins to include production URL:

```typescript
export const corsHeaders = {
    'Access-Control-Allow-Origin': '*', // Or specific: 'https://swa-aryabhata.azurestaticapps.net'
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400'
};
```

> **Note:** In SWA, the API runs on the same domain, so CORS is often not needed. But we keep it for flexibility.

---

## Step 7: Create Production Environment File

### 7.1 Create `apps/FrontEnd/.env.production`

```env
VITE_API_BASE_URL=/api
```

This tells the frontend to use relative URLs in production (SWA serves API at `/api/*`).

---

## Step 8: Commit and Deploy

```bash
git add .
git commit -m "Configure for Azure SWA deployment"
git push origin main
```

GitHub Actions will automatically:
1. Build the React frontend
2. Generate Prisma client
3. Deploy frontend to SWA CDN
4. Deploy functions to managed API

---

## Step 9: Verify Deployment

### 9.1 Check GitHub Actions

1. Go to your GitHub repo
2. Click **"Actions"** tab
3. Watch the workflow run
4. Check for any errors

### 9.2 Access Your App

After successful deployment:

- **Frontend:** `https://swa-aryabhata.azurestaticapps.net`
- **API:** `https://swa-aryabhata.azurestaticapps.net/api/practice/dashboard`

### 9.3 Test Endpoints

```bash
# Test login
curl -X POST https://swa-aryabhata.azurestaticapps.net/api/auth/login

# Test dashboard
curl https://swa-aryabhata.azurestaticapps.net/api/practice/dashboard
```

---

## Troubleshooting

### Build Fails: "Cannot find module '@prisma/client'"

**Solution:** Ensure the Prisma generate step is added to the workflow before the deploy action.

### API Returns 500: Database Connection Error

**Solution:**
1. Check Application Settings are correctly set
2. Verify PostgreSQL firewall allows Azure services
3. Check Azure AD authentication is working

### Frontend Shows Blank Page

**Solution:**
1. Check browser console for errors
2. Verify `VITE_API_BASE_URL` is set correctly during build
3. Check the `dist` folder structure in GitHub Actions logs

### CORS Errors

**Solution:** In SWA, API is same-origin. If you still see CORS errors:
1. Clear browser cache
2. Ensure you're accessing via the SWA URL (not localhost)

---

## Post-Deployment Checklist

- [ ] App loads at `https://swa-aryabhata.azurestaticapps.net`
- [ ] Login shows "Viswanathan" (not "Guest User")
- [ ] Practice dashboard loads chapters
- [ ] Questions load with images (SAS tokens working)
- [ ] Progress saves correctly

---

## Optional: Custom Domain

To add a custom domain (e.g., `app.aryabhata.com`):

1. Go to SWA resource → **"Custom domains"**
2. Click **"+ Add"**
3. Enter your domain
4. Add the CNAME/TXT record to your DNS
5. Wait for validation (can take up to 24 hours)

---

## Cost Estimate

| Resource | Plan | Cost |
|----------|------|------|
| Static Web App | Free | $0/month |
| Static Web App | Standard | ~$9/month |
| PostgreSQL | Already exists | Existing cost |
| Storage | Already exists | Existing cost |

---

## Summary

| Step | Action |
|------|--------|
| 1 | Push code to GitHub |
| 2 | Create SWA in Azure Portal with GitHub integration |
| 3 | Modify auto-generated workflow for Prisma |
| 4 | Add environment variables in SWA Configuration |
| 5 | Allow Azure services in PostgreSQL firewall |
| 6 | Commit `.env.production` and workflow changes |
| 7 | Verify deployment |

**Estimated Time:** 30-45 minutes
