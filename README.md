# Request Triage API

FastAPI backend for the Request Triage application. It provides JWT
authentication, requester and reviewer workflows, SQLite persistence, and a
provider boundary for structured brief generation.

## 1. Setup Instructions

### Prerequisites

- Python 3.10 or newer

### Install dependencies

From `backend/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Configure the environment

The API runs with development defaults and does not require an environment
file. For any shared environment, create `backend/.env` and replace the default
JWT secret:

```dotenv
JWT_SECRET=replace-with-a-long-random-secret
```

To demonstrate webhook delivery when a request is approved, also add:

```dotenv
OUTBOUND_WEBHOOK_URL=https://your-webhook-url
OUTBOUND_WEBHOOK_SECRET=optional-secret
```

Omit both webhook settings when the integration is not needed.

Optional overrides include `CORS_ORIGINS`, `DATABASE_URL`,
`ACCESS_TOKEN_EXPIRE_MINUTES`, `OUTBOUND_WEBHOOK_URL`,
`OUTBOUND_WEBHOOK_SECRET`, and `OUTBOUND_WEBHOOK_TIMEOUT_SECONDS`.

### Run the API

```bash
uvicorn app.main:app --reload --port 8010
```

Open <http://localhost:8010/docs> for the interactive API documentation. The
application creates the SQLite database and tables automatically on startup.

## 2. Assumptions

- The API is a local-development MVP running as a single instance.
- SQLite is sufficient for local development.
- Users choose either the requester or reviewer role during signup.
- Request content is stored as a single text field.
- Brief generation uses a deterministic mock AI provider and does not call a
  paid or external LLM service.

## 3. Known Gaps

- Brief generation uses a placeholder provider instead of a live AI service.
- Database migrations are not managed with a migration framework.
- Authentication does not include token revocation, email verification, or
  password reset.
- Production deployment, rate limiting, and observability are not configured.

## 4. How to Run Tests

Tests use a temporary in-memory SQLite database and do not modify `app.db`.
The suite covers API, authentication, validation, database persistence, and
brief-generation workflow and output-shape validation.

From the project root, run:

```bash
cd backend
source .venv/bin/activate
pytest
```

To run a specific test module:

```bash
pytest tests/test_auth.py
```

Automated webhook tests provide isolated test configuration and do not require
webhook values in `.env`. Run them with:

```bash
pytest tests/test_webhook.py tests/test_intake.py::test_approval_queues_configured_external_handoff
```

For a manual webhook test, set `OUTBOUND_WEBHOOK_URL` and optionally
`OUTBOUND_WEBHOOK_SECRET` in `.env`, restart the API, and approve a request.

### Run data-quality checks

To evaluate generated brief quality against the fixed sample dataset, run from
`backend/`:

```bash
source .venv/bin/activate
python -m evaluation.evaluate_briefs
```

To run the automated evaluation tests:

```bash
pytest tests/test_evaluation.py -v
```
