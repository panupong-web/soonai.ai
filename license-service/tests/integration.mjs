const baseUrl = (process.env.SOONAI_LICENSE_API_URL || '').replace(/\/$/u, '');
const adminToken = process.env.SOONAI_TEST_ADMIN_TOKEN || '';

if (!baseUrl || !adminToken) {
  throw new Error('Set SOONAI_LICENSE_API_URL and SOONAI_TEST_ADMIN_TOKEN to run integration tests.');
}
if (!baseUrl.startsWith('https://') && !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/u.test(baseUrl)) {
  throw new Error('Integration tests require HTTPS except for localhost.');
}

async function request(route, body, token = '') {
  const headers = { 'content-type': 'application/json' };
  if (token) headers.authorization = `Bearer ${token}`;
  const response = await fetch(baseUrl + route, {
    method: 'POST',
    headers,
    body: JSON.stringify(body)
  });
  return { status: response.status, body: await response.json() };
}

const issued = await request('/admin/licenses', { max_devices: 3 }, adminToken);
if (issued.status !== 201 || !issued.body.license_key) {
  throw new Error(`License issue failed with HTTP ${issued.status}`);
}
const unauthorized = await request('/admin/licenses', { max_devices: 3 });
if (unauthorized.status !== 401) throw new Error('Admin endpoint accepted a request without its secret.');
const licenseKey = issued.body.license_key;
const tokens = [];
for (let index = 0; index < 3; index += 1) {
  const result = await request('/v1/activate', {
    license_key: licenseKey,
    device_id: `integration-device-identifier-${index}`,
    device_name: 'integration-test'
  });
  if (result.status !== 200 || !result.body.session_token) {
    throw new Error(`Device ${index + 1} activation failed with HTTP ${result.status}`);
  }
  tokens.push(result.body.session_token);
}

const fourth = await request('/v1/activate', {
  license_key: licenseKey,
  device_id: 'integration-device-identifier-fourth',
  device_name: 'integration-test'
});
if (fourth.status !== 409) throw new Error('The fourth device was not rejected.');

const renewed = await request('/v1/activate', {
  license_key: licenseKey,
  device_id: 'integration-device-identifier-0',
  device_name: 'integration-test'
});
if (renewed.status !== 200 || !renewed.body.session_token) {
  throw new Error('Reactivation of an existing device consumed or denied a seat.');
}

const staleSession = await request('/v1/validate', {}, tokens[0]);
if (staleSession.status !== 401) throw new Error('Reactivation left the previous session valid.');
const validation = await request('/v1/validate', {}, renewed.body.session_token);
if (validation.status !== 200 || validation.body.valid !== true) {
  throw new Error('A valid device session failed validation.');
}

const revoked = await request('/admin/revoke', { license_key: licenseKey }, adminToken);
if (revoked.status !== 200 || revoked.body.revoked !== true) {
  throw new Error('License revocation failed.');
}
const afterRevoke = await request('/v1/validate', {}, renewed.body.session_token);
if (afterRevoke.status !== 401) throw new Error('Revoked session was still accepted.');

console.log('LICENSE_INTEGRATION_OK: 3-device limit, validation, revocation');
