/* ==========================================================================
   Abit Design System - Modern SPA & AJAX Interactive Engine for KAM
   ========================================================================== */

// --- 1. Theme Management (Auto 🌓 / Light ☀️ / Dark 🌙) ---
let themeMode = localStorage.getItem('abit_theme') || 'auto';

function initTheme() {
    setTheme(themeMode);
    
    // 监听系统深浅色变化（当处于 auto 模式时）
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (themeMode === 'auto') {
            setTheme('auto');
        }
    });
}

function setTheme(mode) {
    themeMode = mode;
    localStorage.setItem('abit_theme', mode);
    
    if (mode === 'auto') {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
    } else {
        document.documentElement.setAttribute('data-theme', mode);
    }

    const icons = { auto: '🌓', light: '☀️', dark: '🌙' };
    const labels = { auto: '自动', light: '浅色', dark: '深色' };
    
    document.querySelectorAll('#theme-icon').forEach(el => {
        el.textContent = icons[mode] || '🌓';
    });
    document.querySelectorAll('#theme-label').forEach(el => {
        el.textContent = labels[mode] || '自动';
    });
}

function cycleTheme() {
    const modes = ['auto', 'light', 'dark'];
    const nextIdx = (modes.indexOf(themeMode) + 1) % modes.length;
    const nextMode = modes[nextIdx];
    setTheme(nextMode);
    
    const labels = { auto: '跟随系统 🌓', light: '浅色模式 ☀️', dark: '深色模式 🌙' };
    showToast(`主题已切换为：${labels[nextMode]}`);
}

// 兼容老调用
function toggleTheme() {
    cycleTheme();
}

// --- 2. Toast Notification Pill ---
function showToast(message, type = 'info') {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const pill = document.createElement('div');
    pill.className = 'toast-pill';
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error' || type === 'danger') icon = '❌';
    if (type === 'warning') icon = '⚠️';

    pill.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(pill);

    setTimeout(() => {
        pill.style.opacity = '0';
        pill.style.transform = 'translateY(-12px) scale(0.95)';
        pill.style.transition = 'all 0.25s cubic-bezier(0.1, 0.8, 0.25, 1)';
        setTimeout(() => pill.remove(), 250);
    }, 2800);
}

// --- 3. Quick Copy with Feedback ---
async function copyToClipboard(text, label = '内容') {
    try {
        await navigator.clipboard.writeText(text);
        showToast(`已复制 ${label} 到剪贴板`, 'success');
    } catch (err) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast(`已复制 ${label} 到剪贴板`, 'success');
    }
}

// --- 4. SPA Tab Navigation & View Management ---
function switchTab(pageId, title, btnEl) {
    // 1. 切换 Page 显示
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });
    const targetPage = document.getElementById(pageId);
    if (targetPage) {
        targetPage.classList.add('active');
    }

    // 2. 切换 Dock 按钮高亮
    document.querySelectorAll('.dock-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    if (btnEl) {
        btnEl.classList.add('active');
    } else {
        const matchingBtn = document.querySelector(`.dock-btn[data-target="${pageId}"]`) || 
                             document.getElementById(`dock-btn-${pageId.replace('p-', '')}`);
        if (matchingBtn) matchingBtn.classList.add('active');
    }

    // 3. 更新 URL Hash (无刷新)
    const hash = pageId.replace('p-', '');
    if (window.location.hash !== `#${hash}`) {
        history.replaceState(null, null, `#${hash}`);
    }

    // 4. 页面激活回调
    if (pageId === 'p-domains') {
        loadDomainsAjax();
    } else if (pageId === 'p-add') {
        load1PanelAccounts();
    } else if (pageId === 'p-ssl') {
        loadSSLAccounts();
    }
}

// --- 5. AJAX Domains Data Loading & Rendering ---
let cachedDomainsData = {};

async function loadDomainsAjax(silent = false) {
    try {
        const res = await fetch('/api/list');
        if (!res.ok) return;
        const data = await res.json();
        cachedDomainsData = data;
        renderDomainsUI(data);
        if (!silent) {
            // 静默更新完成
        }
    } catch (e) {
        console.error('加载域名列表失败:', e);
    }
}

function renderDomainsUI(auths) {
    const domainList = Object.entries(auths || {});
    const totalCount = domainList.length;
    const authCount = domainList.filter(([k, v]) => v.auth_enabled).length;
    const sslCount = domainList.filter(([k, v]) => v.ssl_enabled).length;
    const proxyCount = domainList.filter(([k, v]) => v.proxy_enabled).length;

    // 1. 更新统计大屏
    const statTotal = document.getElementById('stat-total-domains');
    const statAuth = document.getElementById('stat-auth-count');
    const statSSL = document.getElementById('stat-ssl-count');
    const statProxy = document.getElementById('stat-proxy-count');

    if (statTotal) statTotal.textContent = totalCount;
    if (statAuth) statAuth.textContent = authCount;
    if (statSSL) statSSL.textContent = sslCount;
    if (statProxy) statProxy.textContent = proxyCount;

    // 2. 渲染卡片流与表格
    const cardGrid = document.getElementById('cardViewContainer');
    const tableBody = document.getElementById('tableBodyContainer');
    const emptyView = document.getElementById('emptyDomainView');
    const mainListContent = document.getElementById('mainListContent');

    if (totalCount === 0) {
        if (emptyView) emptyView.style.display = 'block';
        if (mainListContent) mainListContent.style.display = 'none';
        return;
    } else {
        if (emptyView) emptyView.style.display = 'none';
        if (mainListContent) mainListContent.style.display = 'block';
    }

    if (cardGrid) {
        cardGrid.innerHTML = domainList.map(([domain, auth]) => `
            <div class="domain-card" data-domain="${domain}" data-target="${auth.target_host || '127.0.0.1'}:${auth.target_port}" data-port="${auth.oauth_port}">
                <div>
                    <div class="domain-card-header">
                        <div>
                            <span class="domain-name" onclick="openDomainDetail('${domain}')" style="cursor: pointer;">
                                <span class="status-dot ${!auth.proxy_enabled ? 'offline' : ''}"></span>
                                ${domain}
                            </span>
                            <div class="domain-target">
                                <span>🎯 目标:</span>
                                <code style="background: var(--card-sec); padding: 2px 6px; border-radius: 6px; border: 1px solid var(--border-subtle);">${auth.target_host || '127.0.0.1'}:${auth.target_port}</code>
                            </div>
                        </div>
                        <span class="badge secondary" style="font-family: monospace;">:${auth.oauth_port}</span>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 8px;">
                        <div class="badges-wrap" style="margin: 0;">
                            <span class="badge ${auth.proxy_enabled ? 'success' : 'secondary'}">🔄 反代${auth.proxy_enabled ? '已开' : '已关'}</span>
                            <span class="badge ${auth.ssl_enabled ? 'success' : 'warning'}">${auth.ssl_enabled ? '🔒 SSL已开' : '⚠️ 无SSL'}</span>
                            <span class="badge ${auth.auth_enabled ? 'accent' : 'secondary'}">🛡️ 认证${auth.auth_enabled ? '已开' : '已关'}</span>
                        </div>

                        <div style="display: inline-flex; align-items: center; gap: 6px; margin-left: auto;">
                            <button class="btn secondary sm" onclick="openDomainDetail('${domain}')" style="padding: 4px 10px; font-size: 11px;">详情</button>
                            <button class="btn danger sm" onclick="deleteDomainAjax('${domain}')" style="padding: 4px 8px; font-size: 11px;">🗑️</button>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    }

    if (tableBody) {
        tableBody.innerHTML = domainList.map(([domain, auth]) => `
            <tr data-domain="${domain}" data-target="${auth.target_host || '127.0.0.1'}:${auth.target_port}" data-port="${auth.oauth_port}">
                <td>
                    <span onclick="openDomainDetail('${domain}')" style="font-weight: 700; color: var(--text); cursor: pointer; display: flex; align-items: center; gap: 6px;">
                        <span class="status-dot ${!auth.proxy_enabled ? 'offline' : ''}"></span>
                        ${domain}
                    </span>
                </td>
                <td>
                    <div class="badges-wrap">
                        <span class="badge ${auth.proxy_enabled ? 'success' : 'secondary'}">🔄 反代${auth.proxy_enabled ? '' : '关'}</span>
                        <span class="badge ${auth.ssl_enabled ? 'success' : 'warning'}">${auth.ssl_enabled ? '🔒 SSL' : '⚠️ 无SSL'}</span>
                        <span class="badge ${auth.auth_enabled ? 'accent' : 'secondary'}">🛡️ 认证${auth.auth_enabled ? '' : '关'}</span>
                    </div>
                </td>
                <td><code>${auth.target_host || '127.0.0.1'}:${auth.target_port}</code></td>
                <td><span class="badge secondary">${auth.oauth_port}</span></td>
                <td style="text-align: right;">
                    <div style="display: inline-flex; gap: 6px;">
                        <button class="btn secondary sm" onclick="openDomainDetail('${domain}')">详情</button>
                        <button class="btn danger sm" onclick="deleteDomainAjax('${domain}')">删除</button>
                    </div>
                </td>
            </tr>
        `).join('');
    }
}

// --- 6. AJAX Domain Detail Modal & Real-time Switches ---
let currentDetailDomain = '';

function openDomainDetail(domain) {
    const auth = cachedDomainsData[domain];
    if (!auth) {
        showToast('未找到该域名配置', 'error');
        return;
    }
    currentDetailDomain = domain;

    // 填充详情模态窗内容
    document.getElementById('modalDomainTitle').textContent = domain;
    document.getElementById('modalTargetHost').textContent = `${auth.target_host || '127.0.0.1'}:${auth.target_port}`;
    document.getElementById('modalClientId').textContent = auth.client_id || '';
    document.getElementById('modalClientSecret').textContent = auth.client_secret || '';
    document.getElementById('modalCookieSecret').textContent = auth.cookie_secret || '';
    document.getElementById('modalOauthPort').textContent = `:${auth.oauth_port}`;
    document.getElementById('modalContainerName').textContent = auth.container_name || '';
    document.getElementById('modalCreatedAt').textContent = auth.created_at || '';
    document.getElementById('modalNginxPre').textContent = auth.nginx_config || '# 暂无配置';

    // 填充开关状态
    const toggleProxy = document.getElementById('modalToggleProxy');
    const toggleSsl = document.getElementById('modalToggleSsl');
    const toggleAuth = document.getElementById('modalToggleAuth');

    if (toggleProxy) toggleProxy.checked = !!auth.proxy_enabled;
    if (toggleSsl) toggleSsl.checked = !!auth.ssl_enabled;
    if (toggleAuth) toggleAuth.checked = !!auth.auth_enabled;

    updateModalSwitchBadges(auth);

    // 显示模态窗
    const modal = document.getElementById('domainDetailModal');
    if (modal) modal.classList.add('active');
}

function updateModalSwitchBadges(auth) {
    const badgeProxy = document.getElementById('modalBadgeProxy');
    const badgeSsl = document.getElementById('modalBadgeSsl');
    const badgeAuth = document.getElementById('modalBadgeAuth');

    if (badgeProxy) {
        badgeProxy.className = auth.proxy_enabled ? 'badge success' : 'badge secondary';
        badgeProxy.textContent = auth.proxy_enabled ? '已开启' : '已关闭';
    }
    if (badgeSsl) {
        badgeSsl.className = auth.ssl_enabled ? 'badge success' : 'badge warning';
        badgeSsl.textContent = auth.ssl_enabled ? '已开启' : '未开启';
    }
    if (badgeAuth) {
        badgeAuth.className = auth.auth_enabled ? 'badge accent' : 'badge secondary';
        badgeAuth.textContent = auth.auth_enabled ? '已开启' : '已关闭';
    }
}

function closeDetailModal() {
    const modal = document.getElementById('domainDetailModal');
    if (modal) modal.classList.remove('active');
    currentDetailDomain = '';
}

async function handleModalToggle(feature, enabled, checkboxEl) {
    if (!currentDetailDomain) return;
    const domain = currentDetailDomain;
    checkboxEl.disabled = true;

    try {
        const formData = new FormData();
        formData.append('enabled', enabled ? 'true' : 'false');
        const res = await fetch(`/api/toggle/${domain}/${feature}`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        checkboxEl.disabled = false;

        if (data.success) {
            if (cachedDomainsData[domain]) {
                cachedDomainsData[domain][`${feature}_enabled`] = enabled;
                if (data.nginx_config) {
                    cachedDomainsData[domain]['nginx_config'] = data.nginx_config;
                    document.getElementById('modalNginxPre').textContent = data.nginx_config;
                }
                updateModalSwitchBadges(cachedDomainsData[domain]);
            }
            renderDomainsUI(cachedDomainsData);
            showToast(`${feature.toUpperCase()} 状态已更新为: ${enabled ? '开启' : '关闭'}`, 'success');
        } else {
            checkboxEl.checked = !enabled;
            showToast('操作失败: ' + data.error, 'error');
        }
    } catch (e) {
        checkboxEl.disabled = false;
        checkboxEl.checked = !enabled;
        showToast('网络通信异常', 'error');
    }
}

async function deleteDomainAjax(domain) {
    if (!confirm(`确定要彻底删除域名 ${domain} 的认证配置吗？\n此操作将同时销毁 OAuth2 容器与 Nginx 配置，不可撤销！`)) {
        return;
    }
    try {
        const res = await fetch(`/delete/${domain}`, { method: 'POST' });
        if (res.ok) {
            showToast(`已删除域名 ${domain}`, 'success');
            if (currentDetailDomain === domain) closeDetailModal();
            loadDomainsAjax();
        } else {
            showToast('删除失败，请稍后重试', 'error');
        }
    } catch (e) {
        showToast('请求失败', 'error');
    }
}

// --- 7. 日志流与实时输出 ---
let eventSource = null;
let pollTimer = null;
let lastLogId = 0;

function appendLogLine(containerId, text) {
    const logs = document.getElementById(containerId);
    if (!logs) return;
    const line = document.createElement('div');
    line.textContent = text;
    if (text.includes('失败') || text.includes('error') || text.includes('Error') || text.includes('异常') || text.includes('Failed')) {
        line.className = 'error';
    } else if (text.includes('成功') || text.includes('完成') || text.includes('绑定成功') || text.includes('🎉')) {
        line.className = 'success';
    } else if (text.startsWith('[系统]')) {
        line.className = 'system';
    } else {
        line.className = 'info';
    }
    logs.appendChild(line);
    logs.scrollTop = logs.scrollHeight;
}

function startLogStream(containerId) {
    lastLogId = 0;
    if (eventSource) eventSource.close();
    if (pollTimer) clearInterval(pollTimer);

    try {
        eventSource = new EventSource('/api/logs?last_id=0');
        eventSource.onmessage = function(event) {
            if (event.data && event.data !== 'heartbeat') {
                appendLogLine(containerId, event.data);
            }
            if (event.lastEventId) {
                lastLogId = parseInt(event.lastEventId) || lastLogId;
            }
        };
    } catch (err) {}

    pollTimer = setInterval(async () => {
        try {
            const res = await fetch(`/api/logs/poll?last_id=${lastLogId}`);
            if (res.ok) {
                const data = await res.json();
                if (data.logs && data.logs.length > 0) {
                    data.logs.forEach(entry => appendLogLine(containerId, entry.text));
                    lastLogId = data.last_id;
                }
            }
        } catch (e) {}
    }, 800);
}

function stopLogStream() {
    if (eventSource) setTimeout(() => eventSource.close(), 3000);
    if (pollTimer) setTimeout(() => clearInterval(pollTimer), 3500);
}

// --- 8. 初始化与 Hash 路由自适应 ---
document.addEventListener('DOMContentLoaded', () => {
    initTheme();

    // 根据 URL Hash 激活对应 Tab
    const hash = (window.location.hash || '').replace('#', '');
    if (hash && ['domains', 'add', 'ssl', 'settings'].includes(hash)) {
        switchTab(`p-${hash}`, hash, document.getElementById(`dock-btn-${hash}`));
    } else {
        switchTab('p-domains', '域名管理', document.getElementById('dock-btn-domains'));
    }
});
