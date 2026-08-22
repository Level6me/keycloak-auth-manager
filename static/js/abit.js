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
function updateHeaderDate() {
    const el = document.getElementById('header-date');
    if (el) {
        const now = new Date();
        const month = now.getMonth() + 1;
        const date = now.getDate();
        const days = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
        const dayName = days[now.getDay()];
        el.textContent = `${month}月${date}日 ${dayName}`;
    }
}

function switchTab(pageId, title, btnEl) {
    // 1. 切换 Header 标题
    const headerTitle = document.getElementById('header-title');
    if (headerTitle && title) {
        headerTitle.textContent = title;
    }

    // 2. 切换 Page 显示
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });
    const targetPage = document.getElementById(pageId);
    if (targetPage) {
        targetPage.classList.add('active');
    }

    // 3. 切换 Dock 按钮高亮
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

    // 4. 更新 URL Hash (无刷新)
    const hash = pageId.replace('p-', '');
    if (window.location.hash !== `#${hash}`) {
        history.replaceState(null, null, `#${hash}`);
    }

    // 5. 页面激活回调
    if (pageId === 'p-domains') {
        loadDomainsAjax();
    } else if (pageId === 'p-add') {
        load1PanelAccounts();
    } else if (pageId === 'p-ssl') {
        loadSSLAccounts();
    } else if (pageId === 'p-users') {
        const hasLoaded = usersInitialLoaded || (cachedUsersData && cachedUsersData.length > 0);
        loadUsersAjax(hasLoaded);
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
        cardGrid.innerHTML = domainList.map(([domain, auth]) => {
            const targetHost = auth.target_host || '127.0.0.1';
            const targetPort = auth.target_port || auth.port || 80;
            const targetStr = `${targetHost}:${targetPort}`;

            const proxyBadge = auth.proxy_enabled ? '<span class="badge success">🔄 反代</span>' : '';
            const sslBadge = auth.ssl_enabled ? '<span class="badge success">🔒 SSL</span>' : '';
            const authBadge = auth.auth_enabled ? '<span class="badge accent">🛡️ 认证</span>' : '';

            return `
            <div class="domain-card" data-domain="${domain}" data-target="${targetStr}" data-port="${auth.oauth_port}">
                <div>
                    <div class="domain-card-header">
                        <div>
                            <span class="domain-name" onclick="openDomainDetail('${domain}')" style="cursor: pointer;">
                                <span class="status-dot ${!auth.proxy_enabled ? 'offline' : ''}"></span>
                                ${domain}
                            </span>
                            <div class="domain-target">
                                <span>🎯 目标:</span>
                                <code style="background: var(--card-sec); padding: 2px 6px; border-radius: 6px; border: 1px solid var(--border-subtle);">${targetStr}</code>
                            </div>
                        </div>
                        <span class="badge secondary" style="font-family: monospace;">:${auth.oauth_port}</span>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 8px;">
                        <div class="badges-wrap" style="margin: 0;">
                            ${proxyBadge}
                            ${sslBadge}
                            ${authBadge}
                        </div>

                        <div style="display: inline-flex; align-items: center; gap: 6px; margin-left: auto;">
                            <button class="btn secondary sm" onclick="openDomainDetail('${domain}')" style="padding: 4px 10px; font-size: 11px;">详情</button>
                            <button class="btn danger sm" onclick="deleteDomainAjax('${domain}')" style="padding: 4px 8px; font-size: 11px;">🗑️</button>
                        </div>
                    </div>
                </div>
            </div>
            `;
        }).join('');
    }

    if (tableBody) {
        tableBody.innerHTML = domainList.map(([domain, auth]) => {
            const targetHost = auth.target_host || '127.0.0.1';
            const targetPort = auth.target_port || auth.port || 80;
            const targetStr = `${targetHost}:${targetPort}`;

            const proxyBadge = auth.proxy_enabled ? '<span class="badge success">🔄 反代</span>' : '';
            const sslBadge = auth.ssl_enabled ? '<span class="badge success">🔒 SSL</span>' : '';
            const authBadge = auth.auth_enabled ? '<span class="badge accent">🛡️ 认证</span>' : '';

            return `
            <tr data-domain="${domain}" data-target="${targetStr}" data-port="${auth.oauth_port}">
                <td>
                    <span onclick="openDomainDetail('${domain}')" style="font-weight: 700; color: var(--text); cursor: pointer; display: flex; align-items: center; gap: 6px;">
                        <span class="status-dot ${!auth.proxy_enabled ? 'offline' : ''}"></span>
                        ${domain}
                    </span>
                </td>
                <td>
                    <div class="badges-wrap">
                        ${proxyBadge}
                        ${sslBadge}
                        ${authBadge}
                    </div>
                </td>
                <td><code>${targetStr}</code></td>
                <td><span class="badge secondary">${auth.oauth_port}</span></td>
                <td style="text-align: right;">
                    <div style="display: inline-flex; gap: 6px;">
                        <button class="btn secondary sm" onclick="openDomainDetail('${domain}')">详情</button>
                        <button class="btn danger sm" onclick="deleteDomainAjax('${domain}')">删除</button>
                    </div>
                </td>
            </tr>
            `;
        }).join('');
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
    const targetHost = auth.target_host || '127.0.0.1';
    const targetPort = auth.target_port || auth.port || 80;
    document.getElementById('modalDomainTitle').textContent = domain;
    document.getElementById('modalTargetHost').textContent = `${targetHost}:${targetPort}`;
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
        formData.append('_csrf_token', (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');
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
    
    // 1. 若当前详情模态框打开的是该域名，立即关闭
    if (currentDetailDomain === domain) {
        closeDetailModal();
    }

    // 2. 乐观即时更新前端界面 (移除 DOM 行与缓存)
    if (cachedDomainsData && cachedDomainsData[domain]) {
        delete cachedDomainsData[domain];
        renderDomainsUI(cachedDomainsData);
    }
    
    showToast(`正在彻底删除域名 ${domain}...`, 'info');
    
    try {
        const res = await fetch(`/delete/${domain}`, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRF-Token': (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || ''
            }
        });
        
        let msg = `已成功删除域名 ${domain}`;
        if (res.ok) {
            try {
                const data = await res.json();
                if (data && data.msg) msg = data.msg;
            } catch (_) {}
            showToast(msg, 'success');
        } else {
            showToast('服务端状态已同步', 'info');
        }
    } catch (e) {
        console.error('删除请求异常:', e);
        showToast(`已提交删除指令: ${domain}`, 'info');
    } finally {
        // 3. 重新向后端拉取最新的真实域名列表，保证 100% 数据一致
        loadDomainsAjax(true);
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
    updateHeaderDate();

    // 1. 若本地已有持久化缓存，立刻就地秒速渲染出用户界面，达到 0ms 秒开无白屏
    if (cachedUsersData && cachedUsersData.length > 0) {
        renderUsersUI(cachedUsersData);
    }

    // 2. 页面就绪后在后台发起同步
    const isColdStartWithoutCache = (!cachedUsersData || cachedUsersData.length === 0);
    setTimeout(() => {
        loadUsersAjax(!isColdStartWithoutCache);
    }, 150);

    // 根据 URL Hash 激活对应 Tab
    const hash = (window.location.hash || '').replace('#', '');
    if (hash && ['domains', 'add', 'ssl', 'users', 'settings'].includes(hash)) {
        const titleMap = { 'domains': '总览', 'add': '添加认证', 'ssl': '证书申请', 'users': '用户管理', 'settings': '系统配置' };
        switchTab(`p-${hash}`, titleMap[hash] || hash, document.getElementById(`dock-btn-${hash}`));
    } else {
        switchTab('p-domains', '总览', document.getElementById('dock-btn-domains'));
    }
});

// --- 9. Keycloak User Management Interactive Engine (with Local Persistence & Incremental Sync) ---
let cachedUsersData = [];
try {
    const stored = localStorage.getItem('abit_cached_users');
    if (stored) {
        cachedUsersData = JSON.parse(stored) || [];
    }
} catch (e) {
    cachedUsersData = [];
}
let usersInitialLoaded = (cachedUsersData && cachedUsersData.length > 0);
let userViewMode = localStorage.getItem('abit_user_view_mode') || 'card';

function saveUsersToLocalStorage(users) {
    cachedUsersData = users || [];
    try {
        localStorage.setItem('abit_cached_users', JSON.stringify(cachedUsersData));
        localStorage.setItem('abit_users_last_synced', Date.now().toString());
    } catch (e) {}
}

function switchUserView(mode) {
    userViewMode = mode;
    localStorage.setItem('abit_user_view_mode', mode);
    const cardContainer = document.getElementById('userCardViewContainer');
    const tableContainer = document.getElementById('userTableViewContainer');
    const btnCard = document.getElementById('btnUserCardView');
    const btnTable = document.getElementById('btnUserTableView');

    if (mode === 'table') {
        if (cardContainer) cardContainer.style.display = 'none';
        if (tableContainer) tableContainer.style.display = 'block';
        if (btnTable) btnTable.classList.add('active');
        if (btnCard) btnCard.classList.remove('active');
    } else {
        if (cardContainer) cardContainer.style.display = 'grid';
        if (tableContainer) tableContainer.style.display = 'none';
        if (btnCard) btnCard.classList.add('active');
        if (btnTable) btnTable.classList.remove('active');
    }
}

async function loadUsersAjax(silent = false, force = false) {
    const loadingTip = document.getElementById('usersLoadingTip');
    const emptyTip = document.getElementById('usersEmptyTip');
    const cardContainer = document.getElementById('userCardViewContainer');
    const tableContainer = document.getElementById('userTableViewContainer');

    // 只有在本地从未获取过任何缓存数据且当前非静默时展示加载中占位提示
    const hasCache = (cachedUsersData && cachedUsersData.length > 0);
    if (!hasCache && !silent && loadingTip) {
        loadingTip.style.display = 'block';
    }

    try {
        const res = await fetch(`/api/users${force ? '?force=true' : ''}`);
        if (!res.ok) throw new Error('网络请求失败');
        const data = await res.json();
        if (loadingTip) loadingTip.style.display = 'none';

        if (data.success) {
            usersInitialLoaded = true;
            const newUsers = data.users || [];
            const oldStr = JSON.stringify(cachedUsersData);
            const newStr = JSON.stringify(newUsers);

            // 增量比较：仅当数据发生变更时才写回持久化存储并重绘 DOM
            if (oldStr !== newStr || cachedUsersData.length === 0) {
                saveUsersToLocalStorage(newUsers);
                renderUsersUI(cachedUsersData);
            }
        } else {
            if (!silent) {
                showToast('加载用户失败: ' + (data.error || '未知错误'), 'error');
            }
        }
    } catch (e) {
        if (loadingTip) loadingTip.style.display = 'none';
        if (!silent) {
            showToast('加载 Keycloak 用户列表异常', 'error');
        }
    }
}

function formatTimestamp(ts) {
    if (!ts) return '-';
    const d = new Date(ts);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const date = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${y}-${m}-${date} ${h}:${min}`;
}

function renderUsersUI(users) {
    const totalCount = (users || []).length;
    const passkeyCount = (users || []).filter(u => u.has_passkey).length;
    const activeCount = (users || []).filter(u => u.enabled).length;
    const adminCount = (users || []).filter(u => u.is_admin).length;

    // 更新统计卡片
    const statTotal = document.getElementById('stat-total-users');
    const statPasskey = document.getElementById('stat-passkey-users');
    const statActive = document.getElementById('stat-active-users');
    const statAdmin = document.getElementById('stat-admin-users');

    if (statTotal) statTotal.textContent = totalCount;
    if (statPasskey) statPasskey.textContent = passkeyCount;
    if (statActive) statActive.textContent = activeCount;
    if (statAdmin) statAdmin.textContent = adminCount;

    const cardGrid = document.getElementById('userCardViewContainer');
    const tableBody = document.getElementById('userTableBodyContainer');
    const emptyView = document.getElementById('usersEmptyTip');

    if (totalCount === 0) {
        if (cardGrid) cardGrid.style.display = 'none';
        const tableContainer = document.getElementById('userTableViewContainer');
        if (tableContainer) tableContainer.style.display = 'none';
        if (emptyView) emptyView.style.display = 'block';
        return;
    }

    if (emptyView) emptyView.style.display = 'none';
    switchUserView(userViewMode);

    // 渲染卡片视图
    if (cardGrid) {
        cardGrid.innerHTML = '';
        users.forEach(u => {
            const card = document.createElement('div');
            card.className = 'domain-card';
            card.setAttribute('data-username', u.username || '');
            card.setAttribute('data-email', u.email || '');

            let passkeyBadge = '';
            if (u.has_passkey) {
                passkeyBadge = `<span class="badge success" title="已注册 ${u.passkey_count} 个 Passkey 硬件/生物凭据">🔑 Passkey (${u.passkey_count})</span>`;
            } else if (u.required_actions && u.required_actions.includes('webauthn-register-passwordless')) {
                passkeyBadge = `<span class="badge warning" title="下次登录将引导绑定 Passkey">⏳ 待绑定 Passkey</span>`;
            } else if (u.has_password) {
                passkeyBadge = `<span class="badge secondary" title="仅配置密码登录">🔒 密码登录</span>`;
            } else {
                passkeyBadge = `<span class="badge secondary">未设凭据</span>`;
            }

            let siteBadge = '';
            if (u.all_sites_access) {
                siteBadge = `<span class="badge success" title="可访问系统全部受保护站点">🌐 全部站点</span>`;
            } else {
                const sCount = (u.allowed_sites || []).length;
                siteBadge = `<span class="badge warning" title="仅允许访问指定的 ${sCount} 个站点">🔒 授权站点 (${sCount})</span>`;
            }

            const adminBadge = u.is_admin ? `<span class="badge accent">👑 管理员</span>` : `<span class="badge secondary">👤 普通用户</span>`;
            const statusDot = u.enabled ? `<span class="status-dot"></span>` : `<span class="status-dot offline"></span>`;

            card.innerHTML = `
                <div>
                    <div class="domain-card-header">
                        <div>
                            <span class="domain-name">
                                ${statusDot}
                                ${u.username}
                            </span>
                            <div class="domain-target">
                                <span>📧 邮箱:</span>
                                <span style="color: var(--text); font-weight: 500;">${u.email || '<span style="color:var(--text-sec); font-style:italic;">未绑定邮箱</span>'}</span>
                            </div>
                        </div>
                        <label class="switch" title="一键切换启用/停用">
                            <input type="checkbox" ${u.enabled ? 'checked' : ''} onchange="toggleUserStatus('${u.id}', this.checked, this)">
                            <span class="slider"></span>
                        </label>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 10px;">
                        <div class="badges-wrap" style="margin: 0;">
                            ${adminBadge}
                            ${passkeyBadge}
                            ${siteBadge}
                        </div>

                        <div style="display: inline-flex; align-items: center; gap: 5px; margin-left: auto;">
                            <button class="btn secondary sm" onclick="openResetUserModal('${u.id}', '${u.username}', ${u.has_passkey})" style="padding: 4px 7px; font-size: 11px;" title="重置密码或重新绑定 Passkey">🔐 凭据</button>
                            <button class="btn secondary sm" onclick="openUserSitesModal('${u.id}', '${u.username}')" style="padding: 4px 7px; font-size: 11px;" title="配置可访问站点权限">🌐 站点</button>
                            <button class="btn secondary sm" onclick="openUserRolesModal('${u.id}', '${u.username}')" style="padding: 4px 7px; font-size: 11px;" title="分配角色权限">🛡️ 角色</button>
                            <button class="btn danger sm" onclick="deleteUserAjax('${u.id}', '${u.username}')" style="padding: 4px 7px; font-size: 11px;" title="删除用户">🗑️</button>
                        </div>
                    </div>

                    <div style="margin-top: 8px; font-size: 11px; color: var(--text-sec); display: flex; justify-content: space-between;">
                        <span>创建时间:</span>
                        <span>${formatTimestamp(u.created_timestamp)}</span>
                    </div>
                </div>
            `;
            cardGrid.appendChild(card);
        });
    }

    // 渲染表格视图
    if (tableBody) {
        tableBody.innerHTML = '';
        users.forEach(u => {
            const tr = document.createElement('tr');
            tr.setAttribute('data-username', u.username || '');
            tr.setAttribute('data-email', u.email || '');

            let passkeyBadge = '';
            if (u.has_passkey) {
                passkeyBadge = `<span class="badge success">🔑 Passkey (${u.passkey_count})</span>`;
            } else if (u.required_actions && u.required_actions.includes('webauthn-register-passwordless')) {
                passkeyBadge = `<span class="badge warning">⏳ 待绑定 Passkey</span>`;
            } else if (u.has_password) {
                passkeyBadge = `<span class="badge secondary">🔒 密码登录</span>`;
            } else {
                passkeyBadge = `<span class="badge secondary">未设凭据</span>`;
            }

            let siteBadge = '';
            if (u.all_sites_access) {
                siteBadge = `<span class="badge success">🌐 全部站点</span>`;
            } else {
                const sCount = (u.allowed_sites || []).length;
                siteBadge = `<span class="badge warning">🔒 授权站点 (${sCount})</span>`;
            }

            const adminBadge = u.is_admin ? `<span class="badge accent">👑 管理员</span>` : `<span class="badge secondary">👤 普通用户</span>`;
            const statusDot = u.enabled ? `<span class="status-dot"></span>` : `<span class="status-dot offline"></span>`;

            tr.innerHTML = `
                <td>
                    <div style="display: flex; align-items: center; gap: 8px; font-weight: 700;">
                        ${statusDot}
                        <span>${u.username}</span>
                    </div>
                </td>
                <td>
                    <span style="font-size: 13px; color: ${u.email ? 'var(--text)' : 'var(--text-sec)'};">${u.email || '-'}</span>
                </td>
                <td>
                    <div class="badges-wrap" style="margin: 0;">
                        ${passkeyBadge}
                    </div>
                </td>
                <td>
                    <div class="badges-wrap" style="margin: 0;">
                        ${siteBadge}
                    </div>
                </td>
                <td>
                    <div class="badges-wrap" style="margin: 0;">
                        ${adminBadge}
                    </div>
                </td>
                <td style="font-size: 12px; color: var(--text-sec); font-family: monospace;">
                    ${formatTimestamp(u.created_timestamp)}
                </td>
                <td>
                    <label class="switch" style="transform: scale(0.85); transform-origin: left center;">
                        <input type="checkbox" ${u.enabled ? 'checked' : ''} onchange="toggleUserStatus('${u.id}', this.checked, this)">
                        <span class="slider"></span>
                    </label>
                </td>
                <td style="text-align: right;">
                    <div style="display: inline-flex; align-items: center; gap: 4px;">
                        <button class="btn secondary sm" onclick="openResetUserModal('${u.id}', '${u.username}', ${u.has_passkey})" style="padding: 4px 7px; font-size: 11px;">🔐 凭据</button>
                        <button class="btn secondary sm" onclick="openUserSitesModal('${u.id}', '${u.username}')" style="padding: 4px 7px; font-size: 11px;">🌐 站点</button>
                        <button class="btn secondary sm" onclick="openUserRolesModal('${u.id}', '${u.username}')" style="padding: 4px 7px; font-size: 11px;">🛡️ 角色</button>
                        <button class="btn danger sm" onclick="deleteUserAjax('${u.id}', '${u.username}')" style="padding: 4px 7px; font-size: 11px;">🗑️</button>
                    </div>
                </td>
            `;
            tableBody.appendChild(tr);
        });
    }
}

function filterUsers(query) {
    const q = (query || '').toLowerCase().trim();
    const cards = document.querySelectorAll('#userCardViewContainer .domain-card');
    const rows = document.querySelectorAll('#userTableBodyContainer tr');

    cards.forEach(card => {
        const u = (card.getAttribute('data-username') || '').toLowerCase();
        const e = (card.getAttribute('data-email') || '').toLowerCase();
        if (!q || u.includes(q) || e.includes(q)) {
            card.style.display = 'flex';
        } else {
            card.style.display = 'none';
        }
    });

    rows.forEach(row => {
        const u = (row.getAttribute('data-username') || '').toLowerCase();
        const e = (row.getAttribute('data-email') || '').toLowerCase();
        if (!q || u.includes(q) || e.includes(q)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

// --- Add User Modal Logic ---
function openAddUserModal() {
    const modal = document.getElementById('userAddModal');
    if (modal) {
        document.getElementById('formAddUser').reset();
        document.getElementById('add_user_require_passkey').checked = true;
        modal.classList.add('active');
        setTimeout(() => document.getElementById('add_user_name').focus(), 100);
    }
}

function closeAddUserModal() {
    const modal = document.getElementById('userAddModal');
    if (modal) modal.classList.remove('active');
}

function generateRandomUserPwd() {
    const chars = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%';
    let pwd = '';
    for (let i = 0; i < 14; i++) {
        pwd += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    const input = document.getElementById('add_user_pwd');
    if (input) {
        input.value = pwd;
        copyToClipboard(pwd, '随机初始密码');
    }
}

async function submitAddUser(e) {
    if (e) e.preventDefault();
    const btn = document.getElementById('btnSubmitAddUser');
    const username = (document.getElementById('add_user_name').value || '').trim();
    const email = (document.getElementById('add_user_email').value || '').trim();
    const pwd = document.getElementById('add_user_pwd').value;
    const reqPasskey = document.getElementById('add_user_require_passkey').checked;
    const isAdmin = document.getElementById('add_user_is_admin').checked;
    const temporary = document.getElementById('add_user_temporary').checked;

    if (!username) {
        showToast('请输入用户名', 'warning');
        return;
    }

    btn.disabled = true;
    btn.textContent = '正在创建中...';

    const formData = new FormData();
    formData.append('username', username);
    formData.append('email', email);
    formData.append('password', pwd);
    formData.append('require_passkey', reqPasskey ? 'true' : 'false');
    formData.append('is_admin', isAdmin ? 'true' : 'false');
    formData.append('temporary', temporary ? 'true' : 'false');
    formData.append('_csrf_token', (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');

    try {
        const res = await fetch('/api/users/create', { method: 'POST', body: formData });
        const data = await res.json();
        btn.disabled = false;
        btn.textContent = '🚀 确认创建用户';

        if (data.success) {
            showToast(`用户 ${username} 创建成功！`, 'success');
            closeAddUserModal();
            loadUsersAjax(true, true);
        } else {
            showToast('创建失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        btn.disabled = false;
        btn.textContent = '🚀 确认创建用户';
        showToast('网络请求发生异常', 'error');
    }
}

// --- Toggle User Status Logic (with Optimistic UI & Local Persistence) ---
async function toggleUserStatus(userId, enabled, switchEl) {
    if (switchEl) switchEl.disabled = true;

    // 1. 乐观即时更新本地缓存与 UI
    const targetUser = cachedUsersData.find(u => u.id === userId);
    if (targetUser) {
        targetUser.enabled = enabled;
        saveUsersToLocalStorage(cachedUsersData);
        renderUsersUI(cachedUsersData);
    }

    const formData = new FormData();
    formData.append('enabled', enabled ? 'true' : 'false');
    formData.append('_csrf_token', (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');

    try {
        const res = await fetch(`/api/users/${userId}/toggle`, { method: 'POST', body: formData });
        const data = await res.json();
        if (switchEl) switchEl.disabled = false;

        if (data.success) {
            showToast(`用户状态已切换为: ${enabled ? '正常激活' : '已停用'}`, 'success');
            loadUsersAjax(true, true);
        } else {
            // 回滚乐观更新
            if (targetUser) {
                targetUser.enabled = !enabled;
                saveUsersToLocalStorage(cachedUsersData);
                renderUsersUI(cachedUsersData);
            }
            if (switchEl) switchEl.checked = !enabled;
            showToast('操作失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        if (targetUser) {
            targetUser.enabled = !enabled;
            saveUsersToLocalStorage(cachedUsersData);
            renderUsersUI(cachedUsersData);
        }
        if (switchEl) {
            switchEl.disabled = false;
            switchEl.checked = !enabled;
        }
        showToast('网络请求异常', 'error');
    }
}

// --- Delete User Logic (with Optimistic UI & Local Persistence) ---
async function deleteUserAjax(userId, username) {
    if (!confirm(`确定要彻底删除用户【${username}】吗？\n删除后该用户绑定的所有 Passkey 凭据与权限将被永久清除，不可撤销！`)) {
        return;
    }

    // 1. 乐观即时移除本地缓存并重绘
    const backupUsers = [...cachedUsersData];
    cachedUsersData = cachedUsersData.filter(u => u.id !== userId);
    saveUsersToLocalStorage(cachedUsersData);
    renderUsersUI(cachedUsersData);

    showToast(`正在删除用户 ${username}...`, 'info');

    const formData = new FormData();
    formData.append('_csrf_token', (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');

    try {
        const res = await fetch(`/api/users/${userId}/delete`, { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
            showToast(`用户 ${username} 已成功删除`, 'success');
            loadUsersAjax(true, true);
        } else {
            // 回滚
            cachedUsersData = backupUsers;
            saveUsersToLocalStorage(cachedUsersData);
            renderUsersUI(cachedUsersData);
            showToast('删除失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        cachedUsersData = backupUsers;
        saveUsersToLocalStorage(cachedUsersData);
        renderUsersUI(cachedUsersData);
        showToast('网络通信异常', 'error');
    }
}

// --- Reset User Credentials Modal Logic ---
function openResetUserModal(userId, username, hasPasskey) {
    const modal = document.getElementById('userResetModal');
    if (!modal) return;
    document.getElementById('formResetUser').reset();
    document.getElementById('reset_user_id').value = userId;
    document.getElementById('reset_user_name_display').textContent = username;
    document.getElementById('reset_require_passkey').checked = false;
    document.getElementById('reset_clear_passkey').checked = false;
    modal.classList.add('active');
}

function closeResetUserModal() {
    const modal = document.getElementById('userResetModal');
    if (modal) modal.classList.remove('active');
}

function generateRandomResetPwd() {
    const chars = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%';
    let pwd = '';
    for (let i = 0; i < 14; i++) {
        pwd += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    const input = document.getElementById('reset_new_pwd');
    if (input) {
        input.value = pwd;
        copyToClipboard(pwd, '随机重置密码');
    }
}

async function submitResetUser(e) {
    if (e) e.preventDefault();
    const btn = document.getElementById('btnSubmitResetUser');
    const userId = document.getElementById('reset_user_id').value;
    const newPwd = document.getElementById('reset_new_pwd').value;
    const reqPasskey = document.getElementById('reset_require_passkey').checked;
    const clearPasskey = document.getElementById('reset_clear_passkey').checked;

    if (!newPwd && !reqPasskey && !clearPasskey) {
        showToast('未选择任何修改操作', 'info');
        closeResetUserModal();
        return;
    }

    btn.disabled = true;
    btn.textContent = '正在保存中...';

    const formData = new FormData();
    formData.append('new_password', newPwd);
    formData.append('require_passkey', reqPasskey ? 'true' : 'false');
    formData.append('clear_passkey', clearPasskey ? 'true' : 'false');
    formData.append('_csrf_token', (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');

    try {
        const res = await fetch(`/api/users/${userId}/reset_password`, { method: 'POST', body: formData });
        const data = await res.json();
        btn.disabled = false;
        btn.textContent = '💾 保存并应用';

        if (data.success) {
            showToast('用户凭据设置已成功应用！', 'success');
            closeResetUserModal();
            loadUsersAjax(true, true);
        } else {
            showToast('重置失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        btn.disabled = false;
        btn.textContent = '💾 保存并应用';
        showToast('网络请求异常', 'error');
    }
}

// --- User Roles Modal Logic ---
async function openUserRolesModal(userId, username) {
    const modal = document.getElementById('userRolesModal');
    if (!modal) return;
    document.getElementById('roles_user_id').value = userId;
    document.getElementById('roles_user_name_display').textContent = username;
    const container = document.getElementById('rolesCheckboxContainer');
    container.innerHTML = '<div style="text-align: center; color: var(--text-sec); font-size: 12px; padding: 10px;">正在加载角色列表...</div>';
    modal.classList.add('active');

    try {
        const [rolesRes, usersRes] = await Promise.all([
            fetch('/api/roles').then(r => r.json()),
            fetch('/api/users').then(r => r.json())
        ]);

        if (rolesRes.success) {
            const userObj = (usersRes.users || []).find(u => u.id === userId);
            const userRoles = userObj ? (userObj.roles || []) : [];

            container.innerHTML = '';
            rolesRes.roles.forEach(r => {
                const isChecked = userRoles.includes(r.name);
                const isDefault = (r.name === 'default-roles-master');
                const row = document.createElement('div');
                row.className = 'setting-row';
                row.style.padding = '6px 0';
                row.innerHTML = `
                    <div class="setting-info">
                        <span class="setting-label" style="font-size: 13px;">${r.name === 'admin' ? '👑' : '🏷️'} ${r.name}</span>
                        <span class="setting-desc" style="font-size: 11px;">${r.description || (isDefault ? '系统默认基础角色' : 'Realm 角色')}</span>
                    </div>
                    <label class="switch">
                        <input type="checkbox" value="${r.name}" ${isChecked ? 'checked' : ''} ${isDefault ? 'disabled' : ''}>
                        <span class="slider"></span>
                    </label>
                `;
                container.appendChild(row);
            });
        } else {
            container.innerHTML = `<div style="color: var(--danger); font-size: 12px;">加载失败: ${rolesRes.error}</div>`;
        }
    } catch (e) {
        container.innerHTML = '<div style="color: var(--danger); font-size: 12px;">加载角色列表发生异常</div>';
    }
}

function closeUserRolesModal() {
    const modal = document.getElementById('userRolesModal');
    if (modal) modal.classList.remove('active');
}

async function submitUserRoles(e) {
    if (e) e.preventDefault();
    const btn = document.getElementById('btnSubmitUserRoles');
    const userId = document.getElementById('roles_user_id').value;
    const container = document.getElementById('rolesCheckboxContainer');
    const checkboxes = container.querySelectorAll('input[type="checkbox"]:checked');
    const selectedRoles = Array.from(checkboxes).map(cb => cb.value);

    btn.disabled = true;
    btn.textContent = '正在更新权限...';

    const formData = new FormData();
    formData.append('roles', selectedRoles.join(','));
    formData.append('_csrf_token', (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');

    try {
        const res = await fetch(`/api/users/${userId}/roles`, { method: 'POST', body: formData });
        const data = await res.json();
        btn.disabled = false;
        btn.textContent = '💾 更新角色权限';

        if (data.success) {
            showToast('用户角色权限已成功更新！', 'success');
            closeUserRolesModal();
            loadUsersAjax(true, true);
        } else {
            showToast('更新失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        btn.disabled = false;
        btn.textContent = '💾 更新角色权限';
        showToast('网络请求发生异常', 'error');
    }
}

// --- User Sites Permissions Modal Logic ---
let cachedDomainsForSitesModal = [];

async function openUserSitesModal(userId, username) {
    const modal = document.getElementById('userSitesModal');
    if (!modal) return;
    document.getElementById('sites_user_id').value = userId;
    document.getElementById('sites_user_name_display').textContent = username;

    const container = document.getElementById('sitesCheckboxContainer');
    container.innerHTML = '<div style="text-align: center; color: var(--text-sec); font-size: 12px; padding: 12px;">正在加载受保护站点列表...</div>';
    modal.classList.add('active');

    // 查找当前用户的站点权限配置
    const userObj = (cachedUsersData || []).find(u => u.id === userId);
    const allSites = userObj ? Boolean(userObj.all_sites_access) : true;
    const allowedSites = userObj ? (userObj.allowed_sites || ['*']) : ['*'];

    const allowAllCheckbox = document.getElementById('sites_allow_all');
    if (allowAllCheckbox) {
        allowAllCheckbox.checked = allSites;
    }
    toggleSitesAllowAll(allSites);

    try {
        const res = await fetch('/api/list');
        if (!res.ok) throw new Error('获取站点列表失败');
        const domainsData = await res.json();
        cachedDomainsForSitesModal = Object.keys(domainsData || {});

        container.innerHTML = '';
        if (cachedDomainsForSitesModal.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: var(--text-sec); font-size: 12px; padding: 12px;">系统内暂无配置受保护的域名</div>';
            return;
        }

        cachedDomainsForSitesModal.forEach(domain => {
            const isChecked = allSites || allowedSites.includes(domain);
            const row = document.createElement('div');
            row.className = 'setting-row';
            row.style.padding = '6px 8px';
            row.style.background = 'var(--card)';
            row.style.borderRadius = '8px';
            row.innerHTML = `
                <div class="setting-info" style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 14px;">🌐</span>
                    <span class="setting-label" style="font-size: 13px; font-family: monospace;">${domain}</span>
                </div>
                <label class="switch" style="transform: scale(0.85); transform-origin: right center;">
                    <input type="checkbox" class="site-domain-checkbox" value="${domain}" ${isChecked ? 'checked' : ''} ${allSites ? 'disabled' : ''}>
                    <span class="slider"></span>
                </label>
            `;
            container.appendChild(row);
        });
    } catch (err) {
        container.innerHTML = `<div style="color: var(--danger); font-size: 12px; padding: 12px; text-align: center;">加载站点列表异常: ${err.message}</div>`;
    }
}

function closeUserSitesModal() {
    const modal = document.getElementById('userSitesModal');
    if (modal) modal.classList.remove('active');
}

function toggleSitesAllowAll(allowAll) {
    const customArea = document.getElementById('sitesCustomSelectionArea');
    const checkboxes = document.querySelectorAll('.site-domain-checkbox');
    if (customArea) {
        customArea.style.opacity = allowAll ? '0.45' : '1';
        customArea.style.pointerEvents = allowAll ? 'none' : 'auto';
    }
    checkboxes.forEach(cb => {
        cb.disabled = allowAll;
        if (allowAll) cb.checked = true;
    });
}

function toggleAllSitesCheckboxes(checked) {
    const checkboxes = document.querySelectorAll('.site-domain-checkbox');
    checkboxes.forEach(cb => {
        if (!cb.disabled) cb.checked = checked;
    });
}

async function submitUserSites(e) {
    if (e) e.preventDefault();
    const btn = document.getElementById('btnSubmitUserSites');
    const userId = document.getElementById('sites_user_id').value;
    const allowAll = document.getElementById('sites_allow_all').checked;

    let sitesParam = '*';
    let newAllowedSites = ['*'];
    if (!allowAll) {
        const checkboxes = document.querySelectorAll('.site-domain-checkbox:checked');
        const selectedDomains = Array.from(checkboxes).map(cb => cb.value);
        if (selectedDomains.length === 0) {
            showToast('未选择任何站点，请至少勾选一个站点或开启全站授权', 'warning');
            return;
        }
        sitesParam = selectedDomains.join(',');
        newAllowedSites = selectedDomains;
    }

    // 乐观即时更新本地缓存与 UI
    const targetUser = (cachedUsersData || []).find(u => u.id === userId);
    if (targetUser) {
        targetUser.all_sites_access = allowAll;
        targetUser.allowed_sites = newAllowedSites;
        saveUsersToLocalStorage(cachedUsersData);
        renderUsersUI(cachedUsersData);
    }

    if (btn) {
        btn.disabled = true;
        btn.textContent = '正在保存权限...';
    }

    const csrfToken = (typeof getCsrfToken === 'function') ? getCsrfToken() : ((document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');
    const formData = new FormData();
    formData.append('sites', sitesParam);
    formData.append('_csrf_token', csrfToken);

    try {
        const res = await fetch(`/api/users/${userId}/sites`, { method: 'POST', body: formData });
        const data = await res.json();
        if (btn) {
            btn.disabled = false;
            btn.textContent = '💾 保存并应用权限';
        }

        if (data.success) {
            showToast('用户站点访问权限已成功应用！', 'success');
            closeUserSitesModal();
            loadUsersAjax(true, true);
        } else {
            showToast('设置失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '💾 保存并应用权限';
        }
        showToast('网络请求发生异常: ' + err.message, 'error');
    }
}

// ─── 全局模态框遮罩点击关闭与 ESC 快捷关闭 ───
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.classList.remove('active');
            }
        });
    });
    
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
        }
    });
});



