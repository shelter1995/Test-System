const assert = require('assert');
const fs = require('fs');
const path = require('path');

const cssPath = path.join(__dirname, '..', 'static', 'css', 'style.css');
const cssSource = fs.readFileSync(cssPath, 'utf8');
const htmlPath = path.join(__dirname, '..', 'static', 'index.html');
const htmlSource = fs.readFileSync(htmlPath, 'utf8');

assert.match(cssSource, /--dropdown-control-height:\s*42px;/);
assert.match(cssSource, /--dropdown-control-border:\s*1px solid #cfd8e3;/);
assert.match(cssSource, /--dropdown-control-focus-ring:\s*0 0 0 3px rgba\(122, 169, 216, 0\.16\);/);
assert.match(cssSource, /--dropdown-chevron:\s*url\("data:image\/svg\+xml,[^"]+"\);/);
assert.match(cssSource, /--dropdown-chevron-size:\s*16px 16px;/);

const contractMatch = cssSource.match(/\/\* 统一下拉控件 \*\/\s*([^{}]+)\{([^{}]+)\}/s);
assert.ok(contractMatch, 'shared dropdown control rule should exist');

const selectors = contractMatch[1];
[
    '.start-form select:not(.native-select-hidden)',
    'select.form-control',
    '.history-filter-select',
    '.settings-field select',
    '.settings-test-target',
    '.tutor-db-button',
    '.kbchat-db-button',
].forEach((selector) => {
    assert.ok(selectors.includes(selector), `shared dropdown rule should include ${selector}`);
});

const declarations = contractMatch[2];
assert.match(declarations, /height:\s*var\(--dropdown-control-height\);/);
assert.match(declarations, /border:\s*var\(--dropdown-control-border\);/);
assert.match(declarations, /border-radius:\s*var\(--radius-md\);/);
assert.match(declarations, /font:\s*inherit;/);
assert.match(declarations, /box-sizing:\s*border-box;/);

assert.match(
    cssSource,
    /\.start-form select:not\(\.native-select-hidden\):focus,[^{]+\.kbchat-db-button:focus\s*\{[^}]*border-color:\s*#7aa9d8;[^}]*box-shadow:\s*var\(--dropdown-control-focus-ring\);/s,
    'covered dropdowns should share one focus treatment'
);
assert.match(
    cssSource,
    /select\.form-control,[^{]+\.settings-test-target\s*\{[^}]*appearance:\s*none;[^}]*background-image:\s*var\(--dropdown-chevron\);[^}]*background-size:\s*var\(--dropdown-chevron-size\);/s,
    'native selects should use the shared chevron resource'
);
assert.match(
    cssSource,
    /\.tutor-db-caret,\s*\.kbchat-db-caret\s*\{[^}]*width:\s*16px;[^}]*height:\s*16px;[^}]*background-image:\s*var\(--dropdown-chevron\);[^}]*background-size:\s*var\(--dropdown-chevron-size\);/s,
    'custom database pickers should use the same chevron resource and size as native selects'
);
assert.ok(
    htmlSource.includes('/static/css/style.css?v=3.8'),
    'stylesheet cache version should change with the unified dropdown contract'
);
