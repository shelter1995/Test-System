const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const scriptPath = path.join(__dirname, '..', 'static', 'js', 'knowledge-chat.js');
const source = fs.readFileSync(scriptPath, 'utf8');

const documentStub = {
    addEventListener() {},
    createElement() {
        return {
            set textContent(value) {
                this.innerHTML = String(value || '')
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;');
            },
            innerHTML: '',
        };
    },
    getElementById() {
        return null;
    },
    querySelector() {
        return null;
    },
};

const context = {
    console,
    document: documentStub,
    window: {},
    MutationObserver: function () {
        return { observe() {} };
    },
};

vm.createContext(context);
vm.runInContext(source, context, { filename: scriptPath });

assert.ok(
    context.window.KnowledgeChatStream,
    'knowledge-chat.js should expose KnowledgeChatStream for SSE parsing tests'
);

const events = [];
let buffer = '';
buffer = context.window.KnowledgeChatStream.parseChunk(
    'event: token\ndata: {"delta":"第一段"}\n\n' +
    'event: token\ndata: {"delta":"第二段"}\n\n' +
    'event: token\ndata: {}\n\n' +
    'event: done\ndata: {"answer":"第一段第二段"}\n\n',
    buffer,
    function (event) {
        events.push(event);
    }
);

assert.strictEqual(buffer, '');
assert.deepStrictEqual(events.map((event) => event.type), ['token', 'token', 'token', 'done']);
const answer = events
    .filter((event) => event.type === 'token')
    .map((event) => context.window.KnowledgeChatStream.tokenText(event.payload))
    .join('');

assert.strictEqual(answer, '第一段第二段');
assert.ok(!answer.includes('undefined'));
