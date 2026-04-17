# Phase-1 Security Checklist

Use this checklist after local changes that affect auth, package access, logging, or provenance.

## Logs

- Trigger a handled or unhandled error with a payload that includes nested secrets such as `api_key`, `authorization`, `cookie`, or `session_id`.
- Confirm API logs and worker/provider snapshots replace those values with `***REDACTED***`.
- Confirm request metadata such as `request_id`, `http_path`, and actor identifiers still remain visible for debugging.

## API-key hashing

- Hash a sample key with `content_lab_auth.hash_api_key(...)`.
- Confirm the stored value is versioned and does not contain the plaintext key.
- Confirm `verify_api_key(...)` accepts the original key and rejects an altered key or wrong salt.

## Audit coverage

- `POST /orgs/{org_id}/assets/resolve` on a new generation intent should create an `asset.generate.requested` audit row.
- Existing mutating routes for pages, policy, reel families, reels, and runs should continue writing org-scoped audit rows.

## Package access and provenance

- `GET /orgs/{org_id}/packages/{run_id}` should only return signed downloads for canonical `s3://{bucket}/reels/packages/{reel_id}/...` objects.
- If persisted package metadata points outside the reel package prefix or omits `reel_id`, the route should return `409`.
- Confirm `manifest`, `provenance`, and package artifacts remain traceable to the run/reel and stay inside canonical object storage.
