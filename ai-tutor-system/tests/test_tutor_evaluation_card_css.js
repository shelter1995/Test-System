const assert = require('assert');
const fs = require('fs');
const path = require('path');

const cssPath = path.join(__dirname, '..', 'static', 'css', 'style.css');
const cssSource = fs.readFileSync(cssPath, 'utf8');

assert.match(
    cssSource,
    /\.eval-card\.show\s*{[^}]*max-height:\s*56vh;[^}]*overflow-y:\s*auto/s,
    'visible evaluation cards should scroll when feedback and suggestions exceed the card height'
);

assert.match(
    cssSource,
    /\.eval-card\.show\s*{[^}]*scrollbar-gutter:\s*stable/s,
    'visible evaluation cards should reserve scrollbar space to avoid text reflow'
);
