// 自动将「尝试其他方法」直通为「Passkey 登录」并在点击时直接调起生物识别/安全密钥
(function() {
    function setupPasskeyDirect() {
        const tryAnotherLink = document.getElementById("try-another-way");
        const tryAnotherForm = document.getElementById("kc-select-try-another-way-form");
        
        if (tryAnotherLink && tryAnotherForm) {
            // 设置文案为 Passkey 登录
            tryAnotherLink.innerHTML = "使用 Passkey 登录";
            tryAnotherLink.style.display = "inline-flex";
            tryAnotherLink.style.alignItems = "center";
            tryAnotherLink.style.justifyContent = "center";
            tryAnotherLink.style.gap = "6px";
            tryAnotherLink.style.cursor = "pointer";
            
            tryAnotherLink.onclick = async function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                tryAnotherLink.innerHTML = "正在启动 Passkey 登录...";
                tryAnotherLink.style.pointerEvents = "none";
                tryAnotherLink.style.opacity = "0.7";
                
                try {
                    const actionUrl = tryAnotherForm.action;
                    const res = await fetch(actionUrl, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/x-www-form-urlencoded"
                        },
                        body: new URLSearchParams({ "tryAnotherWay": "on" })
                    });
                    
                    if (!res.ok) {
                        tryAnotherForm.requestSubmit();
                        return;
                    }
                    
                    const html = await res.text();
                    const doc = new DOMParser().parseFromString(html, "text/html");
                    
                    // 查找包含 Passkey / 安全密钥 / WebAuthn 的执行器 ID
                    let passkeyExecId = null;
                    const buttons = doc.querySelectorAll("button[name='authenticationExecution']");
                    for (const btn of buttons) {
                        const txt = (btn.innerText || btn.textContent || "").toLowerCase();
                        if (txt.includes("密钥") || txt.includes("安全") || txt.includes("webauthn") || txt.includes("passkey")) {
                            passkeyExecId = btn.value;
                            break;
                        }
                    }
                    
                    if (passkeyExecId) {
                        // 直接通过 POST 跳转至 WebAuthn 认证界面
                        const targetForm = document.createElement("form");
                        targetForm.method = "POST";
                        const selForm = doc.getElementById("kc-select-credential-form");
                        targetForm.action = selForm ? selForm.action : actionUrl;
                        
                        const input = document.createElement("input");
                        input.type = "hidden";
                        input.name = "authenticationExecution";
                        input.value = passkeyExecId;
                        targetForm.appendChild(input);
                        
                        document.body.appendChild(targetForm);
                        targetForm.submit();
                    } else {
                        tryAnotherForm.requestSubmit();
                    }
                } catch (err) {
                    console.error("Passkey 直通跳转异常:", err);
                    tryAnotherForm.requestSubmit();
                }
            };
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setupPasskeyDirect);
    } else {
        setupPasskeyDirect();
    }
})();
