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

### Share on the same Wi-Fi

To let friends on the same trusted Wi-Fi/LAN open the prototype, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -ShareOnLan
```

Find this computer's private IPv4 address with `ipconfig` (the active Wi-Fi adapter's IPv4 Address). Share `http://<that-address>:5173`, for example `http://192.168.1.23:5173`. Your computer and the other devices must be on the same network, and Windows Firewall may ask you to allow Python/Node on **Private networks**. Stop the app's two terminal windows when finished. Do not configure router port forwarding or share this demo over the public internet: its role picker is for demonstration, not secure authentication.

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

## Public read-only demo on Render

The repo includes a Render Blueprint and Dockerfile for a **read-only public demo**. In this deployment mode, public visitors can browse seeded reports and matching suggestions, but cannot submit reports or claims, access claim records, or use admin-only endpoints. The write restriction is enforced by FastAPI, not just hidden in the UI.

To publish it, push this project to a GitHub repository, sign in to Render, choose **New → Blueprint**, connect that repository, and deploy the detected `render.yaml`. Render will build the Docker image and assign a public `https://...onrender.com` address on the service page. Share that assigned URL after deployment completes. The hosted SQLite database is ephemeral; it is re-seeded with the sample listings after a fresh instance start. Render's free service may sleep when idle and take a short time to wake up.

This deployment intentionally does not expose the full claim workflow. Do not remove `PUBLIC_DEMO_READ_ONLY=true` to make the forms work: the prototype's role picker is not authentication. A full public workflow needs real sign-in and server-verified admin authorization first.

## Local demo roles

Use the **Preview as** selector in the app. Student demo identity: `maya@campus.edu`; admin: `admin@campus.edu`. There are no passwords or external identity services in this prototype. The backend checks the selected role for admin-only APIs, but the role header is intentionally not a production authentication mechanism.

## Three-minute demo

1. Browse the seeded reports; filter by category, type, or location.
2. Open **Blue Hydro Flask bottle** and inspect the high-scoring found report and its explanation.
3. Submit a new lost or found report and see its possible matches immediately.
4. Open a found report as Student and submit a claim with a private identifying detail.
5. Switch to Admin, approve the pending claim, then mark the item returned.
6. Switch back to Student → **My activity** to see report and claim statuses.

See [docs/demo_script.md](docs/demo_script.md) for a timed walkthrough, [docs/technical_approach.md](docs/technical_approach.md) for design details, and [docs/sample_io.md](docs/sample_io.md) for example API payloads.

## API at a glance

- `POST /items`, `GET /items`, `GET /items/{id}`, `GET /items/{id}/matches`
- `GET /my/items`, admin-only `GET /admin/items/{id}` (includes contact details)
- `POST /claims`, `GET /claims`, `PATCH /claims/{id}`
- `PATCH /items/{id}/return`, `GET /stats`

All item listings omit owner/finder contact email. Claimant proof and email are returned only to an admin; students can view their own claim status without proof. Local image upload is not implemented.
