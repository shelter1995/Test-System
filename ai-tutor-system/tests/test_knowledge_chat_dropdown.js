const assert = require('assert');
const fs = require('fs');
const path = require('path');

const scriptPath = path.join(__dirname, '..', 'static', 'js', 'knowledge-chat.js');
const source = fs.readFileSync(scriptPath, 'utf8');
const cssPath = path.join(__dirname, '..', 'static', 'css', 'style.css');
const cssSource = fs.readFileSync(cssPath, 'utf8');
const htmlPath = path.join(__dirname, '..', 'static', 'index.html');
const htmlSource = fs.readFileSync(htmlPath, 'utf8');

assert.match(
    source,
    /<span class="kbchat-db-caret" aria-hidden="true"><\/span>/,
    'knowledge chat dropdown caret should be decorative and hidden from its accessible name'
);
assert.doesNotMatch(
    source,
    /class="kbchat-db-caret"[^>]*>[^<]+<\/span>/,
    'knowledge chat dropdown should not render a text glyph as its caret'
);
assert.match(
    cssSource,
    /\.tutor-db-caret,\s*\.kbchat-db-caret\s*\{[^}]*background-image:\s*var\(--dropdown-chevron\);[^}]*background-size:\s*var\(--dropdown-chevron-size\);/s,
    'knowledge chat dropdown caret should use the same chevron resource as other dropdowns'
);
assert.ok(
    htmlSource.includes('/static/js/knowledge-chat.js?v=2.9'),
    'knowledge chat script cache version should change with the dropdown markup'
);
assert.ok(
    htmlSource.includes('/static/css/style.css?v=3.8'),
    'stylesheet cache version should change with the dropdown caret styling'
);
