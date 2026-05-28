const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const scriptPath = path.join(__dirname, '..', 'static', 'js', 'app_with_health_check.js');
const source = fs.readFileSync(scriptPath, 'utf8');
const htmlPath = path.join(__dirname, '..', 'static', 'index.html');
const htmlSource = fs.readFileSync(htmlPath, 'utf8');
const cssPath = path.join(__dirname, '..', 'static', 'css', 'style.css');
const cssSource = fs.readFileSync(cssPath, 'utf8');

assert.match(
    htmlSource,
    /<span class="tutor-db-caret" aria-hidden="true"><\/span>/,
    'knowledge database dropdown caret should be drawn by CSS, not visible text'
);
assert.doesNotMatch(
    htmlSource,
    /class="tutor-db-caret"[^>]*>v<\/span>/,
    'knowledge database dropdown should not render a literal v as the caret'
);
assert.match(
    cssSource,
    /\.tutor-db-caret\s*{[^}]*border-width:\s*0 2px 2px 0;[^}]*transform:\s*rotate\(45deg\)/s,
    'knowledge database dropdown caret should use a compact chevron style similar to native selects'
);
assert.match(
    cssSource,
    /\.tutor-db-button\s*{[^}]*height:\s*42\.5px;[^}]*padding:\s*0\.5rem 0\.75rem;[^}]*border:\s*2px solid var\(--border-color\)/s,
    'knowledge database dropdown button should align with the surrounding form controls'
);

function createClassList() {
    const values = new Set();
    return {
        add(name) { values.add(name); },
        remove(name) { values.delete(name); },
        toggle(name, force) {
            if (force === undefined ? !values.has(name) : force) {
                values.add(name);
                return true;
            }
            values.delete(name);
            return false;
        },
        contains(name) { return values.has(name); },
    };
}

function createElement(tagName, id) {
    const listeners = {};
    const element = {
        tagName: tagName.toUpperCase(),
        id: id || '',
        children: [],
        options: tagName === 'select' ? [] : undefined,
        classList: createClassList(),
        dataset: {},
        style: {},
        value: '',
        textContent: '',
        _innerHTML: '',
        set innerHTML(value) {
            this._innerHTML = String(value || '');
            if (this._innerHTML === '') this.children = [];
        },
        get innerHTML() {
            return this._innerHTML;
        },
        disabled: false,
        title: '',
        setAttribute(name, value) { this[name] = String(value); },
        getAttribute(name) { return this[name]; },
        appendChild(child) {
            this.children.push(child);
            if (this.options) this.options.push(child);
            child.parentNode = this;
            return child;
        },
        remove(index) {
            if (this.options) this.options.splice(index, 1);
        },
        addEventListener(type, handler) {
            listeners[type] = listeners[type] || [];
            listeners[type].push(handler);
        },
        dispatchEvent(event) {
            (listeners[event.type] || []).forEach((handler) => handler(event));
        },
        querySelectorAll() { return []; },
        querySelector() { return null; },
        closest() { return null; },
        focus() {},
    };
    return element;
}

function createContext(databases) {
    const elements = {};
    const documentStub = {
        body: createElement('body', 'body'),
        addEventListener() {},
        createElement(tagName) {
            return createElement(tagName);
        },
        getElementById(id) {
            if (!elements[id]) {
                const tagName = id === 'tutorDatabase' ? 'select' : 'div';
                elements[id] = createElement(tagName, id);
            }
            return elements[id];
        },
        querySelector() {
            return null;
        },
        querySelectorAll() {
            return [];
        },
    };

    const autoOption = createElement('option');
    autoOption.value = '';
    autoOption.textContent = '自动选择';
    documentStub.getElementById('tutorDatabase').appendChild(autoOption);

    return {
        console,
        document: documentStub,
        window: {},
        Event: function (type) {
            return { type };
        },
        AbortSignal: {
            timeout() {
                return {};
            },
        },
        fetch(url) {
            if (String(url).endsWith('/db/list')) {
                return Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve({ status: 'success', databases }),
                });
            }
            return Promise.resolve({
                ok: true,
                json: () => Promise.resolve({ status: 'healthy' }),
            });
        },
        setTimeout() {
            return 1;
        },
        clearTimeout() {},
        MutationObserver: function () {
            return { observe() {} };
        },
        __elements: elements,
    };
}

(async () => {
    const databases = Array.from({ length: 6 }, (_, index) => ({
        id: `kb_${index + 1}`,
        name: `知识库 ${index + 1}`,
    }));
    const context = createContext(databases);

    vm.createContext(context);
    vm.runInContext(source, context, { filename: scriptPath });

    assert.ok(
        context.window.TutorDatabaseDropdown,
        'app_with_health_check.js should expose TutorDatabaseDropdown for regression tests'
    );

    await context.window.TutorDatabaseDropdown.populate();

    const select = context.__elements.tutorDatabase;
    const menu = context.__elements.tutorDatabaseMenu;
    assert.strictEqual(select.options.length, 7);
    assert.strictEqual(menu.children.length, 7);
    assert.deepStrictEqual(
        menu.children.map((child) => child.textContent),
        ['自动选择', '知识库 1', '知识库 2', '知识库 3', '知识库 4', '知识库 5', '知识库 6']
    );

    context.window.TutorDatabaseDropdown.select('kb_6');
    assert.strictEqual(select.value, 'kb_6');
    assert.strictEqual(context.__elements.tutorDatabaseButtonText.textContent, '知识库 6');
})();
