# Invite Code Admin Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow admins to create, modify, and delete (rotate) invite codes from the dashboard while keeping first-user registration invite-free.

**Architecture:** Add dedicated invite-code APIs in config routes and corresponding config-manager helpers. Surface invite-code controls in dashboard settings with explicit actions (save and rotate). Preserve secure registration behavior: first user can register without invite; subsequent users require invite.

**Tech Stack:** FastAPI, Jinja2 template + vanilla JS (Axios), Python config manager, Docker Compose runtime.

---

### Task 1: Backend Invite API + Config Manager Support

**Files:**
- Modify: `rss/app/core/config_manager.py`
- Modify: `rss/app/routes/config.py`
- Test: `python3 -m py_compile rss/app/core/config_manager.py rss/app/routes/config.py`

**Step 1: Write failing behavior expectation**
- Admin currently cannot manage invite code via API.

**Step 2: Verify absence of endpoint behavior**
- Run: `curl -i http://127.0.0.1:1010/api/config/invite-code`
- Expected before implementation: non-200 or missing route.

**Step 3: Implement minimal API + helpers**
- Add `set_invite_code`, `rotate_invite_code` helpers.
- Add `GET /api/config/invite-code`, `PATCH /api/config/invite-code`, `POST /api/config/invite-code/rotate` with auth.
- Ensure rotate generates a new random code.

**Step 4: Verify syntax and endpoint existence**
- Run: `python3 -m py_compile rss/app/core/config_manager.py rss/app/routes/config.py`
- Run: `curl -s http://127.0.0.1:1010/api/config/invite-code` with auth (later integrated in UI validation).

### Task 2: Dashboard UI Invite Management

**Files:**
- Modify: `rss/app/templates/rss_dashboard.html`
- Test: browser/API smoke + UI-triggered requests

**Step 1: Add settings controls**
- Add invite-code input and action buttons in settings modal.

**Step 2: Hook API calls**
- Load invite code in settings initialization.
- Save custom invite code via PATCH endpoint.
- Rotate invite code via POST endpoint with confirmation.

**Step 3: Verify expected UX**
- Save shows success toast and refreshes current value.
- Rotate replaces value and shows success toast.

### Task 3: Registration UX Alignment

**Files:**
- Modify: `rss/app/templates/register.html`
- Test: first-user registration without invite in UI

**Step 1: Remove forced invite requirement on form input**
- Drop `required` on invite input and update placeholder/hint.

**Step 2: Keep API behavior unchanged**
- First user no invite required, later users still require invite (already in backend).

**Step 3: Verify flow**
- Ensure form can submit with empty invite value.

### Task 4: Verification and Runtime Check

**Files:**
- N/A (command verification)

**Step 1: Run syntax checks**
- `python3 -m py_compile rss/app/routes/auth.py rss/app/routes/config.py rss/app/core/config_manager.py`

**Step 2: Rebuild + restart container**
- `docker compose up -d --build`

**Step 3: Verify routes and auth guard**
- Unauthenticated invite APIs should return 401.
- Authenticated dashboard loads and can edit/rotate invite code.

