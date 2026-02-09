# Migration Plan: Node.js Middleware to Azure Functions v4

## Overview

This document outlines the migration strategy for moving the Express-based middleware in [apps/server/src/routes/api.ts](apps/server/src/routes/api.ts) to Azure Functions v4 in `apps/functions`.

---

## Current Architecture Analysis

### Existing Express Routes in `api.ts`

| Route | Method | Purpose |
|-------|--------|---------|
| `/auth/login` | POST | User authentication/session initialization |
| `/user/resume` | GET | Fetch last attempted question for resume functionality |
| `/practice/dashboard` | GET | Get dashboard data (classes, subjects, chapters) |
| `/practice/question` | GET | Fetch question content with SAS token injection |
| `/practice/progress` | POST | Save user progress |

### Key Dependencies
- **Prisma Client** - Database operations
- **Azure Storage SDK** - SAS token generation for blob URLs
- **Session Configuration** - Hardcoded `sessionUser` object

### Response Pattern (Express)
```typescript
res.json({ data }); // Success
res.status(400).json({ error: 'message' }); // Error
```

---

## Target Architecture

### Azure Functions v4 Structure

```
apps/functions/
├── src/
│   ├── functions/
│   │   ├── authLogin.ts
│   │   ├── userResume.ts
│   │   ├── practiceDashboard.ts
│   │   ├── practiceQuestion.ts
│   │   └── practiceProgress.ts
│   ├── utils/
│   │   ├── prisma.ts          # Already created
│   │   ├── azure-storage.ts   # Port from server
│   │   └── session.config.ts  # Port from server
│   └── types/
│       └── index.ts           # Shared TypeScript interfaces
├── host.json
├── local.settings.json
├── package.json
└── tsconfig.json
```

---

## Migration Steps

### Phase 1: Project Setup

1. **Initialize Azure Functions Project**
   - Create `apps/functions` directory
   - Initialize with `func init --typescript --model V4`
   - Configure `host.json` for HTTP triggers with custom routes

2. **Configure TypeScript**
   - Ensure `tsconfig.json` targets ES2020+
   - Enable strict mode for type safety
   - Configure path aliases if needed

3. **Install Dependencies**
   - `@azure/functions` (v4)
   - `@prisma/client` + `prisma`
   - `@azure/storage-blob`
   - `@azure/identity`

4. **Copy & Adapt Shared Utilities**
   - Port `azure-storage.ts` (SAS token generation)
   - Port `session.config.ts` (temporary hardcoded user)
   - Verify `prisma.ts` utility works with Prisma 7

### Phase 2: Response Model Transformation

**Express Response → Azure Functions v4 HttpResponseInit**

| Express Pattern | Azure Functions v4 Pattern |
|-----------------|---------------------------|
| `res.json(data)` | `return { jsonBody: data }` |
| `res.status(400).json({ error })` | `return { status: 400, jsonBody: { error } }` |
| `res.status(500).json({ error })` | `return { status: 500, jsonBody: { error } }` |

**Key Differences:**
- Express mutates `res` object; Azure Functions returns `HttpResponseInit`
- No `next()` middleware pattern; each function is self-contained
- Query params accessed via `request.query.get('param')` instead of `req.query.param`
- Body accessed via `await request.json()` instead of `req.body`

### Phase 3: Route-by-Route Migration

#### 3.1 `authLogin.ts`
- **Trigger**: HTTP POST `/api/auth/login`
- **Logic**: 
  - Query `userprofiledata` using Prisma
  - Return user profile or fallback session info
- **Response Mapping**:
  - Success: `{ jsonBody: { userId, userName, ... } }`
  - Error: `{ status: 500, jsonBody: { error: 'message' } }`

#### 3.2 `userResume.ts`
- **Trigger**: HTTP GET `/api/user/resume`
- **Logic**:
  - Query `userexercisedata` with `chapterdata` include
  - Return last attempt or null
- **Response Mapping**:
  - No data: `{ jsonBody: null }`
  - Success: `{ jsonBody: { chapterId, questionId, ... } }`

#### 3.3 `practiceDashboard.ts`
- **Trigger**: HTTP GET `/api/practice/dashboard`
- **Logic**:
  - Complex multi-query flow for classes, subjects, chapters
  - Query params: `class`, `subject`, `board`
- **Query Param Access**:
  ```typescript
  const queryClass = request.query.get('class');
  ```
- **Response Mapping**:
  - Success: `{ jsonBody: { supportedClasses, chapters, ... } }`

#### 3.4 `practiceQuestion.ts`
- **Trigger**: HTTP GET `/api/practice/question`
- **Logic**:
  - Mode-based question fetching (start/resume)
  - SAS token injection for blob URLs
  - Next/prev question calculation
- **Critical**: Port `generateSasUrl` utility
- **Response Mapping**:
  - Not found: `{ status: 404, jsonBody: { error: 'message' } }`
  - Success: `{ jsonBody: { questionId, content, ... } }`

#### 3.5 `practiceProgress.ts`
- **Trigger**: HTTP POST `/api/practice/progress`
- **Logic**:
  - Parse JSON body: `await request.json()`
  - Create `userexercisedata` record
- **Body Access**:
  ```typescript
  const { chapterId, exerciseId, questionId } = await request.json() as ProgressPayload;
  ```
- **Response Mapping**:
  - Success: `{ jsonBody: { success: true, entryId } }`

### Phase 4: Shared Utilities

#### 4.1 Prisma Client Singleton
- Already created at `src/utils/prisma.ts`
- Ensure connection pooling is appropriate for serverless (use `connection_limit=1` or PgBouncer)
- Handle cold start implications

#### 4.2 Azure Storage Utility
- Port `generateSasUrl` function from [apps/server/src/utils/azure-storage.ts](apps/server/src/utils/azure-storage.ts)
- Adapt initialization for serverless (lazy load credentials)
- Handle both Shared Key and Managed Identity auth

#### 4.3 Session Configuration
- Port `sessionUser` from [apps/server/src/config/session.config.ts](apps/server/src/config/) (path inferred)
- **Future**: Replace with proper auth (Azure AD B2C, Auth0, etc.)

### Phase 5: Configuration

#### 5.1 `host.json`
```json
{
  "version": "2.0",
  "extensions": {
    "http": {
      "routePrefix": "api"
    }
  }
}
```

#### 5.2 `local.settings.json`
```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "",
    "FUNCTIONS_WORKER_RUNTIME": "node",
    "DATABASE_URL": "...",
    "AZURE_STORAGE_ACCOUNT_NAME": "...",
    "AZURE_STORAGE_KEY": "..."
  }
}
```

#### 5.3 Route Registration (v4 Model)
Each function self-registers via `app.http()`:
```typescript
import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";

app.http('authLogin', {
    methods: ['POST'],
    authLevel: 'anonymous', // or 'function' for key-based
    route: 'auth/login',
    handler: authLoginHandler
});
```

### Phase 6: Testing Strategy

1. **Local Testing**
   - Use Azure Functions Core Tools (`func start`)
   - Test with same curl/Postman commands used for Express

2. **Integration Testing**
   - Verify Prisma queries return expected data
   - Verify SAS tokens are generated correctly
   - Test cold start behavior

3. **Frontend Compatibility**
   - Update [apps/FrontEnd/src/lib/api.ts](apps/FrontEnd/src/lib/api.ts) `baseURL` to point to Functions endpoint
   - Verify all API calls work unchanged (same request/response shapes)

### Phase 7: Deployment

1. **Azure Resources**
   - Create Function App (Node.js 20 LTS, Consumption Plan)
   - Configure Application Settings (env vars)
   - Enable Managed Identity for Key Vault/Storage access

2. **CI/CD**
   - Add GitHub Actions workflow for `apps/functions`
   - Deploy on push to main branch

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Cold start latency | Use Premium Plan or keep-warm pings; optimize imports |
| Prisma connection limits | Use `connection_limit=1` in DATABASE_URL; consider PgBouncer |
| SAS token errors | Cache credentials; handle auth failures gracefully |
| Breaking frontend | Maintain exact same response shapes; test thoroughly |

---

## Success Criteria

- [ ] All 5 routes migrated and functional
- [ ] Frontend works without code changes (only baseURL update)
- [ ] Local development workflow documented
- [ ] Response times comparable to Express server
- [ ] Error handling consistent with original implementation

---

## Timeline Estimate

| Phase | Duration |
|-------|----------|
| Phase 1: Setup | 1-2 hours |
| Phase 2-3: Migration | 4-6 hours |
| Phase 4-5: Utilities & Config | 2-3 hours |
| Phase 6-7: Testing & Deploy | 2-4 hours |
| **Total** | **9-15 hours** |

---

## Next Steps

1. Review this plan and confirm approach
2. Initialize Azure Functions project in `apps/functions`
3. Begin Phase 1 setup
4. Migrate routes one-by-one, testing after each
