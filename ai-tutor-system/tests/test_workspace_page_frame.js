const assert = require('assert');
const fs = require('fs');
const path = require('path');

const cssPath = path.join(__dirname, '..', 'static', 'css', 'style.css');
const cssSource = fs.readFileSync(cssPath, 'utf8');
const htmlPath = path.join(__dirname, '..', 'static', 'index.html');
const htmlSource = fs.readFileSync(htmlPath, 'utf8');

assert.match(cssSource, /--workspace-frame-max:\s*1200px;/);

const frameMatch = cssSource.match(/\/\* 统一业务页面外框 \*\/\s*([^{}]+)\{([^{}]+)\}/s);
assert.ok(frameMatch, 'shared workspace page frame rule should exist');

const selectors = frameMatch[1];
[
    '.kbchat-page',
    '#generationApp',
    '.welcome-card',
    '.chat-container',
    '.report-container',
].forEach((selector) => {
    assert.ok(selectors.includes(selector), `shared frame should include ${selector}`);
});
assert.doesNotMatch(selectors, /history|drawer|backdrop|modal/i);

const declarations = frameMatch[2];
assert.match(declarations, /width:\s*100%;/);
assert.match(declarations, /max-width:\s*var\(--workspace-frame-max\);/);
assert.match(declarations, /margin-inline:\s*auto;/);
assert.match(declarations, /min-width:\s*0;/);

assert.match(
    cssSource,
    /#tutorApp #chatPage,\s*#tutorApp #reportPage\s*\{[^}]*padding:\s*0\.5rem 1\.5rem 1rem;[^}]*box-sizing:\s*border-box;/s,
    'tutor chat and report pages should use the same desktop horizontal gutter'
);
assert.match(
    cssSource,
    /#tutorApp \.start-container\s*\{[^}]*overflow-y:\s*visible;/s,
    'tutor start page should rely on its parent scroller instead of creating a nested scrollbar'
);
assert.match(
    cssSource,
    /#tutorApp #startPage\s*\{[^}]*overflow:\s*visible;/s,
    'tutor start page should use the workspace scroller without reserving a nested scrollbar gutter'
);
assert.match(
    cssSource,
    /@media \(max-width:\s*900px\)\s*\{[^}]*#tutorApp #chatPage,[^}]*#tutorApp #reportPage\s*\{[^}]*padding:\s*0\.5rem 1rem 1rem;/s,
    'tutor chat and report pages should use the mobile workspace gutter'
);
assert.match(
    cssSource,
    /@media \(max-width:\s*900px\)[\s\S]*?\.start-container\s*\{[^}]*padding:\s*0\.5rem 1rem 1rem;/,
    'tutor start page should use the same mobile workspace gutter'
);
assert.ok(
    htmlSource.includes('/static/css/style.css?v=3.8'),
    'stylesheet cache version should change with the shared workspace frame'
);
