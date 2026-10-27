# CampusLoop — Lost & Found Portal

A local-first campus lost-and-found prototype. Students can report lost and found items, browse and search listings, inspect possible matches, and submit private claims. Admins can approve/reject claims and mark approved items returned.

## Run locally (Windows)

**Prerequisites:** Python 3.10+ and Node.js 18+.

From the project root, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

On first run the script creates a backend virtual environment, installs the dependencies, seeds the SQLite database, and opens separate backend and frontend terminal windows. Later runs retain existing database data. Open:

- App: http://localhost:5173
- API docs: http://localhost:8000/docs

Sign in with one of the demo accounts below, or create a student account in the app.

| Role | Email | Password |
|---|---|---|
| Admin | `admin@campus.edu` | `CampusAdmin123!` |
| Student | `maya@campus.edu` | `Student123!` |
| Student | `sam@campus.edu` | `Student123!` |
| Student | `alex@campus.edu` | `Student123!` |

### Share on the same Wi-Fi

To let friends on the same trusted Wi-Fi/LAN open the prototype, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -ShareOnLan
```

Find this computer's private IPv4 address with `ipconfig` (the active Wi-Fi adapter's IPv4 Address). Share `http://<that-address>:5173`, for example `http://192.168.1.23:5173`. Your computer and the other devices must be on the same network, and Windows Firewall may ask you to allow Python/Node on **Private networks**. Stop the app's two terminal windows when finished. Do not configure router port forwarding. For public access, follow the read-only Render or Cloudflare Tunnel steps below.

To run either service manually:

```powershell
# Backend terminal
cd .\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe seed.py
.\.venv\Scripts\python.exe -m uvicorn main:app --reload

# Frontend terminal
cd .\frontend
npm.cmd install
npm.cmd run dev
```

The database is `backend/campus_portal.db`. To reload the sample dataset and reset its reports/claims, stop the backend and run `.\.venv\Scripts\python.exe seed.py --reset` from `backend`.

## Publish a permanent public read-only link (Render)

The Docker image builds the frontend into `frontend/dist` and serves it from FastAPI. Both [Dockerfile](./Dockerfile) and [render.yaml](./render.yaml) set `PUBLIC_DEMO_READ_ONLY=true`; visitors can browse without an account, while the API rejects report, claim, and admin writes. The Render Blueprint checks `/health`. The free Render service may sleep when idle; its SQLite storage is ephemeral and seeded again after a fresh instance start.

1. Create a new, empty GitHub repository (do not initialize it with a README or license).
2. From the project root, initialize Git and push the source:

   ```powershell
   git init
   git add .
   git commit -m "Prepare CampusLoop public demo"
   git branch -M main
   git remote add origin https://github.com/<YOUR-USERNAME>/<YOUR-REPOSITORY>.git
   git push -u origin main
   ```

3. In Render, choose **New → Blueprint**, select/connect the GitHub repository, and click **Deploy** for the detected `render.yaml`.
4. When deployment finishes, open the service page and copy the assigned URL. It will look like `https://campusloop-demo.onrender.com` (the exact hostname depends on availability).
5. Verify the app at that URL and `https://<assigned-hostname>/health`; the health endpoint should return `{"status":"ok"}`.

Do not turn off `PUBLIC_DEMO_READ_ONLY=true` for a public demo.

To build and smoke-test the Docker image locally (requires Docker Desktop on Windows):

```powershell
docker build -t campusloop-demo .
docker run --rm -p 10000:10000 campusloop-demo
```

In another terminal, run `Invoke-RestMethod http://localhost:10000/health`; it should return `status: ok`. The container defaults to `PUBLIC_DEMO_READ_ONLY=true`.

### Quick temporary public link (Cloudflare Tunnel)

This link works only while both the local app and tunnel are running. Install Cloudflare Tunnel (`cloudflared`) first if it is not already on PATH. Open a PowerShell terminal in the project root and run:

```powershell
$env:PUBLIC_DEMO_READ_ONLY = "true"
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Wait for the backend and Vite windows to start, then open a second PowerShell terminal and run:

```powershell
cloudflared tunnel --url http://localhost:5173
```

Copy the `https://....trycloudflare.com` URL printed by `cloudflared` and share it. The temporary address stops working when the tunnel process or local app closes. Alternatively, with ngrok installed and configured, run `ngrok http 5173` and share its printed forwarding URL. Keep the backend in read-only mode while exposing it.

## Accounts and authentication

The demo accounts above are created by `backend/seed.py`. Sign in with email and password, or use **Create account** to register a student account. Passwords are stored as salted PBKDF2-HMAC hashes, and API access uses seven-day bearer-token sessions. Registration always creates a student; admin access is restricted to the seeded admin account.

To run the backend test suite:

```powershell
cd .\backend
.\.venv\Scripts\python.exe -m pytest
```

To build the frontend:

```powershell
cd .\frontend
npm.cmd run build
```

## Three-minute demo

1. Browse the seeded reports; filter by category, type, or location.
2. Open **Blue Hydro Flask bottle** and inspect the high-scoring found report and its explanation.
3. Submit a new lost or found report and see its possible matches immediately.
4. Open a found report as a student and submit a claim with a private identifying detail.
5. Sign in as Admin, approve the pending claim, then sign back in as the claimant.
6. Open **My activity** to see the approval note and collection instructions, then confirm collection.

See [docs/demo_script.md](docs/demo_script.md) for a timed walkthrough, [docs/technical_approach.md](docs/technical_approach.md) for design details, and [docs/sample_io.md](docs/sample_io.md) for example API payloads.

## API at a glance

- `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`
- `POST /items`, `GET /items`, `GET /items/{id}`, `GET /items/{id}/matches`
- `GET /my/items`, admin-only `GET /admin/items/{id}` (includes contact details)
- `GET /my/events`, `PATCH /my/items/{id}/recover`, `DELETE /my/items/{id}`
- `POST /claims`, `GET /claims`, `PATCH /claims/{id}`, `PATCH /claims/{id}/collect`
- `PATCH /items/{id}/return` (admin), `GET /stats`

All item listings omit owner/finder contact email. Claimant proof and email are returned only to an admin; students can view their own claim status and collection instructions without proof or finder email. Local image upload is not implemented.
