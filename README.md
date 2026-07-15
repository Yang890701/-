# Haoshi Development Portal

T1 is a hello-world monorepo scaffold. Real database schema, auth, metadata, import, billing, and business logic belong to later tasks.

## Structure

- `web/`: Next.js App Router with TypeScript, TanStack Table, and SheetJS dependencies declared.
- `api/`: FastAPI scaffold with pydantic-settings, Alembic files, and a local object-storage adapter.
- `infra/`: Future Docker services for machine A.

## Option B: Native PostgreSQL on this machine

Use this option on the current development machine while PostgreSQL is installed natively.

1. Create `.env` from `.env.example` and adjust `DATABASE_URL` for the native PostgreSQL instance.
2. Create the API virtual environment:

   ```powershell
   cd api
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

3. Run the API:

   ```powershell
   uvicorn app.main:app --reload
   ```

4. In another shell, install and build the web app:

   ```powershell
   cd web
   npm install
   npm run build
   npm run dev
   ```

## Option A: Docker services on future machine A

The Docker compose file is provided for the future machine A setup. It is not required for this machine's T1 verification.

```powershell
docker compose -f infra/docker-compose.yml up -d
```

After services are available, use `.env.example` as the starting point for database and object-store settings.

## T1 Verification After Dependencies Are Installed

```powershell
cd web
npm run build
```

```powershell
cd api
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then verify health from another shell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```
