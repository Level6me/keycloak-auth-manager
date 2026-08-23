// Passkey 极致直通登录脚本 (支持应用内直接拉起 Face ID / Touch ID / WebAuthn)
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

    function initPasskeyDirect() {
        const tryAnotherLink = document.getElementById("try-another-way");
        const tryAnotherForm = document.getElementById("kc-select-try-another-way-form");
        const isPasswordPage = !!document.getElementById("kc-form-login");
        const isWebAuthnPage = !!document.getElementById("kc-form-webauthn");

        if (isPasswordPage && tryAnotherLink && tryAnotherForm) {
            // 密码登录界面：链接显示为「使用 Passkey 登录」
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
                    // Step 1: 请求切换其他方式
                    const res1 = await fetch(actionUrl, {
                        method: "POST",
                        headers: { "Content-Type": "application/x-www-form-urlencoded" },
                        body: new URLSearchParams({ "tryAnotherWay": "on" })
                    });
                    if (!res1.ok) throw new Error("Step 1 failed");

                    const html1 = await res1.text();
                    const doc1 = new DOMParser().parseFromString(html1, "text/html");

                    // 寻找 Passkey / 安全密钥执行器 ID
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

                    // Step 2: 获取 WebAuthn Challenge 与表单参数
                    const selForm = doc1.getElementById("kc-select-credential-form");
                    const action2 = selForm ? selForm.action : actionUrl;

                    const res2 = await fetch(action2, {
                        method: "POST",
                        headers: { "Content-Type": "application/x-www-form-urlencoded" },
                        body: new URLSearchParams({ "authenticationExecution": passkeyExecId })
                    });
                    if (!res2.ok) throw new Error("Step 2 failed");

                    const html2 = await res2.text();

                    // 解析 WebAuthn 参数
                    const mChallenge = html2.match(/challenge\s*:\s*"([^"]+)"/);
                    const mRpId = html2.match(/rpId\s*:\s*"([^"]+)"/);
                    const mUV = html2.match(/userVerification\s*:\s*"([^"]+)"/);
                    const mAction = html2.match(/id="webauth"[^>]*action="([^"]+)"/);

                    if (!mChallenge || !mRpId || !window.PublicKeyCredential) {
                        // 降级：通过表单导航至 WebAuthn 页面
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

                    // Step 3: 原生触发 Face ID / Touch ID / Passkey 认证弹窗
                    const credential = await navigator.credentials.get({
                        publicKey: {
                            challenge: base64urlToBuffer(challenge),
                            rpId: rpId,
                            userVerification: userVerification
                        }
                    });

                    if (!credential) throw new Error("No credential returned");

                    // Step 4: 构造登录认证结果并提交至 Keycloak
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
                    console.warn("Passkey 直接认证取消或未成功:", err);
                    tryAnotherLink.innerHTML = originalText;
                    tryAnotherLink.style.pointerEvents = "auto";
                    tryAnotherLink.style.opacity = "1";
                }
            };
        } else if (isWebAuthnPage && tryAnotherLink && tryAnotherForm) {
            // WebAuthn 界面：链接显示为「使用密码登录」
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

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initPasskeyDirect);
    } else {
        initPasskeyDirect();
    }
})();
