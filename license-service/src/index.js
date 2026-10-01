const MAX_REQUEST_BYTES = 4096;
const MAX_DEVICES = 3;
const LICENSE_PREFIX = 'sai_';

function response(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'x-content-type-options': 'nosniff'
    }
  });
}

function error(message, status) {
  return response({ error: message }, status);
}

function base64url(bytes) {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, '');
}

function randomSecret(byteCount = 32) {
  return base64url(crypto.getRandomValues(new Uint8Array(byteCount)));
}

async function sha256(value) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function sameSecret(left, right) {
  const encoder = new TextEncoder();
  const a = encoder.encode(left || '');
  const b = encoder.encode(right || '');
  let difference = a.length ^ b.length;
  const count = Math.max(a.length, b.length);
  for (let index = 0; index < count; index += 1) {
    difference |= (a[index] || 0) ^ (b[index] || 0);
  }
  return difference === 0;
}

async function readJson(request) {
  if (!(request.headers.get('content-type') || '').toLowerCase().includes('application/json')) {
    return { error: 'Content-Type must be application/json' };
  }
  const length = Number(request.headers.get('content-length') || 0);
  if (length > MAX_REQUEST_BYTES) return { error: 'Request too large' };
  const text = await request.text();
  if (new TextEncoder().encode(text).length > MAX_REQUEST_BYTES) return { error: 'Request too large' };
  try {
    const value = JSON.parse(text);
    return value && typeof value === 'object' && !Array.isArray(value)
      ? { value }
      : { error: 'JSON body must be an object' };
  } catch {
    return { error: 'Invalid JSON' };
  }
}

async function allowedByRateLimit(request, env) {
  if (!env.LICENSE_LIMITER) return true;
  const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
  const result = await env.LICENSE_LIMITER.limit({ key: ip });
  return result.success;
}

function isLicenseKey(value) {
  return typeof value === 'string' && /^sai_[A-Za-z0-9_-]{32,64}$/u.test(value);
}

function bearer(request) {
  const value = request.headers.get('authorization') || '';
  return value.startsWith('Bearer ') ? value.slice(7).trim() : '';
}

function validExpiry(expiresAt) {
  return !expiresAt || Date.parse(expiresAt) > Date.now();
}

async function requireAdmin(request, env) {
  const expected = env.ADMIN_API_TOKEN;
  const provided = bearer(request);
  return Boolean(expected && provided && sameSecret(provided, expected));
}

async function activate(request, env) {
  const parsed = await readJson(request);
  if (parsed.error) return error(parsed.error, 400);
  const { license_key: licenseKey, device_id: deviceId, device_name: deviceName = '' } = parsed.value;
  if (!isLicenseKey(licenseKey)) return error('Invalid license key', 400);
  if (typeof deviceId !== 'string' || !/^[A-Za-z0-9._:-]{16,128}$/u.test(deviceId)) {
    return error('Invalid device identifier', 400);
  }
  if (typeof deviceName !== 'string' || deviceName.length > 100) return error('Invalid device name', 400);

  const licenseHash = await sha256(licenseKey);
  const license = await env.LICENSES.prepare(
    'SELECT status, max_devices, expires_at FROM licenses WHERE license_hash = ?'
  ).bind(licenseHash).first();
  if (!license || license.status !== 'active' || !validExpiry(license.expires_at)) {
    return error('License is invalid, expired, or revoked', 403);
  }

  const activationId = randomSecret(18);
  const sessionToken = `sat_${randomSecret(32)}`;
  const now = new Date().toISOString();
  const result = await env.LICENSES.prepare(`
    INSERT INTO activations
      (activation_id, license_hash, device_hash, device_name, token_hash, created_at, last_seen)
    SELECT ?, ?, ?, ?, ?, ?, ?
    WHERE (
      SELECT COUNT(*) FROM activations
      WHERE license_hash = ? AND device_hash <> ?
    ) < (
      SELECT max_devices FROM licenses WHERE license_hash = ? AND status = 'active'
    )
    ON CONFLICT(license_hash, device_hash) DO UPDATE SET
      device_name = excluded.device_name,
      token_hash = excluded.token_hash,
      last_seen = excluded.last_seen
  `).bind(
    activationId, licenseHash, await sha256(deviceId), deviceName.trim(),
    await sha256(sessionToken), now, now, licenseHash, await sha256(deviceId), licenseHash
  ).run();

  if (!result.success) return error('License activation could not be completed', 503);
  const deviceLimit = Math.min(Number(license.max_devices) || MAX_DEVICES, MAX_DEVICES);
  if (!result.meta?.changes) return error(`This license is already active on ${deviceLimit} devices`, 409);
  return response({ session_token: sessionToken, max_devices: deviceLimit });
}

async function validate(request, env) {
  const token = bearer(request);
  if (!token || token.length > 200) return error('Activation required', 401);
  const tokenHash = await sha256(token);
  const row = await env.LICENSES.prepare(`
    SELECT a.license_hash, l.status, l.expires_at
    FROM activations a
    JOIN licenses l ON l.license_hash = a.license_hash
    WHERE a.token_hash = ?
  `).bind(tokenHash).first();
  if (!row || row.status !== 'active' || !validExpiry(row.expires_at)) {
    return error('Activation is invalid, expired, or revoked', 401);
  }
  await env.LICENSES.prepare('UPDATE activations SET last_seen = ? WHERE token_hash = ?')
    .bind(new Date().toISOString(), tokenHash).run();
  return response({ valid: true });
}

async function deactivate(request, env) {
  const token = bearer(request);
  if (!token || token.length > 200) return error('Activation required', 401);
  await env.LICENSES.prepare('DELETE FROM activations WHERE token_hash = ?')
    .bind(await sha256(token)).run();
  return response({ deactivated: true });
}

async function createLicense(request, env) {
  if (!await requireAdmin(request, env)) return error('Unauthorized', 401);
  const parsed = await readJson(request);
  if (parsed.error) return error(parsed.error, 400);
  const maxDevices = Number(parsed.value.max_devices || MAX_DEVICES);
  if (!Number.isInteger(maxDevices) || maxDevices < 1 || maxDevices > MAX_DEVICES) {
    return error(`max_devices must be between 1 and ${MAX_DEVICES}`, 400);
  }
  let expiresAt = null;
  if (parsed.value.expires_at) {
    const timestamp = Date.parse(parsed.value.expires_at);
    if (!Number.isFinite(timestamp) || timestamp <= Date.now()) return error('Invalid expiration date', 400);
    expiresAt = new Date(timestamp).toISOString();
  }
  const key = `${LICENSE_PREFIX}${randomSecret(32)}`;
  await env.LICENSES.prepare(`
    INSERT INTO licenses (license_hash, max_devices, created_at, expires_at)
    VALUES (?, ?, ?, ?)
  `).bind(await sha256(key), maxDevices, new Date().toISOString(), expiresAt).run();
  return response({ license_key: key, max_devices: maxDevices, expires_at: expiresAt }, 201);
}

async function revokeLicense(request, env) {
  if (!await requireAdmin(request, env)) return error('Unauthorized', 401);
  const parsed = await readJson(request);
  if (parsed.error) return error(parsed.error, 400);
  if (!isLicenseKey(parsed.value.license_key)) return error('Invalid license key', 400);
  const licenseHash = await sha256(parsed.value.license_key);
  const result = await env.LICENSES.prepare(
    "UPDATE licenses SET status = 'revoked' WHERE license_hash = ?"
  ).bind(licenseHash).run();
  return response({ revoked: Boolean(result.meta?.changes) });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'GET' && url.pathname === '/healthz') return response({ ok: true });
    if (!['POST'].includes(request.method)) return error('Method not allowed', 405);

    if (!await allowedByRateLimit(request, env)) return error('Too many requests', 429);
    if (url.pathname === '/v1/activate') return activate(request, env);
    if (url.pathname === '/v1/validate') return validate(request, env);
    if (url.pathname === '/v1/deactivate') return deactivate(request, env);
    if (url.pathname === '/admin/licenses') return createLicense(request, env);
    if (url.pathname === '/admin/revoke') return revokeLicense(request, env);
    return error('Not found', 404);
  }
};
