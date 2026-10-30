// load-test.js - short k6 load test through the load balancer.
//
// 5 virtual users for 20 seconds. The build fails if:
//   - more than 1% of requests fail, or
//   - the slowest 5% of requests take longer than 2.5 s
//     (each page asks the backend for CPU usage, which itself takes ~1 s)
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '20s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<2500'],
  },
};

export default function () {
  const res = http.get(__ENV.TARGET_URL);
  check(res, {
    'status is 200': (r) => r.status === 200,
    'page shows the expected version': (r) => r.body.includes(`Frontend ${__ENV.VERSION}`),
  });
  sleep(1);
}


