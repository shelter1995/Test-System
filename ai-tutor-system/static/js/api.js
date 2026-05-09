/**
 * 统一 API 请求封装
 * 为工作台各模块提供通用的 fetch 工具函数
 */
const WorkbenchAPI = (function () {
    const BASE_URLS = {
        RAG_API: 'http://localhost:8003',
        TUTOR_API: 'http://localhost:8002',
    };

    async function requestJson(url, options = {}) {
        const resp = await fetch(url, options);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        return resp.json();
    }

    async function postJson(url, payload) {
        return requestJson(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
    }

    async function putJson(url, payload) {
        return requestJson(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
    }

    return { BASE_URLS, requestJson, postJson, putJson };
})();
