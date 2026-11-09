import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const api = __ENV.API_BASE || 'http://127.0.0.1:8080';
const username = __ENV.TEST_USERNAME || '';
const password = __ENV.TEST_PASSWORD || '';
const errors = new Rate('crm_api_errors');
let vuToken = null;

export const options = {
  scenarios: {
    ramp_to_5000: {
      executor: 'ramping-vus', startVUs: 0,
      stages: [
        { duration: '2m', target: 250 },
        { duration: '3m', target: 1000 },
        { duration: '3m', target: 2500 },
        { duration: '3m', target: 5000 },
        { duration: '5m', target: 5000 },
        { duration: '3m', target: 0 },
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000', 'p(99)<2500'],
    crm_api_errors: ['rate<0.01'],
  },
};

export default function () {
  if (!vuToken) {
    if (!username || !password) throw new Error('Set TEST_USERNAME and TEST_PASSWORD for a dedicated load-test account');
    const login = http.post(`${api}/v1/auth/login`,
      JSON.stringify({ username, password }),
      { headers: { 'Content-Type': 'application/json' }, tags: { endpoint: 'login' } });
    const loginOk = check(login, { 'test account login': (r) => r.status === 200 });
    errors.add(!loginOk);
    if (!loginOk) return;
    vuToken = login.json('access_token');
  }
  const res = http.get(`${api}/v1/leads?limit=50`, {
    headers: { Authorization: `Bearer ${vuToken}` }, tags: { endpoint: 'lead_list' },
  });
  const ok = check(res, { 'lead list returns 200': (r) => r.status === 200 });
  errors.add(!ok);
  sleep(1);
}
