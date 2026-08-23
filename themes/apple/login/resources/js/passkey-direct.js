// Passkey 与多站点按需认证策略控制器 (支持纯 Passkey / 纯密码 / 混合登录)
(function() {
    function base64urlToBuffer(base64url) {
        let base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
        while (base64.length % 4) base64 += "=";
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        return bytes.buffer;
    }

    function bufferToBase64url(buffer) {
        if (!buffer) return "";
        const bytes = new Uint8Array(buffer);
        let binary = "";
        for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
        return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
    }

    function getTargetDomain() {
        const urlParams = new URLSearchParams(window.location.search);
        let redirectUri = urlParams.get("redirect_uri") || "";
        
        if (!redirectUri) {
            const clientData = urlParams.get("client_data") || "";
            if (clientData) {
                try {
                    const decoded = JSON.parse(atob(clientData));
                    redirectUri = decoded.ru || "";
                } catch (e) {}
            }
        }
        
        if (!redirectUri) {
            const forms = document.querySelectorAll("form");
            for (const f of forms) {
                if (f.action && f.action.includes("redirect_uri=")) {
                    const match = f.action.match(/redirect_uri=([^&]+)/);
                    if (match) redirectUri = decodeURIComponent(match[1]);
                }
            }
        }
        
        if (redirectUri) {
            try {
                const u = new URL(redirectUri);
                return u.hostname.toLowerCase();
            } catch (e) {
                const match = redirectUri.match(/https?:\/\/([^\/:]+)/i);
                if (match) return match[1].toLowerCase();
            }
        }
        return window.location.hostname.toLowerCase();
    }

    async function fetchSitePolicy() {
        try {
            const scripts = document.querySelectorAll('script[src*="passkey-direct.js"]');
            let policyUrl = "/resources/login/apple/site-policy.json";
            if (scripts.length > 0) {
                policyUrl = scripts[0].src.replace(/\/js\/passkey-direct\.js.*/, "/site-policy.json");
            }
            const res = await fetch(policyUrl + "?t=" + Date.now());
            if (res.ok) {
                return await res.json();
            }
        } catch (e) {
            console.warn("获取 site-policy.json 失败:", e);
        }
        return {};
    }

    async function initPolicyAndPasskey() {
        const domain = getTargetDomain();
        const policy = await fetchSitePolicy();
        const domainPolicy = policy[domain] || { allow_passkey: true, allow_password: true };
        const allowPasskey = domainPolicy.allow_passkey !== false;
        const allowPassword = domainPolicy.allow_password !== false;

        const tryAnotherLink = document.getElementById("try-another-way");
        const tryAnotherForm = document.getElementById("kc-select-try-another-way-form");
        const isPasswordPage = !!document.getElementById("kc-form-login");
        const isWebAuthnPage = !!document.getElementById("kc-form-webauthn");

        // 场景 1: 该站点禁用了 Passkey 认证 (仅允许账号密码登录)
        if (!allowPasskey && allowPassword) {
            if (tryAnotherForm) tryAnotherForm.style.display = "none";
            if (tryAnotherLink) tryAnotherLink.style.display = "none";
            return;
        }

        // 场景 2: 该站点禁用了密码认证 (仅允许 Passkey 认证)
        if (!allowPassword && allowPasskey) {
            if (isPasswordPage && tryAnotherForm) {
                // 在密码界面：静默直通进入 Passkey 界面
                if (tryAnotherLink) tryAnotherLink.innerHTML = "正在进入 Passkey 认证...";
                try {
                    const actionUrl = tryAnotherForm.action;
                    const res1 = await fetch(actionUrl, {
                        method: "POST",
                        headers: { "Content-Type": "application/x-www-form-urlencoded" },
                        body: new URLSearchParams({ "tryAnotherWay": "on" })
                    });
                    const html1 = await res1.text();
                    const doc1 = new DOMParser().parseFromString(html1, "text/html");

                    let passkeyExecId = null;
                    const buttons = doc1.querySelectorAll("button[name='authenticationExecution']");
                    for (const btn of buttons) {
                        const txt = (btn.innerText || btn.textContent || "").toLowerCase();
                        if (txt.includes("密钥") || txt.includes("安全") || txt.includes("webauthn") || txt.includes("passkey")) {
                            passkeyExecId = btn.value;
                            break;
                        }
                    }

                    const selForm = doc1.getElementById("kc-select-credential-form");
                    const action2 = selForm ? selForm.action : actionUrl;

                    const targetForm = document.createElement("form");
                    targetForm.method = "POST";
                    targetForm.action = action2;
                    const input = document.createElement("input");
                    input.type = "hidden";
                    input.name = "authenticationExecution";
                    input.value = passkeyExecId || "";
                    targetForm.appendChild(input);
                    document.body.appendChild(targetForm);
                    targetForm.submit();
                    return;
                } catch (e) {
                    tryAnotherForm.requestSubmit();
                    return;
                }
            } else if (isWebAuthnPage) {
                // 在 Passkey 界面：隐藏切换密码入口，保持纯净 Passkey 页面
                if (tryAnotherForm) tryAnotherForm.style.display = "none";
                if (tryAnotherLink) tryAnotherLink.style.display = "none";
                return;
            }
        }

        // 场景 3: 两种方式均开启 (混合免密自适应模式)
        if (isPasswordPage && tryAnotherLink && tryAnotherForm) {
            tryAnotherLink.innerHTML = "使用 Passkey 登录";
            tryAnotherLink.style.display = "inline-flex";
            tryAnotherLink.style.alignItems = "center";
            tryAnotherLink.style.justifyContent = "center";
            tryAnotherLink.style.cursor = "pointer";

            tryAnotherLink.onclick = async function(e) {
                e.preventDefault();
                e.stopPropagation();

                const originalText = tryAnotherLink.innerHTML;
                tryAnotherLink.innerHTML = "正在调起 Passkey 登录...";
                tryAnotherLink.style.pointerEvents = "none";
                tryAnotherLink.style.opacity = "0.7";

                try {
                    const actionUrl = tryAnotherForm.action;
                    const res1 = await fetch(actionUrl, {
                        method: "POST",
                        headers: { "Content-Type": "application/x-www-form-urlencoded" },
                        body: new URLSearchParams({ "tryAnotherWay": "on" })
                    });
                    if (!res1.ok) throw new Error("Step 1 failed");

                    const html1 = await res1.text();
                    const doc1 = new DOMParser().parseFromString(html1, "text/html");

                    let passkeyExecId = null;
                    const buttons = doc1.querySelectorAll("button[name='authenticationExecution']");
                    for (const btn of buttons) {
                        const txt = (btn.innerText || btn.textContent || "").toLowerCase();
                        if (txt.includes("密钥") || txt.includes("安全") || txt.includes("webauthn") || txt.includes("passkey")) {
                            passkeyExecId = btn.value;
                            break;
                        }
                    }

                    if (!passkeyExecId) {
                        tryAnotherForm.requestSubmit();
                        return;
                    }

                    const selForm = doc1.getElementById("kc-select-credential-form");
                    const action2 = selForm ? selForm.action : actionUrl;

                    const res2 = await fetch(action2, {
                        method: "POST",
                        headers: { "Content-Type": "application/x-www-form-urlencoded" },
                        body: new URLSearchParams({ "authenticationExecution": passkeyExecId })
                    });
                    if (!res2.ok) throw new Error("Step 2 failed");

                    const html2 = await res2.text();

                    const mChallenge = html2.match(/challenge\s*:\s*"([^"]+)"/);
                    const mRpId = html2.match(/rpId\s*:\s*"([^"]+)"/);
                    const mUV = html2.match(/userVerification\s*:\s*"([^"]+)"/);
                    const mAction = html2.match(/id="webauth"[^>]*action="([^"]+)"/);

                    if (!mChallenge || !mRpId || !window.PublicKeyCredential) {
                        const fallbackForm = document.createElement("form");
                        fallbackForm.method = "POST";
                        fallbackForm.action = action2;
                        const input = document.createElement("input");
                        input.type = "hidden";
                        input.name = "authenticationExecution";
                        input.value = passkeyExecId;
                        fallbackForm.appendChild(input);
                        document.body.appendChild(fallbackForm);
                        fallbackForm.submit();
                        return;
                    }

                    const challenge = mChallenge[1];
                    const rpId = mRpId[1];
                    const userVerification = mUV ? mUV[1] : "preferred";
                    const webauthAction = mAction ? mAction[1].replace(/&amp;/g, "&") : action2;

                    const credential = await navigator.credentials.get({
                        publicKey: {
                            challenge: base64urlToBuffer(challenge),
                            rpId: rpId,
                            userVerification: userVerification
                        }
                    });

                    if (!credential) throw new Error("No credential returned");

                    const submitForm = document.createElement("form");
                    submitForm.method = "POST";
                    submitForm.action = webauthAction;

                    const fields = {
                        clientDataJSON: bufferToBase64url(credential.response.clientDataJSON),
                        authenticatorData: bufferToBase64url(credential.response.authenticatorData),
                        signature: bufferToBase64url(credential.response.signature),
                        credentialId: bufferToBase64url(credential.rawId),
                        userHandle: bufferToBase64url(credential.response.userHandle),
                        error: ""
                    };

                    for (const [key, val] of Object.entries(fields)) {
                        const input = document.createElement("input");
                        input.type = "hidden";
                        input.name = key;
                        input.value = val;
                        submitForm.appendChild(input);
                    }

                    document.body.appendChild(submitForm);
                    submitForm.submit();

                } catch (err) {
                    console.warn("Passkey 直接认证取消或降级:", err);
                    tryAnotherLink.innerHTML = originalText;
                    tryAnotherLink.style.pointerEvents = "auto";
                    tryAnotherLink.style.opacity = "1";
                }
            };
        } else if (isWebAuthnPage && tryAnotherLink && tryAnotherForm) {
            tryAnotherLink.innerHTML = "使用账号密码登录";
            tryAnotherLink.style.display = "inline-flex";
            tryAnotherLink.style.alignItems = "center";
            tryAnotherLink.style.justifyContent = "center";
            tryAnotherLink.style.cursor = "pointer";

            tryAnotherLink.onclick = async function(e) {
                e.preventDefault();
                tryAnotherLink.innerHTML = "正在切换至密码登录...";

                try {
                    const actionUrl = tryAnotherForm.action;
                    const res1 = await fetch(actionUrl, {
                        method: "POST",
                        headers: { "Content-Type": "application/x-www-form-urlencoded" },
                        body: new URLSearchParams({ "tryAnotherWay": "on" })
                    });
                    const html1 = await res1.text();
                    const doc1 = new DOMParser().parseFromString(html1, "text/html");

                    let passwordExecId = null;
                    const buttons = doc1.querySelectorAll("button[name='authenticationExecution']");
                    for (const btn of buttons) {
                        const txt = (btn.innerText || btn.textContent || "").toLowerCase();
                        if (txt.includes("密码") || txt.includes("password") || txt.includes("username")) {
                            passwordExecId = btn.value;
                            break;
                        }
                    }

                    const selForm = doc1.getElementById("kc-select-credential-form");
                    const targetAction = selForm ? selForm.action : actionUrl;

                    const form = document.createElement("form");
                    form.method = "POST";
                    form.action = targetAction;
                    const input = document.createElement("input");
                    input.type = "hidden";
                    input.name = "authenticationExecution";
                    input.value = passwordExecId || "";
                    form.appendChild(input);
                    document.body.appendChild(form);
                    form.submit();
                } catch (err) {
                    tryAnotherForm.requestSubmit();
                }
            };
        }
    }

    function fixPasswordEyeStyle() {
        const pwGroup = document.querySelector('.pf-c-input-group');
        const eyeBtn = document.querySelector('button[data-password-toggle], .pf-c-input-group button');
        const pwInput = document.getElementById('password');
        if (pwGroup) {
            pwGroup.style.position = 'relative';
            pwGroup.style.display = 'block';
            pwGroup.style.width = '100%';
            pwGroup.style.border = 'none';
            pwGroup.style.background = 'transparent';
        }
        if (pwInput) {
            pwInput.style.width = '100%';
            pwInput.style.boxSizing = 'border-box';
            pwInput.style.paddingRight = '48px';
            pwInput.style.paddingLeft = '16px';
            pwInput.style.height = '52px';
            pwInput.style.borderRadius = '14px';
        }
        if (eyeBtn) {
            eyeBtn.style.position = 'absolute';
            eyeBtn.style.right = '8px';
            eyeBtn.style.top = '50%';
            eyeBtn.style.transform = 'translateY(-50%)';
            eyeBtn.style.border = 'none';
            eyeBtn.style.background = 'transparent';
            eyeBtn.style.backgroundColor = 'transparent';
            eyeBtn.style.boxShadow = 'none';
            eyeBtn.style.outline = 'none';
            eyeBtn.style.padding = '0';
            eyeBtn.style.margin = '0';
            eyeBtn.style.zIndex = '20';
        }
    }

    function onInit() {
        fixPasswordEyeStyle();
        initPolicyAndPasskey();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", onInit);
    } else {
        onInit();
    }
})();
