const assert = require('assert');
const fs = require('fs');
const path = require('path');

const generationSource = fs.readFileSync(
    path.join(__dirname, '..', 'static', 'js', 'generation.js'),
    'utf8'
);
const tutorSource = fs.readFileSync(
    path.join(__dirname, '..', 'static', 'js', 'app_with_health_check.js'),
    'utf8'
);
const overviewSource = fs.readFileSync(
    path.join(__dirname, '..', 'static', 'js', 'overview.js'),
    'utf8'
);

assert.match(
    generationSource,
    /deleteGenerationArtifact/,
    'generation history should expose a delete handler for artifacts'
);
assert.match(
    generationSource,
    /method:\s*'DELETE'[\s\S]*\/generation\/artifacts/,
    'artifact deletion should call DELETE /generation/artifacts'
);
assert.match(
    generationSource,
    /artifact-delete-btn/,
    'artifact rows should render a delete button'
);
assert.doesNotMatch(
    generationSource,
    /<a href="' \+ downloadUrl \+ '" target="_blank"/,
    'artifact download links should not open a new browser tab in the desktop shell'
);
assert.doesNotMatch(
    overviewSource,
    /<a class="overview-mini-btn" href="' \+ downloadUrl \+ '" target="_blank"/,
    'overview artifact download links should not open a new browser tab in the desktop shell'
);

assert.match(
    tutorSource,
    /exportHistorySessionPdf/,
    'training history should expose a PDF export handler'
);
assert.match(
    tutorSource,
    /fetch\(url\)/,
    'training history PDF export should fetch the PDF instead of navigating to a blank tab'
);
assert.match(
    tutorSource,
    /link\.download\s*=\s*filename/,
    'training history PDF export should trigger a named file download'
);
assert.match(
    tutorSource,
    /\/session\/\$\{sessionId\}\/export\.pdf/,
    'training history PDF export should use the PDF endpoint'
);
assert.match(
    tutorSource,
    /deleteHistorySession/,
    'training history should expose a delete handler'
);
assert.match(
    tutorSource,
    /method:\s*'DELETE'[\s\S]*\/session\/\$\{sessionId\}/,
    'training history deletion should call DELETE /session/{session_id}'
);
assert.match(
    tutorSource,
    /history-export-pdf/,
    'history rows should render a PDF export button'
);
assert.match(
    tutorSource,
    /history-delete-session/,
    'history rows should render a delete button'
);
assert.match(
    tutorSource,
    /exportReportPdfBtn/,
    'report detail page should expose a PDF export button'
);
