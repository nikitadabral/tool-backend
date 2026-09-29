# Request Triage API

FastAPI backend for the Request Triage application. It provides JWT
authentication, requester and reviewer workflows, SQLite persistence, and a
provider boundary for structured brief generation.

## Prerequisites

- Python 3.10 or newer

## Setup

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The API works with its development defaults and does not require an environment
file. To override them, create `.env` in this directory:

```dotenv
DEBUG=true
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
DATABASE_URL=sqlite:///./app.db
JWT_SECRET=replace-this-for-any-shared-environment
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
OPENAI_API_KEY=
```

Start the server on the frontend's default API port:

```bash
uvicorn app.main:app --reload --port 8010
```

The application creates `app.db` and its tables on startup.

- API documentation: http://localhost:8010/docs
- OpenAPI schema: http://localhost:8010/openapi.json
- Health check: http://localhost:8010/health

## API Overview

| Method | Path | Access |
| --- | --- | --- |
| `POST` | `/api/auth/signup` | Public |
| `POST` | `/api/auth/login` | Public |
| `POST` | `/api/auth/logout` | Authenticated |
| `GET` | `/api/auth/me` | Authenticated |
| `POST` | `/api/requests` | Authenticated |
| `GET` | `/api/requests/mine` | Authenticated |
| `GET` | `/api/requests` | Reviewer |
| `GET` | `/api/requests/{id}` | Authenticated |
| `POST` | `/api/requests/{id}/generate-brief` | Reviewer |
| `PATCH` | `/api/requests/{id}/triage` | Reviewer |

## Run Tests

Tests use a temporary in-memory SQLite database and do not modify `app.db`:

```bash
source .venv/bin/activate
pytest
```

To run one test module:

```bash
pytest tests/test_auth.py
pytest tests/test_intake.py
```

## Assumptions

- This service is a local-development MVP running as a single API instance.
- SQLite is sufficient for the expected development workload.
- Users choose either the requester or reviewer role during signup.
- Request content is intentionally persisted as one unstructured text field.
- Structured brief generation must be deterministic for now, so it does not
  require an external AI service or API key.

## Known Gaps

- `PlaceholderBriefProvider` generates keyword-based content rather than calling
  an LLM; `OPENAI_API_KEY` is currently unused.
- Schema updates rely on table creation and a small development-only column
  updater instead of a migration framework such as Alembic.
- JWT logout cannot revoke a token before it expires.
- Signup trusts the requested role. There is no administrator approval,
  external identity provider, email verification, or password reset.
- Any authenticated user can fetch any request by ID; requester ownership is not
  enforced on the detail endpoint.
- Production concerns such as rate limiting, managed secrets, observability,
  database pooling, and deployment configuration are not implemented.
