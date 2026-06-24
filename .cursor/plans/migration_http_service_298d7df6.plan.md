---
name: Migration HTTP Service
overview: Greenfield Python HTTP service (single authenticated endpoint) that downloads a FileMaker clone from S3, copies it into an FMS container via the Docker socket, and runs a stubbed `docker exec` step you will define later. Fully dockerized with Compose Watch on a `develop` build target. Only one migration may run at a time; concurrent requests are rejected.
todos:
  - id: scaffold
    content: "Create project skeleton: requirements.txt, .gitignore, .env.example, src/ package"
    status: pending
  - id: config-auth
    content: Implement config.py (pydantic-settings) and auth.py (Bearer validation)
    status: pending
  - id: pipeline
    content: "Implement pipeline.py: aws s3 cp → docker cp → stub docker exec"
    status: pending
  - id: aws-iam-readme
    content: "Write docs/aws-iam.md — IAM user/role setup and least-privilege S3 policy (ListBucket + GetObject)"
    status: pending
  - id: api
    content: Implement main.py with GET /health, POST /authenticate, and migration-in-progress guard
    status: pending
  - id: docker
    content: Write Dockerfile (base/develop/production) with AWS CLI + docker CLI
    status: pending
  - id: compose
    content: Write compose.yml with docker.sock mount, staging volume, develop watch
    status: pending
isProject: false
---

# Migration HTTP Service Plan

Prompt log: [prompts/migration_http_service_298d7df6.md](./prompts/migration_http_service_298d7df6.md)

Greenfield project — only [prompt.md](prompt.md) and Cursor config exist today. No code from other branches.

## Architecture

```mermaid
sequenceDiagram
    participant Client
    participant MigrationSvc as migration_service
    participant S3
    participant Docker as docker_sock
    participant FMS as FMS_container

    Client->>MigrationSvc: POST /authenticate Bearer token
    MigrationSvc->>MigrationSvc: validate AUTH_TOKEN
    alt migration already running
        MigrationSvc->>Client: 409 busy
    else idle
        MigrationSvc->>MigrationSvc: acquire migration lock
        MigrationSvc->>S3: aws s3 cp bucket/SOLUTION_clone.fmp12
        MigrationSvc->>MigrationSvc: write ./staging/SOLUTION_clone.fmp12
        MigrationSvc->>Docker: docker cp to FMS:/tmp/migration/clone.fmp12
        MigrationSvc->>FMS: docker exec migration commands stub
        MigrationSvc->>MigrationSvc: release migration lock
        MigrationSvc->>Client: 200 JSON or error
    end
```

## Project layout

```
migration/
├── compose.yml
├── Dockerfile
├── .env.example
├── .gitignore
├── requirements.txt
├── docs/
│   └── aws-iam.md       # IAM user/role setup + S3 policy (AWS only — no docker)
├── src/
│   ├── main.py          # FastAPI app, route, lifespan
│   ├── config.py        # env loading + validation
│   ├── auth.py          # Bearer token dependency
│   └── pipeline.py      # S3 → staging → docker cp → docker exec
└── staging/             # gitignored; runtime download dir
```

## HTTP API

| Item | Choice |
|------|--------|
| Method / path | `POST /authenticate` |
| Auth | `Authorization: Bearer <AUTH_TOKEN>` (constant from `.env`) |
| Request body | None (SOLUTION is env-driven) |
| Success | `200` + `{ "status": "ok" }` |
| Auth failure | `401` |
| Migration already running | `409` + `{ "status": "busy" }` |
| Pipeline failure | `502` + `{ "status": "error", "step": "...", "detail": "..." }` |

Use **FastAPI** — minimal surface area, built-in dependency injection for auth, easy to extend when `docker exec` commands arrive.

### Concurrency (single-flight)

Only one migration may run at a time. If `POST /authenticate` arrives while a prior request is still executing the pipeline, reject it immediately — do not queue or start a second run.

In [src/main.py](src/main.py), hold an in-process `asyncio.Lock` (or equivalent) around the full `run_authenticate()` call. Check/acquire before starting the pipeline; release in a `finally` block so failures still unblock later requests. This is sufficient for v1 because the service runs as a single process under uvicorn.

## Environment variables

Document in [.env.example](.env.example):

| Variable | Purpose |
|----------|---------|
| `AUTH_TOKEN` | Expected Bearer token |
| `BUCKET` | S3 bucket name (no `s3://` prefix) |
| `SOLUTION` | Prefix for object key `{SOLUTION}_clone.fmp12` |
| `FMS_CONTAINER` | Target container name or ID |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` | Standard AWS CLI creds (or omit if host IAM/instance role is forwarded) |
| `PORT` | Default `8080` |

Load via `pydantic-settings` in [src/config.py](src/config.py); fail fast at startup if required vars are missing.

## Pipeline implementation ([src/pipeline.py](src/pipeline.py))

Run each step with `subprocess.run(..., check=True, capture_output=True, text=True)` — matches your shell commands and keeps logs inspectable.

1. **Ensure staging dir** — `mkdir -p staging`
2. **S3 download**
   ```bash
   aws s3 cp "s3://${BUCKET}/${SOLUTION}_clone.fmp12" "./staging/${SOLUTION}_clone.fmp12"
   ```
3. **Docker copy** (requires `/var/run/docker.sock` mount)
   ```bash
   docker cp "./staging/${SOLUTION}_clone.fmp12" "${FMS_CONTAINER}:/tmp/migration/clone.fmp12"
   ```
4. **Docker exec (stub)** — placeholder function `run_fms_migration(container: str) -> None` that currently runs a no-op or a single harmless command (e.g. `docker exec ... ls /tmp/migration`) until you supply real commands. Structure it so swapping in real commands is a one-file change:

   ```python
   def fms_exec_args() -> list[str]:
       # TODO: replace with real FileMaker migration commands
       return ["ls", "-la", "/tmp/migration"]
   ```

   Then: `docker exec <FMS_CONTAINER> <args...>`.

Wrap the full pipeline in one `run_authenticate()` function; map `CalledProcessError` to step name + stderr for the HTTP error response.

When implementing the S3 step, also add [docs/aws-iam.md](docs/aws-iam.md) (see below).

## AWS IAM README ([docs/aws-iam.md](docs/aws-iam.md))

Create this alongside the S3 pipeline step. **AWS/IAM only** — do not duplicate docker, compose, curl, or local dev instructions the reader already knows.

**Include**

1. **Purpose** — one paragraph: dedicated IAM principal for the migration service to read clone files from a single bucket.
2. **Principal choice** — IAM user with access keys (env vars in `.env`) vs IAM role (EC2 instance profile / ECS task role). Note which vars to set for each.
3. **Policy** — least-privilege inline or managed custom policy. Required actions:
   - `s3:ListBucket` on `arn:aws:s3:::${BUCKET}` — list objects in the bucket (scoped with `s3:prefix` condition when practical)
   - `s3:GetObject` on `arn:aws:s3:::${BUCKET}/${SOLUTION}_clone.fmp12` — download the clone file
4. **Example policy document** — JSON with `${BUCKET}` / `${SOLUTION}` placeholders to substitute before attach:

   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Sid": "ListBucketForClone",
               "Effect": "Allow",
               "Action": ["s3:ListBucket"],
               "Resource": "arn:aws:s3:::BUCKET_NAME",
               "Condition": {
                   "StringLike": {
                       "s3:prefix": ["SOLUTION_PREFIX_*"]
                   }
               }
           },
           {
               "Sid": "GetCloneObject",
               "Effect": "Allow",
               "Action": ["s3:GetObject"],
               "Resource": "arn:aws:s3:::BUCKET_NAME/SOLUTION_PREFIX_clone.fmp12"
           }
       ]
   }
   ```

5. **Setup steps** — create policy → create user (or role) → attach policy → create access key (if user) → map `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` in `.env`.
6. **Verification** — `aws s3 ls s3://BUCKET_NAME/SOLUTION_PREFIX_clone.fmp12` and `aws s3 cp` dry-run or head-object check using the new principal's creds.

**Exclude**

- Docker, compose, `docker cp`, `docker exec`, or service HTTP usage
- Generic AWS CLI install instructions

## Docker image ([Dockerfile](Dockerfile))

Multi-stage build with **`develop`** and **`production`** targets sharing a `base` stage:

**`base` stage**
- `python:3.12-slim`
- Install **AWS CLI v2** and **docker CLI** (client only — no daemon)
- `WORKDIR /app`
- Copy `requirements.txt`, `pip install`
- Copy `src/`

**`develop` target**
- `CMD` → `uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080} --reload`
- Used by Compose Watch for live code sync

**`production` target**
- Same as develop but without `--reload` (for non-watch deploys later)

## Compose ([compose.yml](compose.yml))

```yaml
services:
  migration:
    build:
      context: .
      target: develop
    env_file: .env
    ports:
      - "${PORT:-8080}:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./staging:/app/staging
    develop:
      watch:
        - action: sync
          path: ./src
          target: /app/src
        - action: rebuild
          path: ./requirements.txt
```

**Notes**
- `docker.sock` mount gives the service permission to `docker cp` / `docker exec` against containers on the **host** (including `FMS_CONTAINER` running outside this compose stack).
- `./staging` bind-mount keeps downloaded `.fmp12` visible on the host for debugging and avoids re-downloading on container recreate if desired.
- Run as root inside the container (default) — required for typical docker.sock access unless you map the host `docker` GID.

## Supporting files

- **[requirements.txt](requirements.txt)** — `fastapi`, `uvicorn[standard]`, `pydantic-settings`
- **[.gitignore](.gitignore)** — `.env`, `staging/`, `__pycache__/`, `.venv/`
- **[docs/aws-iam.md](docs/aws-iam.md)** — IAM setup for S3 access (see AWS IAM README section)
- **[src/auth.py](src/auth.py)** — FastAPI `Depends` that compares Bearer token to `config.auth_token` using `secrets.compare_digest`
- **[src/main.py](src/main.py)** — `GET /health` (unauthenticated, for compose/orchestrator checks) + `POST /authenticate` with single-flight lock

## Local dev workflow

```bash
cp .env.example .env   # fill in values
docker compose watch   # rebuild on requirements change, sync src on save
curl -X POST http://localhost:8080/authenticate \
  -H "Authorization: Bearer $AUTH_TOKEN"
```

## Out of scope (for later)

- Real `docker exec` FileMaker commands (stub only)
- Request-scoped `SOLUTION` (fixed per deployment per your choice)
- TLS termination, rate limiting, job queue / async long-running migrations
- Running FMS container in the same compose file (assumed external; referenced by name)
- Cross-process or multi-replica migration locking (single uvicorn worker assumed for v1)

## Risks / assumptions

- **FMS container must exist** and be reachable by the name in `FMS_CONTAINER` before calling `/authenticate`.
- **`/tmp/migration/`** must exist inside FMS container or `docker cp` parent path must be creatable — if not, add a preparatory `docker exec ... mkdir -p /tmp/migration` in the stub step.
- **AWS credentials** must be available inside the migration container (env vars or mounted `~/.aws`); see [docs/aws-iam.md](docs/aws-iam.md) for required IAM permissions.
- **Large `.fmp12` files** — synchronous request may time out; acceptable for v1; can move to background job later if needed.
- **Concurrent callers** — second and later requests while a migration is in flight receive `409`; clients should retry after the in-progress run finishes.

