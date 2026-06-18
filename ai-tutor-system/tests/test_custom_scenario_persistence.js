const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'static/js/app_with_health_check.js'), 'utf8');
const index = fs.readFileSync(path.join(root, 'static/index.html'), 'utf8');

assert(app.includes('async function loadScenarios()'), 'frontend should expose scenario hydration');
assert(app.includes("fetch(`${CONFIG.TUTOR_API}/scenarios`)"), 'frontend should load backend scenarios');
assert(app.includes('option.textContent = scenario.name'), 'scenario names must use textContent');
assert(app.includes('loadScenarios();'), 'scenario hydration should run during initialization');
assert(index.includes('/static/js/app_with_health_check.js?v=2.2'), 'tutor script cache version must change');

console.log('All custom scenario persistence assertions passed.');
