# SoonAI License Worker

Cloudflare Worker + D1 service for issuing and validating SoonAI device activations. License keys and activation bearer tokens are stored as SHA-256 hashes in D1; raw license keys are returned once by the admin endpoint and must be delivered privately to the customer.

The Worker does not receive prompts, source files, API provider keys, or workspace contents. It only receives a license key during activation and an opaque random device identifier. Both Python and Node CLIs expose activation/status/deactivation; licensing remains opt-in until this service has been deployed and configured.

## Deploy

Requires Node.js 22+, a Cloudflare account, and Wrangler authentication (`npx wrangler login`).

1. Install dependencies: `npm ci`
2. Create the D1 database: `npm run db:create`
3. Copy the returned database ID into `wrangler.toml` in place of the placeholder.
4. Apply schema: `npm run db:migrate:remote`
5. Set an admin secret: `npx wrangler secret put ADMIN_API_TOKEN`
6. Deploy: `npm run deploy`
7. Configure Cloudflare rate limiting for `/v1/*` and `/admin/*` before distributing production licenses.
8. Set `SOONAI_LICENSE_API_URL` to the deployed HTTPS Worker URL on official client builds.
9. Only after activating and testing a real customer key, enable `SOONAI_LICENSE_REQUIRED=1` in the official launcher environment/release. Keep the gate off until then so an unavailable service cannot lock out all users.

Do not put `ADMIN_API_TOKEN`, customer license keys, or Cloudflare credentials in Git, `.dev.vars`, or client code. For local development, use an untracked `.dev.vars` file and a local D1 database only.

## Issue a license

```powershell
$headers = @{ Authorization = "Bearer $env:ADMIN_API_TOKEN" }
$body = @{ max_devices = 3 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$env:SOONAI_LICENSE_API_URL/admin/licenses" -Headers $headers -ContentType "application/json" -Body $body
```

Store the returned `license_key` in the customer delivery system. The service stores only its SHA-256 hash, so the original key cannot be recovered from D1.

Revoke a key:

```powershell
$body = @{ license_key = $licenseKey } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$env:SOONAI_LICENSE_API_URL/admin/revoke" -Headers $headers -ContentType "application/json" -Body $body
```

## Client commands

```text
soonai license activate
soonai license status
soonai license deactivate
```

The device activation session is protected with Windows DPAPI on Windows and file permissions on Unix-like systems. The CLI allows a 72-hour offline grace after a successful validation.

## Local integration test

After applying the local migration and starting `npm run dev` in another terminal, set these variables in the test shell and run `npm run test:integration`:

```powershell
$env:SOONAI_LICENSE_API_URL = "http://127.0.0.1:8787"
$env:SOONAI_TEST_ADMIN_TOKEN = "the local-only ADMIN_API_TOKEN value"
npm run test:integration
```

## Important limitations

This service limits activations for the official client, but it cannot prevent copying or patching source while the client remains public and MIT-licensed. A determined user can remove a local license check. To protect proprietary logic, that logic must execute on a service you control; this Worker currently validates entitlements only and does not proxy AI requests or process project files. Review privacy, terms, billing, support, abuse limits, and legal requirements before selling licenses.
