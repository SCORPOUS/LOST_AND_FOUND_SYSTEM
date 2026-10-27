# Sample API I/O

<<<<<<< HEAD
Start the app using the instructions in [README.md](../README.md). Sign in first:

```http
POST /auth/login
Content-Type: application/json

{"email":"maya@campus.edu","password":"Student123!"}
```

Use the returned token on protected API requests:

```http
Authorization: Bearer <student-token>
Content-Type: application/json
```

For admin examples, sign in with `admin@campus.edu` and use its returned token. Examples below are representative; IDs and timestamps vary by database state.
=======
Start the app using the instructions in [README.md](../README.md). Requests that create reports or claims should include:

```http
X-User-Email: maya@campus.edu
X-User-Role: student
Content-Type: application/json
```

Admin requests use `X-User-Role: admin`. Examples below are representative; IDs and timestamps vary by database state.
>>>>>>> 8211c2f3d11a4ca8a3cf071dc5d4a4adc1e5020d

## 1. Lost item submission

`POST /items`

```json
{
  "type": "lost",
  "title": "Blue Hydro Flask bottle",
  "description": "Blue 750ml steel bottle with a mountain sticker",
  "category": "Water bottle",
  "color": "Blue",
  "brand": "Hydro Flask",
  "location": "Science Hall",
  "date_event": "2026-10-10",
  "contact_email": "maya@campus.edu"
}
```

Response `201 Created` (public response deliberately excludes contact email):

```json
{
  "item": {
    "id": 1,
    "type": "lost",
    "title": "Blue Hydro Flask bottle",
    "description": "Blue 750ml steel bottle with a mountain sticker",
    "category": "Water bottle",
    "color": "Blue",
    "brand": "Hydro Flask",
    "location": "Science Hall",
    "date_event": "2026-10-10",
    "image_path": null,
    "status": "open",
    "created_at": "2026-10-27T09:30:00+00:00"
  },
  "matches": []
}
```

## 2. Found item submission

`POST /items`

```json
{
  "type": "found",
  "title": "Blue steel water bottle",
  "description": "Hydro Flask bottle, small mountain sticker on side",
  "category": "Water bottle",
  "color": "Blue",
  "brand": "Hydro Flask",
  "location": "Science Hall",
  "date_event": "2026-10-11",
  "contact_email": "sam@campus.edu"
}
```

The response contains the new found item and its top matches, for example:

```json
{
  "item": {
    "id": 2,
    "type": "found",
    "title": "Blue steel water bottle",
    "description": "Hydro Flask bottle, small mountain sticker on side",
    "category": "Water bottle",
    "color": "Blue",
    "brand": "Hydro Flask",
    "location": "Science Hall",
    "date_event": "2026-10-11",
    "image_path": null,
    "status": "open",
    "created_at": "2026-10-27T09:31:00+00:00"
  },
  "matches": [
    {
      "item": {
        "id": 1,
        "type": "lost",
        "title": "Blue Hydro Flask bottle",
        "description": "Blue 750ml steel bottle with a mountain sticker",
        "category": "Water bottle",
        "color": "Blue",
        "brand": "Hydro Flask",
        "location": "Science Hall",
        "date_event": "2026-10-10",
        "image_path": null,
        "status": "open",
        "created_at": "2026-10-27T09:30:00+00:00"
      },
      "score": 86,
      "explanation": "same category, item descriptions are similar, color matches, brand matches, same location, 1 day(s) apart"
    }
  ]
}
```

## 3. Another report example (keys)

`POST /items`

```json
{
  "type": "lost",
  "title": "Brass keys with red tag",
  "description": "Three brass keys and a red CAMPUS tag on a ring",
  "category": "Keys",
  "color": "Brass",
  "brand": "",
  "location": "North Quad",
  "date_event": "2026-10-08",
  "contact_email": "jordan@campus.edu"
}
```

Representative response shape:

```json
{
  "item": {
    "id": 5,
    "type": "lost",
    "title": "Brass keys with red tag",
    "description": "Three brass keys and a red CAMPUS tag on a ring",
    "category": "Keys",
    "color": "Brass",
    "brand": "",
    "location": "North Quad",
    "date_event": "2026-10-08",
    "image_path": null,
    "status": "open",
    "created_at": "2026-10-27T09:32:00+00:00"
  },
  "matches": [
    {
      "item": {
        "id": 6,
        "type": "found",
        "title": "Key ring with red tag",
        "description": "Brass keys on a ring with red campus fob",
        "category": "Keys",
        "color": "Brass",
        "brand": "",
        "location": "North Quad Cafe",
        "date_event": "2026-10-09",
        "image_path": null,
        "status": "open",
        "created_at": "2026-10-27T09:32:01+00:00"
      },
      "score": 72,
      "explanation": "same category, item descriptions are similar, color matches, same campus zone, 1 day(s) apart"
    }
  ]
}
```

## Example match-result list

`GET /items/1/matches`:

```json
[
  {
    "item": {
      "id": 2,
      "type": "found",
      "title": "Blue steel water bottle",
      "description": "Hydro Flask bottle, small mountain sticker on side",
      "category": "Water bottle",
      "color": "Blue",
      "brand": "Hydro Flask",
      "location": "Science Hall",
      "date_event": "2026-10-11",
      "image_path": null,
      "status": "open",
      "created_at": "2026-10-27T09:31:00+00:00"
    },
    "score": 86,
    "explanation": "same category, item descriptions are similar, color matches, brand matches, same location, 1 day(s) apart"
  }
]
```

The endpoint returns at most five opposite-type reports. Example scores can vary if text or location details change.

## Claim submission and admin approval

Student request `POST /claims`:

```json
{
  "item_id": 2,
  "proof_description": "There is a small crescent-shaped scratch beneath the mountain sticker."
}
```

Response `201 Created`:

```json
{
  "id": 1,
  "item_id": 2,
  "status": "pending"
}
```

<<<<<<< HEAD
Admin request `PATCH /claims/1` with `Authorization: Bearer <admin-token>`:
=======
Admin request `PATCH /claims/1` with `X-User-Role: admin`:
>>>>>>> 8211c2f3d11a4ca8a3cf071dc5d4a4adc1e5020d

```json
{
  "status": "approved",
  "admin_notes": "Proof reviewed; ownership confirmed."
}
```

Response:

```json
{
  "id": 1,
  "item_id": 2,
  "item_title": "Blue steel water bottle",
  "status": "approved",
  "admin_notes": "Proof reviewed; ownership confirmed.",
  "created_at": "2026-10-27T09:40:00+00:00",
<<<<<<< HEAD
  "collect_location": "Science Hall",
=======
>>>>>>> 8211c2f3d11a4ca8a3cf071dc5d4a4adc1e5020d
  "claimant_email": "maya@campus.edu",
  "reporter_contact_email": "sam@campus.edu",
  "proof_description": "There is a small crescent-shaped scratch beneath the mountain sticker."
}
```

<<<<<<< HEAD
The claimant's `GET /claims` response includes status, admin notes, and `collect_location`, but does not include finder email or proof. The UI displays the approved collection instruction and provides **Confirm collected**. This sends `PATCH /claims/1/collect` with the claimant's bearer token and changes the item's status from `claimed` to `returned`. An admin can still use `PATCH /items/2/return` if needed.
=======
After approval, `PATCH /items/2/return` as admin changes the item's status from `claimed` to `returned`.
>>>>>>> 8211c2f3d11a4ca8a3cf071dc5d4a4adc1e5020d
