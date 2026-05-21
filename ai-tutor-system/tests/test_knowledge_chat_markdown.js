const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const scriptPath = path.join(__dirname, '..', 'static', 'js', 'knowledge-chat.js');
const source = fs.readFileSync(scriptPath, 'utf8');

function createContext() {
    const documentStub = {
        addEventListener() {},
        createElement() {
            return {
                _textContent: '',
                set textContent(value) {
                    this._textContent = String(value || '');
                    this.innerHTML = this._textContent
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;')
                        .replace(/"/g, '&quot;')
                        .replace(/'/g, '&#39;');
                },
                get textContent() {
                    return this._textContent;
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
    return {
        console,
        document: documentStub,
        window: {},
        MutationObserver: function () {
            return { observe() {} };
        },
    };
}

const context = createContext();
vm.createContext(context);
vm.runInContext(source, context, { filename: scriptPath });

assert.ok(
    context.window.KnowledgeChatMarkdown,
    'knowledge-chat.js should expose KnowledgeChatMarkdown for rendering and regression tests'
);

const html = context.window.KnowledgeChatMarkdown.render(
    [
        '| 技术路线 | 一句话定义 | 核心机制 |',
        '|---|---|---|',
        '| **GraphRAG** | 知识图谱增强检索 | 构建实体关系网络 |',
        '| Vectorless RAG | <script>alert(1)</script> | LLM 结构推理 |',
    ].join('\n')
);

assert.match(html, /<table>/);
assert.match(html, /<thead>/);
assert.match(html, /<tbody>/);
assert.match(html, /<th>技术路线<\/th>/);
assert.match(html, /<strong>GraphRAG<\/strong>/);
assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
assert.doesNotMatch(html, /^\| 技术路线/m);

const codeHtml = context.window.KnowledgeChatMarkdown.render(
    [
        '## 技术演进',
        '```',
        '传统Vector RAG -> GraphRAG',
        '```',
        '后续说明',
    ].join('\n')
);

assert.strictEqual(typeof codeHtml, 'string');
assert.match(codeHtml, /<pre><code>传统Vector RAG -&gt; GraphRAG<\/code><\/pre>/);
assert.match(codeHtml, /<p>后续说明<\/p>/);
assert.notStrictEqual(codeHtml, 'undefined');

const answerHtml = context.window.KnowledgeChatMarkdown.render(
    '这个能力支持按文件检索 [来源 8]，也可以继续追问[来源12]。'
);

assert.match(
    answerHtml,
    /<span class="kbchat-source-ref" title="来源 8">\[来源 8\]<\/span>/
);
assert.match(
    answerHtml,
    /<span class="kbchat-source-ref" title="来源 12">\[来源12\]<\/span>/
);

assert.strictEqual(
    typeof context.window.KnowledgeChatMarkdown.renderAnswerSources,
    'function',
    'knowledge-chat.js should expose answer source summary rendering for regression tests'
);

const sourcesHtml = context.window.KnowledgeChatMarkdown.renderAnswerSources([
    { sourceId: '8', fileName: '业务办理手册.pdf' },
    { sourceId: '来源 12', fileName: '<script>alert(1)</script>.docx' },
]);

assert.match(sourcesHtml, /<div class="kbchat-answer-sources"/);
assert.match(sourcesHtml, /来源8：业务办理手册\.pdf/);
assert.match(sourcesHtml, /来源12：&lt;script&gt;alert\(1\)&lt;\/script&gt;\.docx/);
assert.doesNotMatch(sourcesHtml, /<script>/);

assert.strictEqual(
    typeof context.window.KnowledgeChatMarkdown.renderAssistantBody,
    'function',
    'knowledge-chat.js should expose assistant body rendering for source timing regression tests'
);

const streamingAssistantHtml = context.window.KnowledgeChatMarkdown.renderAssistantBody({
    text: '正在生成回答...',
    sources: [{ sourceId: '8', fileName: '业务办理手册.pdf' }],
    complete: false,
});

assert.doesNotMatch(
    streamingAssistantHtml,
    /kbchat-answer-sources/,
    'assistant bubble should not render bottom sources before the answer is complete'
);

const completeAssistantHtml = context.window.KnowledgeChatMarkdown.renderAssistantBody({
    text: '答案已经生成完成 [来源 8]',
    sources: [{ sourceId: '8', fileName: '业务办理手册.pdf' }],
    complete: true,
});

assert.match(completeAssistantHtml, /kbchat-answer-sources/);
assert.match(completeAssistantHtml, /来源8：业务办理手册\.pdf/);
