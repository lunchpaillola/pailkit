# PailKit API - Deployment Gameplan

## Goal
Get the API deployed to Fly.io with a secure, production-ready authentication model.

---

## 🔐 Authentication Architecture: "Bring Your Own Key" (BYOK)

### Why Header-Based Authentication?
The original plan to pass API keys in request bodies was **not secure or production-ready**. Here's the better approach:

**✅ Header-Based Provider Keys (Current Implementation)**
- Users pass provider API keys via `X-Provider-Auth` header
- Provider specified via `X-Provider` header (default: "daily")
- Keys never stored in database - lightweight and secure
- Works immediately without user management
- Aligns with your philosophy: "tools for builders" - they bring their own credentials

**Why This is Better:**
1. **Security**: API keys in headers (not request body) - less likely to be logged
2. **Standard Practice**: Matches how APIs like Stripe, Twilio work
3. **Multi-Provider Ready**: Add new providers without changing architecture
4. **Commercial Path**: Can evolve to PailKit-managed keys later (see below)

**Example API Call:**
```bash
# With explicit provider (recommended)
curl -X POST https://api.pailkit.com/api/rooms/create \
  -H "X-Provider-Auth: Bearer daily_abc123..." \
  -H "X-Provider: daily" \
  -H "Content-Type: application/json" \
  -d '{"profile": "conversation"}'

# Without provider header (defaults to "daily")
curl -X POST https://api.pailkit.com/api/rooms/create \
  -H "X-Provider-Auth: Bearer daily_abc123..." \
  -H "Content-Type: application/json" \
  -d '{"profile": "conversation"}'
```

---

## 📈 Evolution Path (Future Options)

### Phase 1: BYOK with Headers ✅ (Current)
- Users bring their own provider keys
- No user accounts, no database needed
- Perfect for open-source and early adopters
- **Status**: ✅ Implemented

### Phase 2: Optional PailKit API Keys (Later)
When you're ready to add user management:
- Users register and add provider keys once
- Get a PailKit API key
- Use `Authorization: Bearer pailkit_xxx` instead of provider keys
- Keys stored encrypted in database
- Same unified API - just different auth

### Phase 3: Fully Managed Service (Commercial)
- You provision provider accounts
- Users only need PailKit API key
- You handle billing/usage
- Users pay you, you pay providers
- More user-friendly, but requires infrastructure

**For now, Phase 1 gets you live TODAY with a secure, shareable API.**

---

## ✅ To-Do Checklist

### 1. ✅ Update Router for Header-Based Auth
**File updated**: `api/routers/rooms.py`

**What was done:**
- ✅ Removed hardcoded `daily_api_key = os.getenv("DAILY_API_KEY")` requirement
- ✅ Removed global `daily_provider` variable
- ✅ Removed `provider` field from `RoomCreateRequest` model (provider is header-only now)
- ✅ Added `X-Provider-Auth` header for provider API keys (required)
- ✅ Added `X-Provider` header for provider selection (optional, defaults to "daily")
- ✅ Updated `create_room()` to extract provider and API key from headers
- ✅ Updated `delete_room()` to extract provider and API key from headers
- ✅ Added `get_room()` endpoint with same auth pattern
- ✅ Updated `get_provider()` function:
  - Now accepts API key as parameter (not hardcoded)
  - Normalizes provider name to lowercase (case-insensitive matching)
- ✅ Provider name normalization: all provider names are lowercased for consistency

**How it works now:**
- **Provider selection**: Always from `X-Provider` header (never from request body)
  - If header omitted, defaults to "daily"
  - Case-insensitive: "Daily", "DAILY", "daily" all work
- **API key**: Always from `X-Provider-Auth` header (required)
  - Supports both `Bearer <key>` and raw key formats
- **Stateless design**: Provider instance created per-request with user's credentials
- **No environment variables**: Deployment doesn't need any provider keys
- **Consistent pattern**: All endpoints (create, get, delete) use same auth approach

**Key Design Decision:**
Provider is **header-only** (not in request body) to keep authentication and provider selection together in headers, following standard API practices.

---

### 1b. ✅ Clean Up Header Aliases (Code Simplification)

**What was done:**
- ✅ Removed unnecessary `alias` parameters from Header declarations
- ✅ FastAPI automatically converts `x_provider_auth` → `X-Provider-Auth` header
- ✅ FastAPI automatically converts `x_provider` → `X-Provider` header

**Files updated:**
- `api/routers/rooms.py` - Removed aliases from all three endpoints:
  - `create_room()` - Removed `alias="X-Provider-Auth"` and `alias="X-Provider"`
  - `delete_room()` - Removed `alias="X-Provider-Auth"` and `alias="X-Provider"`
  - `get_room()` - Removed `alias="X-Provider-Auth"` and `alias="X-Provider"`

**Before:**
```python
x_provider_auth: str = Header(..., alias="X-Provider-Auth", description="...")
x_provider: str = Header("daily", alias="X-Provider", description="...")
```

**After:**
```python
x_provider_auth: str = Header(..., description="...")
x_provider: str = Header("daily", description="...")
```

**Why this works:**
FastAPI's Header automatically converts underscores to hyphens, so aliases are redundant. This makes the code cleaner and follows the "less is more" principle!

**Status:** ✅ Complete - Tests pass without issues.

---

### 1c. ✅ Test Status

**Current Status:**
- ✅ All unit tests passing (mocked tests)
- ✅ Integration tests working correctly
- ✅ Integration tests properly read `DAILY_API_KEY` environment variable

**Integration Test Configuration:**
- Integration tests read `DAILY_API_KEY` from environment variables (via `os.getenv("DAILY_API_KEY")`)
- Tests correctly pass the key in the `X-Provider-Auth` header as `Bearer {daily_api_key}`
- Tests can be run with: `npm run test:integration` or `RUN_INTEGRATION_TESTS=true pytest`

**Test Command:**
```bash
# Run all tests (mocked)
npm run test

# Run integration tests (requires DAILY_API_KEY in .env)
npm run test:integration
```

**Note:** Integration tests require `DAILY_API_KEY` in your `.env` file (matching `env.example`). They skip gracefully if the key is not provided.

---

### 2. Test Profiles Work (Quick Check)
**Files to check**: `api/rooms/profiles.py`, `api/providers/rooms/daily.py`

**What to do:**
- [ ] Start the API: `cd api && uvicorn main:app --reload`
- [ ] Test creating a room with a real Daily.co API key:
  ```bash
  curl -X POST http://localhost:8000/api/rooms/create \
    -H "X-Provider-Auth: Bearer YOUR_DAILY_API_KEY" \
    -H "X-Provider: daily" \
    -H "Content-Type: application/json" \
    -d '{"profile": "conversation"}'
  ```
- [ ] Verify you get a room URL back
- [ ] Manually test "broadcast" profile works
- [ ] If RTMP doesn't work, that's okay - we'll fix later

---

### 3. Create Dockerfile
**File to create**: `api/Dockerfile`

**What it should contain:**
- [ ] Python 3.12 base image
- [ ] Copy requirements.txt and install dependencies
- [ ] Copy all code
- [ ] Run uvicorn to start the server
- [ ] **Note**: No DAILY_API_KEY environment variable needed!

**Example:**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### 4. Create fly.toml
**File to create**: `fly.toml` (in project root or api directory)

**What it should contain:**
- [ ] App name (e.g., "pailkit-api")
- [ ] Region (e.g., "iad" for Virginia)
- [ ] Port 8000 configuration
- [ ] Basic machine settings (shared-cpu-1x, 256MB RAM should be fine to start)

**Note**: No secrets needed! Users bring their own keys.

---

### 5. Create .dockerignore
**File to create**: `api/.dockerignore`

**What to ignore:**
- [ ] `__pycache__` folders
- [ ] `venv` folder
- [ ] `.env` files
- [ ] Python cache files
- [ ] `*.pyc` files

---

### 6. Deploy to Fly.io
**Commands to run:**
- [ ] `cd api`
- [ ] `fly launch` (follow the prompts)
  - Enter app name when prompted
  - Select region
  - Don't deploy yet
- [ ] Review the generated `fly.toml`
- [ ] `fly deploy`
- [ ] Copy the URL it gives you (e.g., `https://pailkit-api.fly.dev`)

---

### 7. Test It Works
**What to test:**
- [ ] Visit `https://your-app.fly.dev/health` - should see `{"status": "healthy"}`
- [ ] Visit `https://your-app.fly.dev/docs` - should see Swagger docs
- [ ] Test creating a room with a real Daily.co API key:
  ```bash
  curl -X POST https://your-app.fly.dev/api/rooms/create \
    -H "X-Provider-Auth: Bearer YOUR_DAILY_API_KEY" \
    -H "X-Provider: daily" \
    -H "Content-Type: application/json" \
    -d '{"profile": "conversation"}'
  ```
- [ ] Verify you get a room URL back
- [ ] Test the `/api/rooms/get/{room_name}` endpoint
- [ ] Test the `/api/rooms/delete/{room_name}` endpoint

---

## 🎉 Done!

Once all checkboxes are checked, you're live with a secure, shareable API!

**What you've built:**
- ✅ Secure header-based authentication
- ✅ Multi-provider architecture ready
- ✅ No key storage required
- ✅ Production-ready deployment
- ✅ Works with your philosophy: builders bring their own tools

---

## 🔮 Later (Not Today)

### Short-term Enhancements:
- Write more tests
- Add better logging (don't log API keys!)
- Fix RTMP if needed
- Add rate limiting (protect your infrastructure)
- Add usage analytics (optional, for insights)

### Medium-term Evolution:
- Add more providers (Zoom, Twilio, etc.)
- Implement Phase 2: Optional PailKit API keys (user accounts)
- Add API key rotation/management UI
- Add webhook support for room events

### Commercial Path:
- If you want to go fully managed (Phase 3):
  - Add user registration/auth
  - Add provider key management
  - Add billing/usage tracking
  - Provision master provider accounts
  - Handle cost allocation

**But for now, the BYOK model lets you ship TODAY and share freely.** 🚀

---

## 📝 Key Architectural Decisions

**Why not environment variables for provider keys?**
- Doesn't scale - can't have one key per user
- Users would need their own deployments
- Not compatible with multi-tenant SaaS model

**Why not request body for provider/key?**
- Keys would be logged in request bodies
- Provider selection mixed with business logic (profile, overrides)
- Not standard practice - auth should be in headers
- Harder to audit/secure
- Inconsistent with REST API best practices

**Why headers?**
- Standard practice (Stripe, Twilio, AWS all use headers)
- Less likely to be logged accidentally
- Easy to add middleware/rate limiting later
- Works with existing API client libraries

**Why BYOK instead of managed?**
- Ships faster (no user management needed)
- Users control their own costs
- No billing infrastructure required
- Perfect for open-source/sharing
- Can evolve to managed later without breaking changes

---

## 🛠️ Example: Using the API

**Create a conversation room (with explicit provider):**
```bash
curl -X POST https://api.pailkit.com/api/rooms/create \
  -H "X-Provider-Auth: Bearer daily_abc123xyz" \
  -H "X-Provider: daily" \
  -H "Content-Type: application/json" \
  -d '{"profile": "conversation"}'
```

**Create a conversation room (provider defaults to "daily"):**
```bash
curl -X POST https://api.pailkit.com/api/rooms/create \
  -H "X-Provider-Auth: Bearer daily_abc123xyz" \
  -H "Content-Type: application/json" \
  -d '{"profile": "conversation"}'
```

**Note:** Provider name is case-insensitive - "Daily", "DAILY", or "daily" all work.

**Create a broadcast room with overrides:**
```bash
curl -X POST https://api.pailkit.com/api/rooms/create \
  -H "X-Provider-Auth: Bearer daily_abc123xyz" \
  -H "X-Provider: daily" \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "broadcast",
    "overrides": {
      "capabilities": {
        "chat": false
      }
    }
  }'
```

**Get room details:**
```bash
curl -X GET https://api.pailkit.com/api/rooms/get/room-name-here \
  -H "X-Provider-Auth: Bearer daily_abc123xyz" \
  -H "X-Provider: daily"
```

**Delete a room:**
```bash
curl -X DELETE https://api.pailkit.com/api/rooms/delete/room-name-here \
  -H "X-Provider-Auth: Bearer daily_abc123xyz" \
  -H "X-Provider: daily"
```

---

## 🚨 Security Best Practices

**For Users:**
- Never commit API keys to git
- Rotate keys regularly
- Use environment variables or secret managers in production
- Monitor usage through provider dashboards

**For You (PailKit):**
- Never log `X-Provider-Auth` headers
- Add rate limiting to prevent abuse
- Consider adding request signing later
- Document security practices clearly

---

**Ready to deploy? Let's ship it! 🚀**
