/* ==========================================================================
   Abit Design System - Modern SPA & AJAX Interactive Engine for KAM
   ========================================================================== */

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

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
    } else if (pageId === 'p-apps') {
        const hasLoaded = appsInitialLoaded || (cachedOidcClientsData && cachedOidcClientsData.length > 0);
        loadOidcClientsAjax(hasLoaded);
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

            let loginPolicyBadge = '';
            if (auth.auth_enabled) {
                if (auth.allow_passkey === false && auth.allow_password !== false) {
                    loginPolicyBadge = '<span class="badge secondary" title="该站点仅允许用户名与密码登录">🔒 仅密码</span>';
                } else if (auth.allow_password === false && auth.allow_passkey !== false) {
                    loginPolicyBadge = '<span class="badge accent" title="该站点仅允许 Passkey 认证">🔑 仅 Passkey</span>';
                } else {
                    loginPolicyBadge = '<span class="badge success" title="该站点支持 Passkey 与密码登录">🔑 Passkey+密码</span>';
                }
            }

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

                    <div style="margin: 10px 0 8px 0; display: flex; flex-wrap: wrap; gap: 6px; min-height: 24px;">
                        <div class="badges-wrap" style="margin: 0;">
                            ${proxyBadge}
                            ${sslBadge}
                            ${authBadge}
                            ${loginPolicyBadge}
                        </div>
                    </div>

                    <div class="domain-actions" style="margin-top: auto; padding-top: 10px; border-top: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; gap: 6px;">
                        <button class="btn secondary sm" onclick="openDomainDetail('${domain}')" style="flex: 1; font-size: 12px; padding: 5px 8px; text-align: center; justify-content: center;">📋 详情配置</button>
                        <button class="btn danger sm" onclick="deleteDomainAjax('${domain}')" style="font-size: 12px; padding: 5px 10px;">🗑️ 删除</button>
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

            let loginPolicyBadge = '';
            if (auth.auth_enabled) {
                if (auth.allow_passkey === false && auth.allow_password !== false) {
                    loginPolicyBadge = '<span class="badge secondary" title="该站点仅允许用户名与密码登录">🔒 仅密码</span>';
                } else if (auth.allow_password === false && auth.allow_passkey !== false) {
                    loginPolicyBadge = '<span class="badge accent" title="该站点仅允许 Passkey 认证">🔑 仅 Passkey</span>';
                } else {
                    loginPolicyBadge = '<span class="badge success" title="该站点支持 Passkey 与密码登录">🔑 Passkey+密码</span>';
                }
            }

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
                        ${loginPolicyBadge}
                    </div>
                </td>
                <td><code>${targetStr}</code></td>
                <td><span class="badge secondary">${auth.oauth_port}</span></td>
                <td style="text-align: right;">
                    <div style="display: inline-flex; gap: 6px;">
                        <button class="btn secondary sm" onclick="openDomainDetail('${domain}')">📋 详情</button>
                        <button class="btn danger sm" onclick="deleteDomainAjax('${domain}')">🗑️ 删除</button>
                    </div>
                </td>
            </tr>`;
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
    const hostInput = document.getElementById('modalInputTargetHost');
    const portInput = document.getElementById('modalInputTargetPort');
    if (hostInput) hostInput.value = targetHost;
    if (portInput) portInput.value = targetPort;
    toggleEditTarget(false);

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
    const toggleAllowPasskey = document.getElementById('modalToggleAllowPasskey');
    const toggleAllowPassword = document.getElementById('modalToggleAllowPassword');

    if (toggleProxy) toggleProxy.checked = !!auth.proxy_enabled;
    if (toggleSsl) toggleSsl.checked = !!auth.ssl_enabled;
    if (toggleAuth) toggleAuth.checked = !!auth.auth_enabled;
    if (toggleAllowPasskey) toggleAllowPasskey.checked = (auth.allow_passkey !== false);
    if (toggleAllowPassword) toggleAllowPassword.checked = (auth.allow_password !== false);

    // 填充与加载 1Panel 关联证书选择器
    populateModalDomainSslCerts(auth.ssl_id || 0);

    updateModalSwitchBadges(auth);

    // 显示模态窗
    const modal = document.getElementById('domainDetailModal');
    if (modal) modal.classList.add('active');
}

function toggleEditTarget(isEditing) {
    const displayEl = document.getElementById('modalTargetDisplay');
    const editEl = document.getElementById('modalTargetEdit');
    if (displayEl) displayEl.style.display = isEditing ? 'none' : 'flex';
    if (editEl) editEl.style.display = isEditing ? 'flex' : 'none';
}

async function saveTargetPortAjax() {
    if (!currentDetailDomain) return;
    const domain = currentDetailDomain;
    const hostInput = document.getElementById('modalInputTargetHost');
    const portInput = document.getElementById('modalInputTargetPort');
    const btn = document.getElementById('btnSaveTargetPort');

    const host = (hostInput ? hostInput.value.trim() : '') || '127.0.0.1';
    const port = parseInt(portInput ? portInput.value.trim() : '80', 10);

    if (isNaN(port) || port < 1 || port > 65535) {
        showToast('请输入合法的端口号 (1-65535)', 'warning');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ 保存中...';
    }

    try {
        const formData = new FormData();
        formData.append('target_host', host);
        formData.append('target_port', port.toString());
        formData.append('_csrf_token', (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');

        const res = await fetch(`/api/domain/${domain}/target`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (btn) {
            btn.disabled = false;
            btn.textContent = '💾 保存';
        }

        if (data.success) {
            if (cachedDomainsData[domain]) {
                cachedDomainsData[domain].target_host = host;
                cachedDomainsData[domain].target_port = port;
                cachedDomainsData[domain].port = port;
                if (data.nginx_config) {
                    cachedDomainsData[domain].nginx_config = data.nginx_config;
                    document.getElementById('modalNginxPre').textContent = data.nginx_config;
                }
            }
            document.getElementById('modalTargetHost').textContent = `${host}:${port}`;
            toggleEditTarget(false);
            renderDomainsUI(cachedDomainsData);
            showToast(`目标服务已成功更新为: ${host}:${port}`, 'success');
        } else {
            showToast('修改失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '💾 保存';
        }
        showToast('网络通信异常: ' + e.message, 'error');
    }
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
    toggleEditTarget(false);
    currentDetailDomain = '';
}

async function handleModalToggle(feature, enabled, checkboxEl) {
    if (!currentDetailDomain) return;
    const domain = currentDetailDomain;
    checkboxEl.disabled = true;

    try {
        const formData = new FormData();
        formData.append('enabled', enabled ? 'true' : 'false');
        if (feature === 'ssl') {
            const sslSelect = document.getElementById('modalSelectSslCert');
            if (sslSelect && sslSelect.value) {
                formData.append('ssl_id', sslSelect.value);
            }
        }
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
                if (data.ssl_id !== undefined) {
                    cachedDomainsData[domain].ssl_id = data.ssl_id;
                }
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
            showToast('操作失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        checkboxEl.disabled = false;
        checkboxEl.checked = !enabled;
        showToast('网络通信异常', 'error');
    }
}

async function populateModalDomainSslCerts(selectedSslId = 0) {
    const select = document.getElementById('modalSelectSslCert');
    if (!select) return;

    let certs = cachedSslCertificates || [];
    if (certs.length === 0) {
        try {
            const res = await fetch('/api/ssl/certificates');
            const data = await res.json();
            if (data.certificates) {
                cachedSslCertificates = data.certificates;
                certs = data.certificates;
            }
        } catch (e) {}
    }

    let html = '<option value="0">【未指定 / 自动匹配】</option>';
    certs.forEach(c => {
        const org = c.organization || "Let's Encrypt";
        const exp = c.expire_date ? c.expire_date.split('T')[0] : '';
        const isSel = (c.id === selectedSslId) ? 'selected' : '';
        html += `<option value="${c.id}" ${isSel}>${escapeHtml(c.primary_domain)} (${org} · ${exp})</option>`;
    });
    select.innerHTML = html;
    select.value = selectedSslId.toString();
}

async function handleDomainSslCertChange(sslId) {
    if (!currentDetailDomain) return;
    const domain = currentDetailDomain;
    const targetSslId = parseInt(sslId || '0', 10);

    const fd = new FormData();
    fd.append('ssl_id', targetSslId.toString());
    fd.append('_csrf_token', (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');

    try {
        const res = await fetch(`/api/domain/${domain}/ssl_cert`, { method: 'POST', body: fd });
        const data = await res.json();
        if (data.success) {
            if (cachedDomainsData[domain]) {
                cachedDomainsData[domain].ssl_id = targetSslId;
            }
            showToast('✅ 域名绑定证书已更新', 'success');
        } else {
            showToast('❌ 更新失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('❌ 网络通信异常', 'error');
    }
}

async function handleAuthMethodsToggle() {
    if (!currentDetailDomain) return;
    const domain = currentDetailDomain;
    const passkeyToggle = document.getElementById('modalToggleAllowPasskey');
    const passwordToggle = document.getElementById('modalToggleAllowPassword');
    const allowPasskey = passkeyToggle ? passkeyToggle.checked : true;
    const allowPassword = passwordToggle ? passwordToggle.checked : true;

    if (!allowPasskey && !allowPassword) {
        showToast('必须至少保留一种登录认证方式（Passkey 或密码）！', 'warning');
        if (passkeyToggle) passkeyToggle.checked = true;
        return;
    }

    if (passkeyToggle) passkeyToggle.disabled = true;
    if (passwordToggle) passwordToggle.disabled = true;

    try {
        const formData = new FormData();
        formData.append('allow_passkey', allowPasskey ? 'true' : 'false');
        formData.append('allow_password', allowPassword ? 'true' : 'false');
        formData.append('_csrf_token', (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');

        const res = await fetch(`/api/domain/${domain}/auth_methods`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (passkeyToggle) passkeyToggle.disabled = false;
        if (passwordToggle) passwordToggle.disabled = false;

        if (data.success) {
            if (cachedDomainsData && cachedDomainsData[domain]) {
                cachedDomainsData[domain].allow_passkey = allowPasskey;
                cachedDomainsData[domain].allow_password = allowPassword;
                if (data.nginx_config) {
                    cachedDomainsData[domain].nginx_config = data.nginx_config;
                    const pre = document.getElementById('modalNginxPre');
                    if (pre) pre.textContent = data.nginx_config;
                }
            }
            renderDomainsUI(cachedDomainsData);
            let modeDesc = 'Passkey 与密码混合模式';
            if (allowPasskey && !allowPassword) modeDesc = '仅限 Passkey (WebAuthn) 认证';
            if (allowPassword && !allowPasskey) modeDesc = '仅限账号密码认证';
            showToast(`站点 ${domain} 登录策略已成功更新为：${modeDesc}`, 'success');
        } else {
            showToast('更新失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        if (passkeyToggle) passkeyToggle.disabled = false;
        if (passwordToggle) passwordToggle.disabled = false;
        showToast('网络请求异常: ' + e.message, 'error');
    }
}


async function deleteDomainAjax(domain) {
    if (!confirm(`确定要删除域名 ${domain} 的认证配置吗？\n该操作将同时清理相关代理容器与反代配置。`)) {
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
    
    showToast(`正在删除域名 ${domain}...`, 'info');
    
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
    if (hash === 'add') {
        switchTab('p-domains', '域名管理', document.getElementById('dock-btn-domains'));
        setTimeout(() => {
            if (typeof openAddDomainModal === 'function') openAddDomainModal();
        }, 150);
    } else if (hash && ['domains', 'apps', 'ssl', 'users', 'settings'].includes(hash)) {
        const titleMap = { 'domains': '域名管理', 'apps': '应用接入', 'ssl': '证书申请', 'users': '用户管理', 'settings': '系统配置' };
        switchTab(`p-${hash}`, titleMap[hash] || hash, document.getElementById(`dock-btn-${hash}`));
    } else {
        switchTab('p-domains', '域名管理', document.getElementById('dock-btn-domains'));
    }
});


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
                passkeyBadge = `<span class="badge success" title="已注册 ${u.passkey_count} 个 Passkey 凭据">Passkey (${u.passkey_count})</span>`;
            } else if (u.required_actions && u.required_actions.includes('webauthn-register-passwordless')) {
                passkeyBadge = `<span class="badge warning" title="下次登录需注册 Passkey 凭据">待绑定 Passkey</span>`;
            } else if (u.has_password) {
                passkeyBadge = `<span class="badge secondary" title="已配置密码凭据">密码</span>`;
            } else {
                passkeyBadge = `<span class="badge secondary">未设凭据</span>`;
            }

            let siteBadge = '';
            if (u.all_sites_access) {
                siteBadge = `<span class="badge success" title="具备全部受保护站点访问权限">全局访问</span>`;
            } else {
                const sCount = (u.allowed_sites || []).length;
                siteBadge = `<span class="badge warning" title="仅限访问指定的 ${sCount} 个站点">指定站点 (${sCount})</span>`;
            }

            const adminBadge = u.is_admin ? `<span class="badge accent">管理员</span>` : `<span class="badge secondary">普通用户</span>`;
            const statusDot = u.enabled ? `<span class="status-dot"></span>` : `<span class="status-dot offline"></span>`;

            card.innerHTML = `
                <div>
                    <div class="domain-card-header">
                        <div>
                            <span class="domain-name">
                                ${statusDot}
                                ${escapeHtml(u.username)}
                            </span>
                            <div class="domain-target">
                                <span>📧 邮箱:</span>
                                <span style="color: var(--text); font-weight: 500;">${escapeHtml(u.email) || '<span style="color:var(--text-sec); font-style:italic;">未绑定邮箱</span>'}</span>
                            </div>
                        </div>
                        <label class="switch" title="切换账户启用状态">
                            <input type="checkbox" ${u.enabled ? 'checked' : ''} onchange="toggleUserStatus('${u.id}', this.checked, this)">
                            <span class="slider"></span>
                        </label>
                    </div>

                    <div style="margin: 10px 0 6px 0; display: flex; flex-wrap: wrap; gap: 6px; min-height: 24px;">
                        <div class="badges-wrap" style="margin: 0;">
                            ${adminBadge}
                            ${passkeyBadge}
                            ${siteBadge}
                        </div>
                    </div>

                    <div style="font-size: 11px; color: var(--text-sec); display: flex; justify-content: space-between; align-items: center; background: var(--card-sec); padding: 5px 10px; border-radius: 8px; border: 1px solid var(--border-subtle); margin-bottom: 8px;">
                        <span>🕒 创建时间:</span>
                        <span style="font-family: monospace;">${formatTimestamp(u.created_timestamp)}</span>
                    </div>

                    <div class="domain-actions" style="margin-top: auto; padding-top: 10px; border-top: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; gap: 6px;">
                        <button type="button" class="btn secondary sm btn-user-action" data-action="reset" data-user-id="${escapeHtml(u.id)}" data-username="${escapeHtml(u.username)}" data-has-passkey="${u.has_passkey ? 'true' : 'false'}" onclick="openResetUserModal('${u.id}', '${escapeHtml(u.username)}', ${Boolean(u.has_passkey)})" style="flex: 1; justify-content: center; font-size: 11px; padding: 5px 6px;" title="重置密码或重新绑定 Passkey">🔐 凭据</button>
                        <button type="button" class="btn secondary sm btn-user-action" data-action="sites" data-user-id="${escapeHtml(u.id)}" data-username="${escapeHtml(u.username)}" onclick="openUserSitesModal('${u.id}', '${escapeHtml(u.username)}')" style="flex: 1; justify-content: center; font-size: 11px; padding: 5px 6px;" title="配置可访问站点权限">🌐 站点</button>
                        <button type="button" class="btn secondary sm btn-user-action" data-action="roles" data-user-id="${escapeHtml(u.id)}" data-username="${escapeHtml(u.username)}" onclick="openUserRolesModal('${u.id}', '${escapeHtml(u.username)}')" style="flex: 1; justify-content: center; font-size: 11px; padding: 5px 6px;" title="分配角色权限">🛡️ 角色</button>
                        <button type="button" class="btn danger sm btn-user-action" data-action="delete" data-user-id="${escapeHtml(u.id)}" data-username="${escapeHtml(u.username)}" onclick="deleteUserAjax('${u.id}', '${escapeHtml(u.username)}')" style="font-size: 11px; padding: 5px 8px;" title="删除用户">🗑️</button>
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
                passkeyBadge = `<span class="badge success">Passkey (${u.passkey_count})</span>`;
            } else if (u.required_actions && u.required_actions.includes('webauthn-register-passwordless')) {
                passkeyBadge = `<span class="badge warning">待绑定 Passkey</span>`;
            } else if (u.has_password) {
                passkeyBadge = `<span class="badge secondary">密码</span>`;
            } else {
                passkeyBadge = `<span class="badge secondary">未设凭据</span>`;
            }

            let siteBadge = '';
            if (u.all_sites_access) {
                siteBadge = `<span class="badge success">全局访问</span>`;
            } else {
                const sCount = (u.allowed_sites || []).length;
                siteBadge = `<span class="badge warning">指定站点 (${sCount})</span>`;
            }

            const adminBadge = u.is_admin ? `<span class="badge accent">管理员</span>` : `<span class="badge secondary">普通用户</span>`;
            const statusDot = u.enabled ? `<span class="status-dot"></span>` : `<span class="status-dot offline"></span>`;

            tr.innerHTML = `
                <td>
                    <div style="display: flex; align-items: center; gap: 8px; font-weight: 700;">
                        ${statusDot}
                        <span>${escapeHtml(u.username)}</span>
                    </div>
                </td>
                <td>
                    <span style="font-size: 13px; color: ${u.email ? 'var(--text)' : 'var(--text-sec)'};">${escapeHtml(u.email) || '-'}</span>
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
                        <button type="button" class="btn secondary sm btn-user-action" data-action="reset" data-user-id="${escapeHtml(u.id)}" data-username="${escapeHtml(u.username)}" data-has-passkey="${u.has_passkey ? 'true' : 'false'}" onclick="openResetUserModal('${u.id}', '${escapeHtml(u.username)}', ${Boolean(u.has_passkey)})" style="padding: 4px 7px; font-size: 11px;">🔐 凭据</button>
                        <button type="button" class="btn secondary sm btn-user-action" data-action="sites" data-user-id="${escapeHtml(u.id)}" data-username="${escapeHtml(u.username)}" onclick="openUserSitesModal('${u.id}', '${escapeHtml(u.username)}')" style="padding: 4px 7px; font-size: 11px;">🌐 站点</button>
                        <button type="button" class="btn secondary sm btn-user-action" data-action="roles" data-user-id="${escapeHtml(u.id)}" data-username="${escapeHtml(u.username)}" onclick="openUserRolesModal('${u.id}', '${escapeHtml(u.username)}')" style="padding: 4px 7px; font-size: 11px;">🛡️ 角色</button>
                        <button type="button" class="btn danger sm btn-user-action" data-action="delete" data-user-id="${escapeHtml(u.id)}" data-username="${escapeHtml(u.username)}" onclick="deleteUserAjax('${u.id}', '${escapeHtml(u.username)}')" style="padding: 4px 7px; font-size: 11px;">🗑️</button>
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
    if (!confirm(`确定要删除用户【${username}】吗？\n删除后该用户绑定的凭据与权限将被清除。`)) {
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
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    const modal = document.getElementById('userResetModal');
    if (!modal) return;
    const form = document.getElementById('formResetUser');
    if (form) form.reset();
    document.getElementById('reset_user_id').value = userId || '';
    document.getElementById('reset_user_name_display').textContent = username || '';
    const reqPk = document.getElementById('reset_require_passkey');
    if (reqPk) reqPk.checked = false;
    const clearPk = document.getElementById('reset_clear_passkey');
    if (clearPk) clearPk.checked = false;
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

    if (btn) {
        btn.disabled = true;
        btn.textContent = '正在保存中...';
    }

    const csrfToken = (typeof getCsrfToken === 'function') ? getCsrfToken() : ((document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');
    const formData = new FormData();
    formData.append('new_password', newPwd);
    formData.append('require_passkey', reqPasskey ? 'true' : 'false');
    formData.append('clear_passkey', clearPasskey ? 'true' : 'false');
    formData.append('_csrf_token', csrfToken);

    try {
        const res = await fetch(`/api/users/${userId}/reset_password`, { method: 'POST', body: formData });
        const data = await res.json();
        if (btn) {
            btn.disabled = false;
            btn.textContent = '💾 保存并应用';
        }

        if (data.success) {
            showToast('用户凭据设置已成功应用！', 'success');
            closeResetUserModal();
            loadUsersAjax(true, true);
        } else {
            showToast('重置失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '💾 保存并应用';
        }
        showToast('网络请求异常: ' + err.message, 'error');
    }
}

// --- User Roles Modal Logic ---
async function openUserRolesModal(userId, username) {
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    const modal = document.getElementById('userRolesModal');
    if (!modal) return;
    document.getElementById('roles_user_id').value = userId || '';
    document.getElementById('roles_user_name_display').textContent = username || '';
    const container = document.getElementById('rolesCheckboxContainer');
    if (container) {
        container.innerHTML = '<div style="text-align: center; color: var(--text-sec); font-size: 12px; padding: 10px;">正在加载角色列表...</div>';
    }
    modal.classList.add('active');

    try {
        const userObj = (cachedUsersData || []).find(u => u.id === userId);
        const userRoles = userObj ? (userObj.roles || []) : [];

        const rolesRes = await fetch('/api/roles').then(r => r.json());

        if (rolesRes && rolesRes.success && Array.isArray(rolesRes.roles)) {
            container.innerHTML = '';
            rolesRes.roles.forEach(r => {
                const isChecked = userRoles.includes(r.name);
                const isDefault = (r.name === 'default-roles-master');
                const row = document.createElement('div');
                row.className = 'setting-row';
                row.style.padding = '6px 0';
                row.innerHTML = `
                    <div class="setting-info">
                        <span class="setting-label" style="font-size: 13px;">${r.name === 'admin' ? '👑' : '🏷️'} ${escapeHtml(r.name)}</span>
                        <span class="setting-desc" style="font-size: 11px;">${escapeHtml(r.description || (isDefault ? '系统默认基础角色' : 'Realm 角色'))}</span>
                    </div>
                    <label class="switch">
                        <input type="checkbox" value="${escapeHtml(r.name)}" ${isChecked ? 'checked' : ''} ${isDefault ? 'disabled' : ''}>
                        <span class="slider"></span>
                    </label>
                `;
                container.appendChild(row);
            });
        } else {
            container.innerHTML = `<div style="color: var(--danger); font-size: 12px; padding: 8px; text-align: center;">加载失败: ${(rolesRes && rolesRes.error) || '未知错误'}</div>`;
        }
    } catch (e) {
        if (container) {
            container.innerHTML = '<div style="color: var(--danger); font-size: 12px; padding: 8px; text-align: center;">加载角色列表发生异常</div>';
        }
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

    if (btn) {
        btn.disabled = true;
        btn.textContent = '正在更新权限...';
    }

    const csrfToken = (typeof getCsrfToken === 'function') ? getCsrfToken() : ((document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');
    const formData = new FormData();
    formData.append('roles', selectedRoles.join(','));
    formData.append('_csrf_token', csrfToken);

    try {
        const res = await fetch(`/api/users/${userId}/roles`, { method: 'POST', body: formData });
        const data = await res.json();
        if (btn) {
            btn.disabled = false;
            btn.textContent = '💾 更新角色权限';
        }

        if (data.success) {
            showToast('用户角色权限已成功更新！', 'success');
            closeUserRolesModal();
            loadUsersAjax(true, true);
        } else {
            showToast('更新失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '💾 更新角色权限';
        }
        showToast('网络请求发生异常: ' + err.message, 'error');
    }
}

// --- User Sites Permissions Modal Logic ---
let cachedDomainsForSitesModal = [];

async function openUserSitesModal(userId, username) {
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    const modal = document.getElementById('userSitesModal');
    if (!modal) return;
    document.getElementById('sites_user_id').value = userId || '';
    document.getElementById('sites_user_name_display').textContent = username || '';

    const container = document.getElementById('sitesCheckboxContainer');
    if (container) {
        container.innerHTML = '<div style="text-align: center; color: var(--text-sec); font-size: 12px; padding: 12px;">正在加载受保护站点列表...</div>';
    }
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

    const renderSiteCheckboxes = (domains) => {
        if (!container) return;
        container.innerHTML = '';
        if (!domains || domains.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: var(--text-sec); font-size: 12px; padding: 12px;">系统内暂无配置受保护的域名</div>';
            return;
        }

        domains.forEach(domain => {
            const isChecked = allSites || allowedSites.includes(domain);
            const row = document.createElement('div');
            row.className = 'setting-row';
            row.style.padding = '6px 8px';
            row.style.background = 'var(--card)';
            row.style.borderRadius = '8px';
            row.innerHTML = `
                <div class="setting-info" style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 14px;">🌐</span>
                    <span class="setting-label" style="font-size: 13px; font-family: monospace;">${escapeHtml(domain)}</span>
                </div>
                <label class="switch" style="transform: scale(0.85); transform-origin: right center;">
                    <input type="checkbox" class="site-domain-checkbox" value="${escapeHtml(domain)}" ${isChecked ? 'checked' : ''} ${allSites ? 'disabled' : ''}>
                    <span class="slider"></span>
                </label>
            `;
            container.appendChild(row);
        });
    };

    let domainsList = Object.keys(cachedDomainsData || {});
    if (domainsList.length === 0 && cachedDomainsForSitesModal.length > 0) {
        domainsList = cachedDomainsForSitesModal;
    }
    if (domainsList.length > 0) {
        renderSiteCheckboxes(domainsList);
    }

    try {
        const res = await fetch('/api/list');
        if (res.ok) {
            const domainsData = await res.json();
            cachedDomainsData = domainsData || {};
            cachedDomainsForSitesModal = Object.keys(domainsData || {});
            renderSiteCheckboxes(cachedDomainsForSitesModal);
        }
    } catch (err) {
        if (domainsList.length === 0 && container) {
            container.innerHTML = `<div style="color: var(--danger); font-size: 12px; padding: 12px; text-align: center;">加载站点列表异常: ${err.message}</div>`;
        }
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

function openAddDomainModal() {
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    const modal = document.getElementById('addDomainModal');
    if (!modal) return;
    const termWrap = document.getElementById('addTerminalWrap');
    if (termWrap) termWrap.style.display = 'none';
    const form = document.getElementById('authAddForm');
    if (form) {
        form.reset();
        if (typeof selectAddTargetType === 'function') selectAddTargetType('local');
        if (typeof toggleAddSSLSection === 'function') toggleAddSSLSection(false);
    }
    if (typeof loadCloudflareZones === 'function') loadCloudflareZones();
    if (typeof load1PanelAccounts === 'function') load1PanelAccounts();
    modal.classList.add('active');
}

function closeAddDomainModal() {
    const modal = document.getElementById('addDomainModal');
    if (modal) modal.classList.remove('active');
    if (typeof stopLogStream === 'function') stopLogStream();
}

// ─── 显式暴露全局函数，确保无论在任何内联或异步上下文中均 100% 可用 ───
window.openAddDomainModal = openAddDomainModal;
window.closeAddDomainModal = closeAddDomainModal;
window.openResetUserModal = openResetUserModal;
window.closeResetUserModal = closeResetUserModal;
window.openUserSitesModal = openUserSitesModal;
window.closeUserSitesModal = closeUserSitesModal;
window.openUserRolesModal = openUserRolesModal;
window.closeUserRolesModal = closeUserRolesModal;
window.openAddUserModal = openAddUserModal;
window.closeAddUserModal = closeAddUserModal;
window.deleteUserAjax = deleteUserAjax;
window.loadUsersAjax = loadUsersAjax;
window.switchUserView = switchUserView;
window.filterUsers = filterUsers;
window.handleAuthMethodsToggle = handleAuthMethodsToggle;
window.openDomainDetail = openDomainDetail;
window.closeDetailModal = closeDetailModal;
window.handleModalToggle = handleModalToggle;


// ─── 全局事件委托：监听用户管理操作按钮点击，杜绝 DOM 重绘丢失或内联调用偶发无响应 ───
document.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-user-action');
    if (!btn) return;

    e.preventDefault();
    e.stopPropagation();

    const action = btn.dataset.action;
    const userId = btn.dataset.userId;
    const username = btn.dataset.username;
    const hasPasskey = btn.dataset.hasPasskey === 'true';

    if (!userId) return;

    if (action === 'reset') {
        openResetUserModal(userId, username, hasPasskey);
    } else if (action === 'sites') {
        openUserSitesModal(userId, username);
    } else if (action === 'roles') {
        openUserRolesModal(userId, username);
    } else if (action === 'delete') {
        deleteUserAjax(userId, username);
    }
});

// ─── 弹窗激活状态与背景页面滚动锁定同步（防止背景上下滑动穿透）───
function syncModalScrollLock() {
    const hasActiveModal = !!document.querySelector('.modal-overlay.active');
    if (hasActiveModal) {
        document.body.classList.add('modal-open');
        document.documentElement.classList.add('modal-open');
    } else {
        document.body.classList.remove('modal-open');
        document.documentElement.classList.remove('modal-open');
    }
}
window.syncModalScrollLock = syncModalScrollLock;

// ─── 全局模态框遮罩点击关闭、ESC 快捷关闭与背景滚动锁定 ───
document.addEventListener('DOMContentLoaded', () => {
    // 1. 初始化 MutationObserver 监听所有模态弹窗的 class 变化，自动触发页面滚动锁定/解锁
    const modalObserver = new MutationObserver(() => {
        syncModalScrollLock();
    });

    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        modalObserver.observe(overlay, { attributes: true, attributeFilter: ['class'] });

        // 点击遮罩空白区域关闭弹窗
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.classList.remove('active');
            }
        });

        // 阻止遮罩空白区域的触摸滑动穿透到底层页面
        overlay.addEventListener('touchmove', (e) => {
            if (e.target === overlay) {
                e.preventDefault();
            }
        }, { passive: false });
    });
    
    // ESC 键关闭弹窗
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
        }
    });

    // 初始状态同步一次
    syncModalScrollLock();
});


// ═════════════════════════════════════════════════════════════════════
// ─── 8. OIDC 客户端应用接入管理 (App Management) ───
// ═════════════════════════════════════════════════════════════════════
let cachedOidcClientsData = [];
let cachedOidcEndpoints = null;
let appsInitialLoaded = false;
let currentGuideClient = null;

async function loadOidcClientsAjax(silent = false) {
    const loadingTip = document.getElementById('appsLoadingTip');
    const emptyTip = document.getElementById('appsEmptyTip');
    const container = document.getElementById('appsCardContainer');

    if (!silent && loadingTip) loadingTip.style.display = 'block';

    try {
        const res = await fetch('/api/oidc/clients');
        const data = await res.json();

        if (loadingTip) loadingTip.style.display = 'none';

        if (data.success && Array.isArray(data.clients)) {
            cachedOidcClientsData = data.clients;
            cachedOidcEndpoints = data.endpoints || null;
            appsInitialLoaded = true;
            renderOidcClients();
            updateOidcStats();
        } else {
            if (!silent) showToast(data.error || '加载应用列表失败', 'error');
        }
    } catch (e) {
        if (loadingTip) loadingTip.style.display = 'none';
        if (!silent) showToast('网络连接异常', 'error');
    }
}

function updateOidcStats() {
    const totalEl = document.getElementById('stat-total-apps');
    const pkEl = document.getElementById('stat-passkey-apps');
    const hybridEl = document.getElementById('stat-hybrid-apps');
    const sysEl = document.getElementById('stat-system-apps');

    if (!totalEl) return;

    const total = cachedOidcClientsData.length;
    const pk = cachedOidcClientsData.filter(c => c.auth_method === 'passkey_only').length;
    const hybrid = cachedOidcClientsData.filter(c => c.auth_method === 'hybrid').length;
    const sys = cachedOidcClientsData.filter(c => c.is_system).length;

    totalEl.textContent = total;
    if (pkEl) pkEl.textContent = pk;
    if (hybridEl) hybridEl.textContent = hybrid;
    if (sysEl) sysEl.textContent = sys;
}

let appsViewMode = localStorage.getItem('abit_apps_view_mode') || 'card';

function switchAppsView(mode) {
    appsViewMode = mode;
    try { localStorage.setItem('abit_apps_view_mode', mode); } catch (e) {}
    const cardContainer = document.getElementById('appsCardContainer');
    const tableContainer = document.getElementById('appsTableViewContainer');
    const btnCard = document.getElementById('btnAppsCardView');
    const btnTable = document.getElementById('btnAppsTableView');

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

function filterOidcApps(keyword) {
    renderOidcClients(keyword);
}

function renderOidcClients(filterKeyword = '') {
    const cardContainer = document.getElementById('appsCardContainer');
    const tableContainer = document.getElementById('appsTableViewContainer');
    const tableBody = document.getElementById('appsTableBodyContainer');
    const emptyTip = document.getElementById('appsEmptyTip');
    if (!cardContainer) return;

    const keyword = (filterKeyword || '').trim().toLowerCase();
    const clients = cachedOidcClientsData.filter(c => {
        if (!keyword) return true;
        return (c.name && c.name.toLowerCase().includes(keyword)) ||
               (c.client_id && c.client_id.toLowerCase().includes(keyword)) ||
               (c.description && c.description.toLowerCase().includes(keyword));
    });

    if (clients.length === 0) {
        cardContainer.style.display = 'none';
        if (tableContainer) tableContainer.style.display = 'none';
        if (emptyTip) emptyTip.style.display = 'block';
        return;
    }

    if (emptyTip) emptyTip.style.display = 'none';

    // 1. 渲染卡片视图 (Card Grid)
    cardContainer.innerHTML = clients.map(c => {
        const isSys = c.is_system;
        const authBadge = c.auth_method === 'passkey_only' ? 
            `<span class="badge success">仅 Passkey</span>` : 
            (c.auth_method === 'password_only' ? `<span class="badge secondary">仅密码</span>` : `<span class="badge accent">混合认证</span>`);

        const sysBadge = isSys ? `<span class="badge warning" style="font-size: 10px;">系统内置</span>` : '';
        const uris = (c.redirect_uris || []).slice(0, 2).map(u => `<div style="font-family: monospace; font-size: 11px; color: var(--text-sec); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; min-width: 0;">🔗 ${escapeHtml(u)}</div>`).join('');

        const secretId = `secret_${c.client_id.replace(/[^a-zA-Z0-9]/g, '_')}`;

        return `
        <div class="domain-card" style="display: flex; flex-direction: column; min-width: 0; max-width: 100%; box-sizing: border-box; overflow: hidden;">
            <div>
                <div class="domain-card-header">
                    <div style="min-width: 0; flex: 1; overflow: hidden;">
                        <span class="domain-name" style="cursor: default;">
                            <span style="font-size: 18px; flex-shrink: 0;">${isSys ? '🛡️' : '📱'}</span>
                            <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(c.name)}</span>
                            ${sysBadge}
                        </span>
                        <div class="domain-target">
                            <span>🔑 Client ID:</span>
                            <code style="background: var(--card-sec); padding: 2px 6px; border-radius: 6px; border: 1px solid var(--border-subtle); font-size: 11px; color: var(--accent);">${escapeHtml(c.client_id)}</code>
                        </div>
                    </div>
                    <div style="flex-shrink: 0;">${authBadge}</div>
                </div>

                <div style="margin: 8px 0; display: flex; flex-direction: column; gap: 4px; min-height: 40px; min-width: 0; max-width: 100%; overflow: hidden;">
                    ${c.description ? `<div style="font-size: 12px; color: var(--text-sec); margin-bottom: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(c.description)}</div>` : ''}
                    ${uris || '<div style="font-size: 11px; color: var(--text-sec);">暂无回调地址</div>'}
                </div>

                <!-- Client Secret Box -->
                <div style="background: var(--card-sec); border-radius: 8px; padding: 6px 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; gap: 8px; min-width: 0; max-width: 100%; box-sizing: border-box; border: 1px solid var(--border-subtle);">
                    <div style="display: flex; flex-direction: column; min-width: 0; flex: 1; overflow: hidden;">
                        <span style="font-size: 10px; color: var(--text-sec); font-weight: 700;">CLIENT SECRET</span>
                        <div style="display: flex; align-items: center; gap: 6px; min-width: 0; max-width: 100%;">
                            <input type="password" id="${secretId}" value="${escapeHtml(c.client_secret || '')}" readonly style="background: transparent; border: none; font-family: monospace; font-size: 11px; color: var(--text); outline: none; width: 100%; min-width: 0; text-overflow: ellipsis; flex: 1;">
                            <button type="button" onclick="toggleSecretInputVisibility('${secretId}')" class="pill-btn" style="padding: 2px 6px; font-size: 10px; flex-shrink: 0;" title="显示/隐藏">👁️</button>
                        </div>
                    </div>
                    <div style="display: flex; gap: 4px; flex-shrink: 0;">
                        <button class="pill-btn" onclick="copyToClipboard('${escapeHtml(c.client_secret || '')}', 'Client Secret')" style="padding: 4px 8px; font-size: 11px; white-space: nowrap;">📋 复制</button>
                        ${!isSys ? `<button class="pill-btn" onclick="regenerateOidcSecret('${escapeHtml(c.client_id)}')" title="重置密钥" style="padding: 4px 8px; font-size: 11px; flex-shrink: 0;">🔄</button>` : ''}
                    </div>
                </div>

                <div class="domain-actions" style="margin-top: auto; padding-top: 10px; border-top: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; gap: 6px; width: 100%; box-sizing: border-box; min-width: 0;">
                    <button class="btn secondary sm" onclick="openOidcGuideModal('${escapeHtml(c.client_id)}')" style="font-size: 12px; padding: 5px 8px; flex: 1; text-align: center; justify-content: center; min-width: 0; white-space: nowrap;">📋 参数</button>
                    ${!isSys ? `
                    <button class="btn secondary sm" onclick="openEditOidcClientModal('${escapeHtml(c.client_id)}')" style="font-size: 12px; padding: 5px 8px; flex: 1; text-align: center; justify-content: center; min-width: 0; white-space: nowrap;">✏️ 编辑</button>
                    <button class="btn danger sm" onclick="deleteOidcClientAjax('${escapeHtml(c.client_id)}', '${escapeHtml(c.name)}')" style="font-size: 12px; padding: 5px 8px; flex: 1; text-align: center; justify-content: center; min-width: 0; white-space: nowrap;">🗑️ 删除</button>
                    ` : '<span style="font-size: 11px; color: var(--text-sec); padding: 4px 8px; flex: 1; text-align: right;">系统内置</span>'}
                </div>
            </div>
        </div>`;
    }).join('');

    // 2. 渲染表格视图 (Table View)
    if (tableBody) {
        tableBody.innerHTML = clients.map(c => {
            const isSys = c.is_system;
            const authBadge = c.auth_method === 'passkey_only' ? 
                `<span class="badge success">仅 Passkey</span>` : 
                (c.auth_method === 'password_only' ? `<span class="badge secondary">仅密码</span>` : `<span class="badge accent">混合认证</span>`);

            const sysBadge = isSys ? `<span class="badge warning" style="font-size: 10px; margin-left: 4px;">系统内置</span>` : '';
            const uris = (c.redirect_uris || []).length > 0 ? 
                (c.redirect_uris || []).map(u => `<div style="font-family: monospace; font-size: 11px; color: var(--text-sec); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 260px;" title="${escapeHtml(u)}">🔗 ${escapeHtml(u)}</div>`).join('') :
                '<span style="font-size: 11px; color: var(--text-sec);">暂无回调地址</span>';

            const secretId = `tbl_secret_${c.client_id.replace(/[^a-zA-Z0-9]/g, '_')}`;

            return `
            <tr>
                <td>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 18px; flex-shrink: 0;">${isSys ? '🛡️' : '📱'}</span>
                        <div style="min-width: 0;">
                            <div style="font-weight: 700; font-size: 13px; color: var(--text); display: flex; align-items: center;">
                                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(c.name)}</span>
                                ${sysBadge}
                            </div>
                            ${c.description ? `<div style="font-size: 11px; color: var(--text-sec); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(c.description)}">${escapeHtml(c.description)}</div>` : ''}
                        </div>
                    </div>
                </td>
                <td>
                    <code style="background: var(--card-sec); padding: 2px 6px; border-radius: 6px; border: 1px solid var(--border-subtle); font-size: 12px; color: var(--accent);">${escapeHtml(c.client_id)}</code>
                </td>
                <td>
                    <div class="badges-wrap" style="margin: 0;">
                        ${authBadge}
                    </div>
                </td>
                <td>
                    <div style="display: flex; flex-direction: column; gap: 2px;">
                        ${uris}
                    </div>
                </td>
                <td>
                    <div style="background: var(--card-sec); border-radius: 8px; padding: 4px 8px; display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--border-subtle); max-width: 240px;">
                        <input type="password" id="${secretId}" value="${escapeHtml(c.client_secret || '')}" readonly style="background: transparent; border: none; font-family: monospace; font-size: 11px; color: var(--text); outline: none; width: 90px; text-overflow: ellipsis;">
                        <button type="button" onclick="toggleSecretInputVisibility('${secretId}')" class="pill-btn" style="padding: 1px 5px; font-size: 10px;" title="显示/隐藏">👁️</button>
                        <button class="pill-btn" onclick="copyToClipboard('${escapeHtml(c.client_secret || '')}', 'Client Secret')" style="padding: 1px 6px; font-size: 10px;" title="复制密钥">📋</button>
                        ${!isSys ? `<button class="pill-btn" onclick="regenerateOidcSecret('${escapeHtml(c.client_id)}')" title="重置密钥" style="padding: 1px 5px; font-size: 10px;">🔄</button>` : ''}
                    </div>
                </td>
                <td style="text-align: right;">
                    <div style="display: inline-flex; gap: 6px;">
                        <button class="btn secondary sm" onclick="openOidcGuideModal('${escapeHtml(c.client_id)}')">📋 参数</button>
                        ${!isSys ? `
                        <button class="btn secondary sm" onclick="openEditOidcClientModal('${escapeHtml(c.client_id)}')">✏️ 编辑</button>
                        <button class="btn danger sm" onclick="deleteOidcClientAjax('${escapeHtml(c.client_id)}', '${escapeHtml(c.name)}')">🗑️ 删除</button>
                        ` : '<span style="font-size: 11px; color: var(--text-sec); padding: 4px 6px;">系统内置</span>'}
                    </div>
                </td>
            </tr>`;
        }).join('');
    }

    // 应用当前视图模式
    switchAppsView(appsViewMode);
}

function toggleSecretInputVisibility(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password';
}

function openAddOidcClientModal() {
    const modal = document.getElementById('addOidcClientModal');
    if (modal) {
        document.getElementById('addOidcClientForm').reset();
        modal.classList.add('active');
    }
}

function closeAddOidcClientModal() {
    const modal = document.getElementById('addOidcClientModal');
    if (modal) modal.classList.remove('active');
}

function openEditOidcClientModal(clientId) {
    const client = cachedOidcClientsData.find(c => c.client_id === clientId);
    if (!client) {
        showToast('未找到该客户端信息', 'error');
        return;
    }
    document.getElementById('edit_oidc_client_id_hidden').value = client.client_id;
    document.getElementById('edit_oidc_client_id').value = client.client_id;
    document.getElementById('edit_oidc_app_name').value = client.name || client.client_id;
    document.getElementById('edit_oidc_auth_method').value = client.auth_method || 'hybrid';
    document.getElementById('edit_oidc_redirect_uris').value = (client.redirect_uris || []).join('\n');
    document.getElementById('edit_oidc_post_logout_uris').value = client.post_logout_redirect_uris || '+';
    document.getElementById('edit_oidc_app_desc').value = client.description || '';

    const modal = document.getElementById('editOidcClientModal');
    if (modal) modal.classList.add('active');
}

function closeEditOidcClientModal() {
    const modal = document.getElementById('editOidcClientModal');
    if (modal) modal.classList.remove('active');
}

function autoFixClientRedirectUris() {
    const textarea = document.getElementById('edit_oidc_redirect_uris');
    if (!textarea) return;
    const lines = textarea.value.split(/[\r\n]+/).map(s => s.trim()).filter(Boolean);
    const added = new Set(lines);
    for (const uri of lines) {
        try {
            const url = new URL(uri);
            const origin = `${url.protocol}//${url.host}`;
            added.add(`${origin}/*`);
            added.add(`${origin}/`);
        } catch (e) {}
    }
    textarea.value = Array.from(added).join('\n');
    document.getElementById('edit_oidc_post_logout_uris').value = '+';
    showToast('已自动补充根域通配符与注销白名单 (+)', 'success');
}

async function submitEditOidcClientForm(event) {
    event.preventDefault();
    const clientId = document.getElementById('edit_oidc_client_id_hidden').value.trim();
    const name = document.getElementById('edit_oidc_app_name').value.trim();
    const authMethod = document.getElementById('edit_oidc_auth_method').value;
    const redirectUris = document.getElementById('edit_oidc_redirect_uris').value.trim();
    const postLogoutUris = document.getElementById('edit_oidc_post_logout_uris').value.trim();
    const description = document.getElementById('edit_oidc_app_desc').value.trim();

    if (!name) {
        showToast('请输入应用名称', 'error');
        return;
    }
    if (!redirectUris) {
        showToast('请至少填写一个回调地址', 'error');
        return;
    }

    const btn = document.getElementById('btnSubmitEditOidcClient');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-small"></span> 正在保存...';

    const formData = new FormData();
    formData.append('_csrf_token', getCsrfToken());
    formData.append('name', name);
    formData.append('auth_method', authMethod);
    formData.append('redirect_uris', redirectUris);
    formData.append('post_logout_redirect_uris', postLogoutUris || '+');
    formData.append('description', description);

    try {
        const res = await fetch(`/api/oidc/clients/${encodeURIComponent(clientId)}`, {
            method: 'PUT',
            body: formData
        });
        const result = await res.json();
        if (result.success) {
            showToast(result.msg || '客户端配置已更新！', 'success');
            closeEditOidcClientModal();
            await loadOidcClientsAjax(true);
        } else {
            showToast(result.error || '保存失败', 'error');
        }
    } catch (e) {
        showToast('网络通信异常', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '💾 保存配置';
    }
}

async function submitAddOidcClientForm(e) {
    e.preventDefault();
    const btn = document.getElementById('btnSubmitAddOidcClient');
    const name = document.getElementById('oidc_app_name').value.trim();
    const clientId = document.getElementById('oidc_client_id').value.trim();
    const authMethod = document.getElementById('oidc_auth_method').value;
    const redirectUris = document.getElementById('oidc_redirect_uris').value.trim();
    const desc = document.getElementById('oidc_app_desc').value.trim();

    if (!name || !clientId || !redirectUris) {
        showToast('请完整填写应用名称、Client ID 与回调地址', 'warning');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '⏳ 正在 Keycloak 中创建...';

    const formData = new FormData();
    formData.append('name', name);
    formData.append('client_id', clientId);
    formData.append('auth_method', authMethod);
    formData.append('redirect_uris', redirectUris);
    formData.append('description', desc);
    formData.append('_csrf_token', getCsrfToken());

    try {
        const res = await fetch('/api/oidc/clients', { method: 'POST', body: formData });
        const result = await res.json();

        if (result.success) {
            showToast(result.msg || '客户端创建成功！', 'success');
            closeAddOidcClientModal();
            await loadOidcClientsAjax(true);
            // 自动弹出该应用的对接指南参数表
            openOidcGuideModal(clientId);
        } else {
            showToast(result.error || '创建失败', 'error');
        }
    } catch (err) {
        showToast('网络通信异常', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🚀 立即在 Keycloak 创建';
    }
}

async function regenerateOidcSecret(clientId) {
    if (!confirm(`确定要重置应用 [${clientId}] 的 Client Secret 吗？\n重置后已对接的系统需要同步更新此密钥。`)) {
        return;
    }

    const formData = new FormData();
    formData.append('_csrf_token', getCsrfToken());

    try {
        const res = await fetch(`/api/oidc/clients/${encodeURIComponent(clientId)}/secret/regenerate`, {
            method: 'POST',
            body: formData
        });
        const result = await res.json();
        if (result.success) {
            showToast('Client Secret 已成功重置！', 'success');
            await loadOidcClientsAjax(true);
        } else {
            showToast(result.error || '重置密钥失败', 'error');
        }
    } catch (e) {
        showToast('网络通信异常', 'error');
    }
}

async function deleteOidcClientAjax(clientId, appName) {
    if (!confirm(`确认删除客户端应用 [${appName} (${clientId})]？\n删除后关联系统将无法继续使用 Keycloak 身份认证服务。`)) {
        return;
    }

    const token = typeof getCsrfToken === 'function' ? getCsrfToken() : '';
    const formData = new FormData();
    formData.append('_csrf_token', token);

    try {
        const res = await fetch(`/api/oidc/clients/${encodeURIComponent(clientId)}?_csrf_token=${encodeURIComponent(token)}`, {
            method: 'DELETE',
            headers: {
                'X-CSRF-Token': token,
                'X-CSRFToken': token
            },
            body: formData
        });
        const result = await res.json();
        if (result.success) {
            showToast(result.msg || '应用已成功删除！', 'success');
            await loadOidcClientsAjax(true);
        } else {
            showToast(result.error || '删除失败', 'error');
        }
    } catch (e) {
        showToast('网络通信异常', 'error');
    }
}

function openGlobalOidcEndpointsModal() {
    openOidcGuideModal('global-sso');
}

function openOidcGuideModal(clientId) {
    const client = cachedOidcClientsData.find(c => c.client_id === clientId) || {
        client_id: clientId,
        name: 'OIDC 客户端',
        client_secret: ''
    };
    currentGuideClient = client;

    const endpoints = cachedOidcEndpoints || {
        issuer: 'https://au.abab.pw/realms/master',
        discovery_url: 'https://au.abab.pw/realms/master/.well-known/openid-configuration',
        authorization_endpoint: 'https://au.abab.pw/realms/master/protocol/openid-connect/auth',
        token_endpoint: 'https://au.abab.pw/realms/master/protocol/openid-connect/token',
        userinfo_endpoint: 'https://au.abab.pw/realms/master/protocol/openid-connect/userinfo'
    };

    document.getElementById('guideModalTitle').textContent = `[${client.name || client.client_id}] 对接配置指南`;
    document.getElementById('guide_discovery_url').textContent = endpoints.discovery_url;
    document.getElementById('guide_issuer').textContent = endpoints.issuer;
    document.getElementById('guide_client_id').textContent = client.client_id;
    document.getElementById('guide_client_secret').textContent = client.client_secret || '（未获取到或已隐藏）';
    document.getElementById('guide_auth_url').textContent = endpoints.authorization_endpoint;
    document.getElementById('guide_token_url').textContent = endpoints.token_endpoint;
    document.getElementById('guide_userinfo_url').textContent = endpoints.userinfo_endpoint;

    // 填充 Gitea 专用 1 对 1 字段
    const giteaClientIdEl = document.getElementById('gitea_guide_client_id');
    if (giteaClientIdEl) giteaClientIdEl.textContent = client.client_id;
    const giteaSecretEl = document.getElementById('gitea_guide_client_secret');
    if (giteaSecretEl) giteaSecretEl.textContent = client.client_secret || '（未获取到或已隐藏）';
    const giteaDiscEl = document.getElementById('gitea_guide_discovery_url');
    if (giteaDiscEl) giteaDiscEl.textContent = endpoints.discovery_url;

    // 生成 Gitea app.ini / GitLab 配置示例
    const gitYaml = `; Gitea app.ini 配置文件 [oauth2_client] 段落示例:
[oauth2_client]
ENABLE = true
NAME = "keycloak"
PROVIDER = "openidConnect"
CLIENT_ID = "${client.client_id}"
CLIENT_SECRET = "${client.client_secret || 'YOUR_CLIENT_SECRET'}"
OPENID_CONNECT_SCOPES = "openid email profile"
AUTO_DISCOVERY_URL = "${endpoints.discovery_url}"
USERNAME = "preferred_username"
EMAIL = "email"
UPDATE_EXISTING_USER_DATA = true
AUTO_REGISTRATION = true`;
    const gitEl = document.getElementById('guide_git_yaml');
    if (gitEl) gitEl.textContent = gitYaml;

    switchGuideTab('standard');

    const modal = document.getElementById('oidcGuideModal');
    if (modal) modal.classList.add('active');
}

function closeOidcGuideModal() {
    const modal = document.getElementById('oidcGuideModal');
    if (modal) modal.classList.remove('active');
    currentGuideClient = null;
}

function switchGuideTab(tab) {
    document.getElementById('btnGuideTabStandard').classList.toggle('active', tab === 'standard');
    document.getElementById('btnGuideTabWordpress').classList.toggle('active', tab === 'wordpress');
    document.getElementById('btnGuideTabGit').classList.toggle('active', tab === 'git');

    document.getElementById('guideTabContentStandard').style.display = tab === 'standard' ? 'block' : 'none';
    document.getElementById('guideTabContentWordpress').style.display = tab === 'wordpress' ? 'block' : 'none';
    document.getElementById('guideTabContentGit').style.display = tab === 'git' ? 'block' : 'none';
}

// ═════════════════════════════════════════════════════════════════════
// ─── 9. SSL 证书管理与后台静默申请引擎 (SSL Certificate Engine) ───
// ═════════════════════════════════════════════════════════════════════
let cachedSslCertificates = [];
let cachedSslActiveTasks = [];
let sslTaskPollTimer = null;
let currentDetailSslTaskId = null;
let currentDetailSslId = null;

async function loadSslCertificatesAjax(silent = false) {
    const loadingTip = document.getElementById('sslLoadingTip');
    const emptyTip = document.getElementById('sslEmptyTip');
    const cardContainer = document.getElementById('sslCardContainer');
    const tableContainer = document.getElementById('sslTableContainer');

    if (!silent && loadingTip) loadingTip.style.display = 'block';

    try {
        const res = await fetch('/api/ssl/certificates');
        if (!res.ok) throw new Error('网络请求失败');
        const data = await res.json();
        if (loadingTip) loadingTip.style.display = 'none';

        if (data.success) {
            cachedSslCertificates = data.certificates || [];
            cachedSslActiveTasks = data.active_tasks || [];
            renderSslCertificates();
            updateSslStats();
            checkAndStartSslTaskPolling();
        } else {
            if (!silent) showToast('加载证书列表失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        if (loadingTip) loadingTip.style.display = 'none';
        if (!silent) showToast('加载 1Panel 证书列表异常', 'error');
    }
}

function updateSslStats() {
    const totalEl = document.getElementById('stat-total-certs');
    const readyEl = document.getElementById('stat-ready-certs');
    const applyingEl = document.getElementById('stat-applying-certs');
    const renewEl = document.getElementById('stat-autorenew-certs');

    if (!totalEl) return;

    const certs = cachedSslCertificates || [];
    const activeTasks = (cachedSslActiveTasks || []).filter(t => t.status === 'applying');
    
    const total = certs.length;
    const ready = certs.filter(c => c.status === 'ready' || c.status === 'success' || c.status === 'issued').length;
    const applying = activeTasks.length + certs.filter(c => c.status === 'applying').length;
    const autorenew = certs.filter(c => c.auto_renew).length;

    totalEl.textContent = total;
    if (readyEl) readyEl.textContent = ready;
    if (applyingEl) applyingEl.textContent = applying;
    if (renewEl) renewEl.textContent = autorenew;
}

let sslViewMode = localStorage.getItem('abit_ssl_view_mode') || 'card';

function switchSslView(mode) {
    sslViewMode = mode;
    try { localStorage.setItem('abit_ssl_view_mode', mode); } catch (e) {}
    const cardContainer = document.getElementById('sslCardContainer');
    const tableContainer = document.getElementById('sslTableContainer');
    const btnCard = document.getElementById('btnSslCardView');
    const btnTable = document.getElementById('btnSslTableView');

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

function filterSslCertificates(keyword) {
    renderSslCertificates(keyword);
}

function renderSslCertificates(filterKeyword = '') {
    const cardContainer = document.getElementById('sslCardContainer');
    const tableContainer = document.getElementById('sslTableContainer');
    const tableBody = document.getElementById('sslTableBody');
    const emptyTip = document.getElementById('sslEmptyTip');
    if (!cardContainer || !tableContainer) return;

    const keyword = (filterKeyword || '').trim().toLowerCase();
    
    // 活跃申请任务 (进行中的优先排在最前)
    const activeTasks = (cachedSslActiveTasks || []).filter(t => {
        if (!keyword) return true;
        return t.domain && t.domain.toLowerCase().includes(keyword);
    });

    // 收集处于申请中的任务域名和 SSL ID 用于去重
    const applyingTaskDomains = new Set(
        activeTasks
            .filter(t => t.status === 'applying')
            .map(t => (t.domain || '').toLowerCase())
            .filter(Boolean)
    );
    const applyingTaskSslIds = new Set(
        activeTasks
            .filter(t => t.status === 'applying' && t.ssl_id)
            .map(t => t.ssl_id)
    );

    const certs = (cachedSslCertificates || []).filter(c => {
        if (!keyword) return true;
        return (c.primary_domain && c.primary_domain.toLowerCase().includes(keyword)) ||
               (c.organization && c.organization.toLowerCase().includes(keyword)) ||
               (c.acme_account && c.acme_account.toLowerCase().includes(keyword));
    });

    // 去重：若某个证书仍在申请中（未 ready）且已有活跃 task 正在跟踪，则过滤掉 1Panel 提前占位的空白记录，由活跃任务卡片统一呈现
    const displayCerts = certs.filter(c => {
        const isReady = c.status === 'ready' || c.status === 'success' || c.status === 'issued';
        if (isReady) return true;
        const dom = (c.primary_domain || '').toLowerCase();
        if (applyingTaskDomains.has(dom) || applyingTaskSslIds.has(c.id)) {
            return false;
        }
        return true;
    });

    if (activeTasks.length === 0 && displayCerts.length === 0) {
        cardContainer.style.display = 'none';
        tableContainer.style.display = 'none';
        if (emptyTip) emptyTip.style.display = 'block';
        return;
    }

    if (emptyTip) emptyTip.style.display = 'none';

    // 1. 渲染紧凑卡片 (Card View)
    let cardHtml = '';
    let tableHtml = '';

    // --- 活跃任务渲染 ---
    activeTasks.forEach(task => {
        const isApplying = task.status === 'applying';
        let badgeClass = 'badge warning';
        let badgeText = '⏳ 申请中';
        if (task.status === 'ready' || task.status === 'success') {
            badgeClass = 'badge success';
            badgeText = '✅ 已就绪';
        } else if (task.status === 'cancelled') {
            badgeClass = 'badge secondary';
            badgeText = '⚠️ 已取消';
        } else if (!isApplying) {
            badgeClass = 'badge danger';
            badgeText = '❌ 申请失败';
        }
        const latestLog = (task.logs && task.logs.length) ? task.logs[task.logs.length - 1] : (task.message || '正在排队处理...');

        // 卡片视图
        cardHtml += `
        <div class="domain-card" style="border-color: var(--accent); background: var(--accent-bg);">
            <div>
                <div class="domain-card-header">
                    <div>
                        <span class="domain-name" style="color: var(--accent);">
                            <span style="font-size: 16px;">⚡</span>
                            ${escapeHtml(task.domain)}
                        </span>
                        <div class="domain-target" style="font-family: monospace; font-size: 11px;">
                            <span>任务 ID:</span>
                            <code>${escapeHtml(task.task_id.substring(0, 8))}...</code>
                        </div>
                    </div>
                    <span class="${badgeClass}">${badgeText}</span>
                </div>

                <div style="font-size: 11px; color: var(--text-sec); background: var(--card); border-radius: 8px; padding: 8px 10px; font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; border: 1px solid var(--border-subtle); margin: 8px 0;">
                    ${escapeHtml(latestLog)}
                </div>

                <div class="domain-actions" style="margin-top: auto; padding-top: 10px; border-top: 1px solid var(--border-subtle); display: flex; gap: 6px;">
                    <button class="btn secondary sm" onclick="openSslTaskDetailModal('${escapeHtml(task.task_id)}')" style="flex: 1; justify-content: center; font-size: 11px; padding: 5px 6px;">📜 进度日志</button>
                    ${isApplying ? `<button class="btn danger sm" onclick="cancelSslTaskAjax('${escapeHtml(task.task_id)}')" style="font-size: 11px; padding: 5px 10px;">🛑 取消</button>` : ''}
                </div>
            </div>
        </div>`;

        // 表格视图
        tableHtml += `
        <tr style="background: var(--accent-bg);">
            <td>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span>⚡</span>
                    <div>
                        <div style="font-weight: 700; font-size: 13px; color: var(--accent);">${escapeHtml(task.domain)}</div>
                        <div style="font-size: 10px; color: var(--text-sec); font-family: monospace;">任务 ID: ${escapeHtml(task.task_id.substring(0, 8))}...</div>
                    </div>
                </div>
            </td>
            <td><span class="badge secondary" style="font-size: 10px;">后台任务</span></td>
            <td><span class="${badgeClass}" style="font-size: 10px;">${badgeText}</span></td>
            <td>
                <div style="font-size: 11px; color: var(--text-sec); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(latestLog)}">
                    ${escapeHtml(latestLog)}
                </div>
            </td>
            <td><span style="font-size: 11px; color: var(--text-sec);">-</span></td>
            <td style="text-align: right;">
                <div style="display: inline-flex; gap: 6px;">
                    <button class="btn secondary sm" onclick="openSslTaskDetailModal('${escapeHtml(task.task_id)}')">📜 日志</button>
                    ${isApplying ? `<button class="btn danger sm" onclick="cancelSslTaskAjax('${escapeHtml(task.task_id)}')">🛑 取消</button>` : ''}
                </div>
            </td>
        </tr>`;
    });

    // --- 已就绪/已签发证书渲染 ---
    displayCerts.forEach(cert => {
        const isReady = cert.status === 'ready' || cert.status === 'success' || cert.status === 'issued';
        const isApplying = cert.status === 'applying';
        const statusBadge = isReady ? 
            '<span class="badge success" style="font-size: 10px; padding: 2px 6px;">✅ 就绪</span>' : 
            (isApplying ? '<span class="badge warning" style="font-size: 10px; padding: 2px 6px;">⏳ 申请中</span>' : `<span class="badge danger" style="font-size: 10px; padding: 2px 6px;">❌ ${escapeHtml(cert.status)}</span>`);

        const websitesHtml = (cert.websites || []).length > 0 ? 
            cert.websites.map(w => `<span class="badge secondary" style="font-size: 10px; padding: 1px 5px;">🌐 ${escapeHtml(w)}</span>`).join(' ') : 
            '<span style="font-size: 11px; color: var(--text-sec);">未绑定反代</span>';

        let expireShort = '-';
        let daysLeftStr = '';
        if (cert.expire_date && !cert.expire_date.startsWith('0001-01-01') && !cert.expire_date.startsWith('1970-01-01') && isReady) {
            const expDate = new Date(cert.expire_date);
            const now = new Date();
            const daysLeft = Math.ceil((expDate - now) / (1000 * 60 * 60 * 24));
            expireShort = cert.expire_date.split('T')[0] || cert.expire_date;
            if (!isNaN(daysLeft)) {
                if (daysLeft > 30) {
                    daysLeftStr = `<span style="color: var(--success); font-weight: 600;">${daysLeft}天后到期</span>`;
                } else if (daysLeft > 0) {
                    daysLeftStr = `<span style="color: var(--warning); font-weight: 700;">${daysLeft}天后到期</span>`;
                } else {
                    daysLeftStr = `<span style="color: var(--danger); font-weight: 700;">已过期</span>`;
                }
            }
        } else {
            expireShort = isReady ? '正常' : '待签发';
            daysLeftStr = isReady ? '' : '<span style="color: var(--warning);">⏳ 申请中</span>';
        }

        const authTypeLabel = cert.provider === 'dnsAccount' ? 'DNS 验证' : 'HTTP 验证';
        const orgLabel = cert.organization || "Let's Encrypt";

        // 卡片视图 (统一 Apple Glass 风格)
        cardHtml += `
        <div class="domain-card">
            <div>
                <div class="domain-card-header">
                    <div>
                        <span class="domain-name" title="${escapeHtml(cert.primary_domain)}">
                            <span style="font-size: 16px;">🔒</span>
                            ${escapeHtml(cert.primary_domain)}
                        </span>
                        <div class="domain-target">
                            <span>🏢 机构:</span>
                            <span style="color: var(--text);">${escapeHtml(orgLabel)} · ${authTypeLabel}</span>
                        </div>
                    </div>
                    <div>${statusBadge}</div>
                </div>

                <div style="font-size: 12px; display: flex; justify-content: space-between; align-items: center; background: var(--card-sec); padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border-subtle); margin: 8px 0;">
                    <span style="color: var(--text-sec); font-family: monospace;">📅 ${expireShort}</span>
                    <span>${daysLeftStr} ${cert.auto_renew ? '· <span style="color: var(--success); font-weight: 600;">🔄 自动续签</span>' : ''}</span>
                </div>

                <div style="min-height: 24px; margin-bottom: 8px;">
                    ${(cert.websites && cert.websites.length > 0) ? `<div style="display: flex; flex-wrap: wrap; gap: 4px;">${websitesHtml}</div>` : '<div style="font-size: 11px; color: var(--text-sec);">未绑定反代站点</div>'}
                </div>

                <div class="domain-actions" style="margin-top: auto; padding-top: 10px; border-top: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; gap: 6px;">
                    <button class="btn secondary sm" onclick="downloadSslBundle(${cert.id}, '${escapeHtml(cert.primary_domain)}')" style="flex: 1; justify-content: center; font-size: 11px; padding: 5px 6px;" title="导出完整证书元数据包与自动续签凭据">📥 导出</button>
                    <button class="btn secondary sm" onclick="openSslItemLogModal(${cert.id}, '${escapeHtml(cert.primary_domain)}')" style="flex: 1; justify-content: center; font-size: 11px; padding: 5px 6px;">📜 日志</button>
                    <button class="btn accent sm" onclick="reapplySslForDomain('${escapeHtml(cert.primary_domain)}')" style="font-size: 11px; padding: 5px 8px; white-space: nowrap;">🔄 续签/申请</button>
                </div>
            </div>
        </div>`;

        // 表格视图 (紧凑精炼)
        tableHtml += `
        <tr>
            <td>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span>🔒</span>
                    <div>
                        <div style="font-weight: 700; font-size: 13px; color: var(--text);">${escapeHtml(cert.primary_domain)}</div>
                        <div style="font-size: 11px; color: var(--text-sec);">${escapeHtml(orgLabel)}</div>
                    </div>
                </div>
            </td>
            <td><span class="badge secondary" style="font-size: 10px;">${authTypeLabel}</span></td>
            <td>${statusBadge}</td>
            <td>
                <div style="font-size: 12px; font-family: monospace;">${expireShort}</div>
                <div style="font-size: 10px;">${daysLeftStr} ${cert.auto_renew ? '· <span style="color: var(--success);">自动续签</span>' : ''}</div>
            </td>
            <td><div style="display: flex; flex-wrap: wrap; gap: 3px;">${websitesHtml}</div></td>
            <td style="text-align: right;">
                <div style="display: inline-flex; gap: 6px;">
                    <button class="btn secondary sm" onclick="downloadSslBundle(${cert.id}, '${escapeHtml(cert.primary_domain)}')" title="导出完整证书包">📥 导出</button>
                    <button class="btn secondary sm" onclick="openSslItemLogModal(${cert.id}, '${escapeHtml(cert.primary_domain)}')">📜 日志</button>
                    <button class="btn accent sm" onclick="reapplySslForDomain('${escapeHtml(cert.primary_domain)}')">🔄 申请</button>
                </div>
            </td>
        </tr>`;
    });

    cardContainer.innerHTML = cardHtml;
    if (tableBody) tableBody.innerHTML = tableHtml;

    // 应用当前视图模式
    switchSslView(sslViewMode);
}

// ─── SSL Export & Import Handlers ───
function downloadSslBundle(sslId, domain) {
    showToast(`正在导出 ${domain} 证书 ZIP 压缩包...`, 'info');
    const a = document.createElement('a');
    a.href = `/api/ssl/export/${sslId}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function exportAllSslBundles() {
    showToast('正在批量导出 1Panel 全部证书 ZIP 压缩包 (按域名分目录)...', 'info');
    const a = document.createElement('a');
    a.href = `/api/ssl/export_all`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function openImportSslModal() {
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    const modal = document.getElementById('importSslModal');
    if (!modal) return;
    const form = document.getElementById('sslImportModalForm');
    if (form) form.reset();
    switchImportTab('file');
    modal.classList.add('active');
}

function closeImportSslModal() {
    const modal = document.getElementById('importSslModal');
    if (modal) modal.classList.remove('active');
}

function switchImportTab(tabName) {
    const fileSec = document.getElementById('importSectionFile');
    const textSec = document.getElementById('importSectionText');
    const btnFile = document.getElementById('btnImportTabFile');
    const btnText = document.getElementById('btnImportTabText');

    if (tabName === 'text') {
        if (fileSec) fileSec.style.display = 'none';
        if (textSec) textSec.style.display = 'block';
        if (btnText) btnText.classList.add('active');
        if (btnFile) btnFile.classList.remove('active');
    } else {
        if (fileSec) fileSec.style.display = 'block';
        if (textSec) textSec.style.display = 'none';
        if (btnFile) btnFile.classList.add('active');
        if (btnText) btnText.classList.remove('active');
    }
}

async function submitImportSslModal(e) {
    if (e) e.preventDefault();
    const btn = document.getElementById('modalSslImportSubmitBtn');
    const fileInput = document.getElementById('import_ssl_file');
    const jsonTextarea = document.getElementById('import_ssl_json');

    const formData = new FormData();
    formData.append('_csrf_token', (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');

    if (fileInput && fileInput.files && fileInput.files.length > 0) {
        formData.append('file', fileInput.files[0]);
    } else if (jsonTextarea && jsonTextarea.value.trim()) {
        formData.append('bundle_json', jsonTextarea.value.trim());
    } else {
        showToast('请选择证书 ZIP 压缩包 / JSON 备份文件或粘贴数据', 'warning');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ 正在解析并导入中...';
    }

    try {
        const res = await fetch('/api/ssl/import', { method: 'POST', body: formData });
        const data = await res.json();
        if (btn) {
            btn.disabled = false;
            btn.textContent = '🚀 确认导入证书';
        }

        if (data.success) {
            showToast(data.message || '证书导入成功！', 'success');
            closeImportSslModal();
            await loadSslCertificatesAjax(true);
        } else {
            showToast('导入失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '🚀 确认导入证书';
        }
        showToast('网络请求发生异常: ' + err.message, 'error');
    }
}

function checkAndStartSslTaskPolling() {
    const hasActive = (cachedSslActiveTasks || []).some(t => t.status === 'applying');
    if (hasActive) {
        if (!sslTaskPollTimer) {
            sslTaskPollTimer = setInterval(async () => {
                await loadSslCertificatesAjax(true);
                // 若详情弹窗正打开某个任务，同步刷新弹窗日志
                if (currentDetailSslTaskId) {
                    const curTask = cachedSslActiveTasks.find(t => t.task_id === currentDetailSslTaskId);
                    if (curTask) {
                        renderSslModalLogs(curTask.logs || []);
                        updateSslDetailModalHeader(curTask.status, curTask.domain, curTask.updated_at, curTask.task_id);
                    }
                }
            }, 3000);
        }
    } else {
        if (sslTaskPollTimer) {
            clearInterval(sslTaskPollTimer);
            sslTaskPollTimer = null;
        }
    }
}

// ─── Apply SSL Modal & Submission ───
function openApplySslModal(prefillDomain = '') {
    const modal = document.getElementById('applySslModal');
    if (!modal) return;
    if (prefillDomain) {
        document.getElementById('modal_ssl_domain').value = prefillDomain;
    }
    loadModalSSLAccounts();
    modal.classList.add('active');
}

function closeApplySslModal() {
    const modal = document.getElementById('applySslModal');
    if (modal) modal.classList.remove('active');
}

function toggleModalSSLDNSSection(val) {
    document.getElementById('modal_ssl_dns_container').style.display = (val === 'dns') ? 'block' : 'none';
}

async function loadModalSSLAccounts() {
    try {
        const acmeRes = await fetch('/api/acme_accounts');
        const acmes = await acmeRes.json();
        const select = document.getElementById('modal_ssl_acme_account');
        select.innerHTML = '';
        acmes.forEach(acc => {
            const opt = document.createElement('option');
            opt.value = acc.id;
            opt.textContent = `${acc.email} (ID: ${acc.id})`;
            select.appendChild(opt);
        });

        const dnsRes = await fetch('/api/dns_accounts');
        const dnss = await dnsRes.json();
        const dnsSelect = document.getElementById('modal_ssl_dns_account');
        dnsSelect.innerHTML = '';
        dnss.forEach(acc => {
            const opt = document.createElement('option');
            opt.value = acc.id;
            opt.textContent = `${acc.name} (ID: ${acc.id})`;
            dnsSelect.appendChild(opt);
        });
    } catch (e) {}
}

async function submitApplySslModal(e) {
    if (e) e.preventDefault();
    const domain = document.getElementById('modal_ssl_domain').value.trim();
    const acmeId = document.getElementById('modal_ssl_acme_account').value;
    const authMethod = document.getElementById('modal_ssl_auth_method').value;
    const dnsId = document.getElementById('modal_ssl_dns_account').value;
    const btn = document.getElementById('modalSslSubmitBtn');

    if (!domain) {
        showToast('请输入申请域名', 'warning');
        return;
    }
    if (authMethod === 'dns' && !dnsId) {
        showToast('请选择 DNS 账户', 'warning');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ 正在提交...';
    }

    const csrfToken = (typeof getCsrfToken === 'function') ? getCsrfToken() : ((document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');
    const formData = new FormData();
    formData.append('domain', domain);
    formData.append('acme_id', acmeId);
    if (authMethod === 'dns') formData.append('dns_id', dnsId);
    formData.append('_csrf_token', csrfToken);

    try {
        const res = await fetch('/api/apply_ssl', { method: 'POST', body: formData });
        const result = await res.json();
        if (btn) {
            btn.disabled = false;
            btn.textContent = '🚀 开始后台申请';
        }

        if (result.success) {
            showToast(`已成功发起 ${domain} 的 SSL 证书申请任务！`, 'success');
            closeApplySslModal();
            // 立即刷新证书列表并弹出详情窗口查看进度
            await loadSslCertificatesAjax(true);
            if (result.task_id) {
                openSslTaskDetailModal(result.task_id);
            }
        } else {
            showToast('提交失败: ' + (result.error || '未知错误'), 'error');
        }
    } catch (err) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '🚀 开始后台申请';
        }
        showToast('网络请求发生异常: ' + err.message, 'error');
    }
}

// ─── SSL Task / Log Detail Modal ───
function openSslTaskDetailModal(taskId) {
    currentDetailSslTaskId = taskId;
    currentDetailSslId = null;
    const modal = document.getElementById('sslDetailModal');
    if (!modal) return;

    const task = (cachedSslActiveTasks || []).find(t => t.task_id === taskId);
    if (task) {
        updateSslDetailModalHeader(task.status, task.domain, task.updated_at, task.task_id);
        renderSslModalLogs(task.logs || []);
    } else {
        updateSslDetailModalHeader('loading', '正在加载...', '', taskId);
        fetchSslTaskStatus(taskId);
    }
    modal.classList.add('active');
}

async function fetchSslTaskStatus(taskId) {
    try {
        const res = await fetch(`/api/ssl/task/${taskId}`);
        const data = await res.json();
        if (data.success && data.task) {
            const task = data.task;
            updateSslDetailModalHeader(task.status, task.domain, task.updated_at, task.task_id);
            renderSslModalLogs(task.logs || []);
        }
    } catch (e) {}
}

async function openSslItemLogModal(sslId, domain) {
    currentDetailSslTaskId = null;
    currentDetailSslId = sslId;
    const modal = document.getElementById('sslDetailModal');
    if (!modal) return;

    updateSslDetailModalHeader('ready', domain, '', `SSL ID: ${sslId}`);
    document.getElementById('sslDetailActions').innerHTML = '';
    renderSslModalLogs(['正在读取 1Panel 证书流水日志...']);
    modal.classList.add('active');

    try {
        const res = await fetch(`/api/ssl/logs/${sslId}`);
        const data = await res.json();
        if (data.success && data.logs) {
            renderSslModalLogs(data.logs);
        } else {
            renderSslModalLogs(['获取日志失败: ' + (data.error || '未知错误')]);
        }
    } catch (e) {
        renderSslModalLogs(['网络通信异常: ' + e.message]);
    }
}

function updateSslDetailModalHeader(status, domain, updateTime, subId) {
    const titleEl = document.getElementById('sslDetailTitle');
    const subEl = document.getElementById('sslDetailSub');
    const badgeEl = document.getElementById('sslDetailStatusBadge');
    const timeEl = document.getElementById('sslDetailTime');
    const actionsEl = document.getElementById('sslDetailActions');

    if (titleEl) titleEl.textContent = `${domain} 证书进度详情`;
    if (subEl) subEl.textContent = subId || '';
    if (timeEl) timeEl.textContent = updateTime ? `更新于: ${updateTime}` : '';

    if (badgeEl) {
        if (status === 'applying') {
            badgeEl.className = 'badge warning';
            badgeEl.textContent = '⏳ 正在申请中...';
        } else if (status === 'ready' || status === 'success') {
            badgeEl.className = 'badge success';
            badgeEl.textContent = '✅ 已成功签发';
        } else if (status === 'cancelled') {
            badgeEl.className = 'badge secondary';
            badgeEl.textContent = '⚠️ 已取消申请';
        } else {
            badgeEl.className = 'badge danger';
            badgeEl.textContent = '❌ 申请失败';
        }
    }

    if (actionsEl && currentDetailSslTaskId) {
        if (status === 'applying') {
            actionsEl.innerHTML = `<button class="btn danger sm" onclick="cancelSslTaskAjax('${currentDetailSslTaskId}')" style="font-size: 11px; padding: 4px 10px;">🛑 取消申请任务</button>`;
        } else {
            actionsEl.innerHTML = `<button class="btn accent sm" onclick="reapplySslForDomain('${domain}')" style="font-size: 11px; padding: 4px 10px;">🔄 重新申请</button>`;
        }
    }
}

function renderSslModalLogs(logs) {
    const logsEl = document.getElementById('sslDetailLogs');
    if (!logsEl) return;
    logsEl.innerHTML = (logs || []).map(line => {
        let cls = 'info';
        // 关键改动：避免误报停止，日志中正常的等待/跳过不标记为严重错误
        if (line.includes('❌') || line.includes('error:') || line.includes('Failed:') || line.includes('证书申请失败')) {
            cls = 'error';
        } else if (line.includes('🎉') || line.includes('成功') || line.includes('Validations succeeded') || line.includes('Server responded with a certificate')) {
            cls = 'success';
        } else if (line.startsWith('[系统]')) {
            cls = 'system';
        }
        return `<div class="${cls}">${escapeHtml(line)}</div>`;
    }).join('');
    logsEl.scrollTop = logsEl.scrollHeight;
}

function closeSslDetailModal() {
    const modal = document.getElementById('sslDetailModal');
    if (modal) modal.classList.remove('active');
    currentDetailSslTaskId = null;
    currentDetailSslId = null;
}

async function cancelSslTaskAjax(taskId) {
    if (!confirm('确定要取消此证书的后台申请任务吗？')) return;
    try {
        const res = await fetch(`/api/ssl/cancel/${taskId}`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('已取消证书申请任务', 'info');
            await loadSslCertificatesAjax(true);
            if (currentDetailSslTaskId === taskId) {
                updateSslDetailModalHeader('cancelled', '', '', taskId);
            }
        }
    } catch (e) {
        showToast('取消请求异常', 'error');
    }
}

function reapplySslForDomain(domain) {
    closeSslDetailModal();
    openApplySslModal(domain);
}

// 页面加载或切换时绑定
async function loadSSLAccounts() {
    await loadSslCertificatesAjax(false);
}

// 导出全局函数
window.toggleEditTarget = toggleEditTarget;
window.saveTargetPortAjax = saveTargetPortAjax;
window.loadSslCertificatesAjax = loadSslCertificatesAjax;
window.filterSslCertificates = filterSslCertificates;
window.switchSslView = switchSslView;
window.openApplySslModal = openApplySslModal;
window.closeApplySslModal = closeApplySslModal;
window.toggleModalSSLDNSSection = toggleModalSSLDNSSection;
window.submitApplySslModal = submitApplySslModal;
window.openSslTaskDetailModal = openSslTaskDetailModal;
window.openSslItemLogModal = openSslItemLogModal;
window.closeSslDetailModal = closeSslDetailModal;
window.cancelSslTaskAjax = cancelSslTaskAjax;
window.reapplySslForDomain = reapplySslForDomain;
window.loadSSLAccounts = loadSSLAccounts;
window.downloadSslBundle = downloadSslBundle;
window.exportAllSslBundles = exportAllSslBundles;
window.openImportSslModal = openImportSslModal;
window.closeImportSslModal = closeImportSslModal;
window.switchImportTab = switchImportTab;
window.submitImportSslModal = submitImportSslModal;
window.handleDomainSslCertChange = handleDomainSslCertChange;
window.populateModalDomainSslCerts = populateModalDomainSslCerts;
window.switchAppsView = switchAppsView;
window.filterOidcApps = filterOidcApps;
window.renderOidcClients = renderOidcClients;
window.loadOidcClientsAjax = loadOidcClientsAjax;
window.openAddOidcClientModal = openAddOidcClientModal;
window.closeAddOidcClientModal = closeAddOidcClientModal;
window.openGlobalOidcEndpointsModal = openGlobalOidcEndpointsModal;
window.openOidcGuideModal = openOidcGuideModal;
window.closeOidcGuideModal = closeOidcGuideModal;
window.switchGuideTab = switchGuideTab;
window.toggleSecretInputVisibility = toggleSecretInputVisibility;
