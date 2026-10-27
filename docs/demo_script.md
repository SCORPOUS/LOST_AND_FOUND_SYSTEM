# Three-minute demo script

## 0:00–0:25 — Start in Browse

Open the seeded app and point out the report cards and filters. Search “bottle” or filter to **Water bottle** to narrow the listing. Explain that public cards show report details but not contact email. For a same-Wi-Fi demonstration, start with `run.ps1 -ShareOnLan` and open the host computer's private IPv4 address on the other device.

## 0:25–0:55 — Inspect a match

Open **Blue Hydro Flask bottle**. Show the found report, score, and the concise explanation (same category, color/brand, location, date). Note that these are suggestions, not automated claim decisions.

## 0:55–1:35 — Submit a claim

Open the matched found report. Enter a proof detail known to the owner (for example, a scratch under the sticker) and submit. Explain that the item owner/finder contact and proof are kept private from public listings.

## 1:35–2:20 — Admin review

Use **Preview as → Admin**. Open Admin review, inspect the pending claim and proof, and approve it with a short note. The found item becomes **claimed**. Click **Mark returned** to finish the status flow.

## 2:20–2:45 — Student status

Switch back to Student and open **My activity**. Show the report status and claim decision without displaying private proof.

## 2:45–3:00 — Wrap up

Mention that new reports are matched immediately against opposite-type open reports, and that FastAPI interactive API documentation is available at `/docs`. The prototype uses a local SQLite database and no paid/external APIs.
