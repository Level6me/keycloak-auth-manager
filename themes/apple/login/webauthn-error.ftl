<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=false; section>
    <#if section = "title">
        ${msg("webauthn-error-title")}
    <#elseif section = "header">
        ${msg("webauthn-error-title")}
    <#elseif section = "form">
        <style>
            #kc-select-try-another-way-form,
            #try-another-way,
            a#try-another-way {
                display: none !important;
            }
        </style>
        <form id="kc-error-credential-form" class="${properties.kcFormClass!}" action="${url.loginAction}" method="post">
            <div class="${properties.kcFormGroupClass!}">
                <input type="hidden" id="executionValue" name="authenticationExecution"/>
                <input type="hidden" id="isAppended" name="isAppended" value="true"/>
            </div>

            <div class="${properties.kcFormGroupClass!}">
                <div id="kc-form-buttons" class="${properties.kcFormButtonsClass!}">
                    <input tabindex="4" onclick="window.history.back();"
                           class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}"
                           name="tryagain" id="kc-tryagain" type="button" value="${msg("doTryAgain")}"/>
                </div>
            </div>
        </form>
    </#if>
</@layout.registrationLayout>
