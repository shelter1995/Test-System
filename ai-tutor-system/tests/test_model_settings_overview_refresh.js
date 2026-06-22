const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const modelSettings = fs.readFileSync(path.join(root, 'static/js/model-settings.js'), 'utf8');
const overview = fs.readFileSync(path.join(root, 'static/js/overview.js'), 'utf8');
const index = fs.readFileSync(path.join(root, 'static/index.html'), 'utf8');

assert(
    modelSettings.includes("window.dispatchEvent(new CustomEvent('model-settings:saved'"),
    'model settings save should publish a refresh event'
);
assert(
    overview.includes("window.addEventListener('model-settings:saved'") &&
        overview.includes('refresh(true);'),
    'overview should force refresh when model settings are saved'
);
assert(
    index.includes('/static/js/model-settings.js?v=1.1') &&
        index.includes('/static/js/overview.js?v=1.2'),
    'script versions should be bumped so the browser loads the refreshed assets'
);
