/**
 * 管理端前端公共工具：统一封装 fetch 调用与分页渲染。
 * 全部管理端页面共用这一份，避免每个页面各写一套错误处理逻辑。
 */

/**
 * 调用 /api/* 接口的统一入口。
 * - 自动带上 Cookie（credentials: "same-origin"），FR-01 的会话令牌就是靠这个 Cookie 传递的。
 * - 非 2xx 响应统一抛出 Error，message 取 FastAPI 默认错误体的 detail 字段
 *   （HTTPException 默认返回 {"detail": "..."}），调用方 catch 到直接展示给管理员即可。
 * - 401 时额外跳转登录页——会话过期是常见场景（8 小时 TTL 或后端进程重启），
 *   与其让每个页面各自处理这个特殊状态码，不如在这里统一兜底。
 */
async function apiFetch(url, options = {}) {
    const resp = await fetch(url, {
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });
    if (resp.status === 401) {
        window.location.href = "/login";
        throw new Error("会话已过期，正在跳转登录页");
    }
    let body = null;
    try {
        body = await resp.json();
    } catch (e) {
        // 204 No Content 等无响应体的情况，忽略解析失败。
    }
    if (!resp.ok) {
        const message = (body && body.detail) ? body.detail : `请求失败（HTTP ${resp.status}）`;
        throw new Error(message);
    }
    return body;
}

/**
 * 渲染一个简单的分页控件到指定容器。
 * @param {HTMLElement} container 承载分页按钮的元素
 * @param {{page: number, page_size: number, total: number}} pageInfo
 * @param {(nextPage: number) => void} onPageChange 点击页码时的回调
 */
function renderPagination(container, pageInfo, onPageChange) {
    const totalPages = Math.max(1, Math.ceil(pageInfo.total / pageInfo.page_size));
    container.innerHTML = "";
    const info = document.createElement("span");
    info.textContent = `第 ${pageInfo.page} / ${totalPages} 页，共 ${pageInfo.total} 条`;
    container.appendChild(info);

    const prevBtn = document.createElement("button");
    prevBtn.className = "secondary";
    prevBtn.textContent = "上一页";
    prevBtn.disabled = pageInfo.page <= 1;
    prevBtn.onclick = () => onPageChange(pageInfo.page - 1);
    container.appendChild(prevBtn);

    const nextBtn = document.createElement("button");
    nextBtn.className = "secondary";
    nextBtn.textContent = "下一页";
    nextBtn.disabled = pageInfo.page >= totalPages;
    nextBtn.onclick = () => onPageChange(pageInfo.page + 1);
    container.appendChild(nextBtn);
}

/** 在页面顶部的错误提示框里展示一条错误信息；传空字符串隐藏提示框。 */
function showError(boxElement, message) {
    if (!message) {
        boxElement.style.display = "none";
        boxElement.textContent = "";
        return;
    }
    boxElement.style.display = "block";
    boxElement.textContent = message;
}

/** 置信度徽章的 HTML 片段，供事件日志/预测调试等多个页面复用同一套展示样式。 */
function confidenceBadge(confidence, isDegraded) {
    const label = { low: "低", medium: "中", high: "高" }[confidence] || confidence;
    let html = `<span class="badge badge-${confidence}">${label}</span>`;
    if (isDegraded) {
        html += `<span class="badge badge-degraded">降级兜底</span>`;
    }
    return html;
}
