<#import "template.ftl" as layout>
<@layout.registrationLayout displayInfo=(realm.registrationAllowed && !registrationDisabled??); section>
    <#if section = "title">
        ${msg("webauthn-login-title")}
    <#elseif section = "header">
        ${msg("webauthn-login-title")}
    <#elseif section = "form">
        <div id="kc-form-webauthn" class="${properties.kcFormClass!}">
            <form id="webauth" action="${url.loginAction}" method="post">
                <input type="hidden" id="clientDataJSON" name="clientDataJSON"/>
                <input type="hidden" id="authenticatorData" name="authenticatorData"/>
                <input type="hidden" id="signature" name="signature"/>
                <input type="hidden" id="credentialId" name="credentialId"/>
                <input type="hidden" id="userHandle" name="userHandle"/>
                <input type="hidden" id="error" name="error"/>
            </form>

            <div class="${properties.kcFormGroupClass!} no-bottom-margin" style="text-align: center;">
                <#if authenticators??>
                    <form id="authn_select" class="${properties.kcFormClass!}">
                        <#list authenticators.authenticators as authenticator>
                            <input type="hidden" name="authn_use_chk" value="${authenticator.credentialId}"/>
                        </#list>
                    </form>
                </#if>

                <div id="kc-form-buttons" class="${properties.kcFormButtonsClass!}">
                    <input id="authenticateWebAuthnButton" type="button" autofocus="autofocus"
                           value="${msg("webauthn-doAuthenticate")}"
                           class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}"/>
                </div>
            </div>
        </div>

    <script type="module">
        <#outputformat "JavaScript">
        import { authenticateByWebAuthn } from "${url.resourcesPath}/js/webauthnAuthenticate.js";
        const authButton = document.getElementById('authenticateWebAuthnButton');
        function triggerAuth() {
            const input = {
                isUserIdentified : ${isUserIdentified},
                challenge : ${challenge?c},
                userVerification : ${userVerification?c},
                rpId : ${rpId?c},
                createTimeout : ${createTimeout?c},
                errmsg : ${msg("webauthn-unsupported-browser-text")?c}
            };
            authenticateByWebAuthn(input);
        }
        authButton.addEventListener("click", triggerAuth, { once: true });
        
        // 页面加载完成后立即自动调起 Passkey 弹窗
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", () => {
                setTimeout(triggerAuth, 50);
            });
        } else {
            setTimeout(triggerAuth, 50);
        }
        </#outputformat>
    </script>

    <#elseif section = "info">
        <#if realm.registrationAllowed && !registrationDisabled??>
            <div id="kc-registration">
                <span>${msg("noAccount")} <a tabindex="6" href="${url.registrationUrl}">${msg("doRegister")}</a></span>
            </div>
        </#if>
    </#if>
</@layout.registrationLayout>
