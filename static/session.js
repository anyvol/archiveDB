(function (global) {
    const SESSION_EXPIRED_DETAIL = 'session_expired';
    const DEFAULT_MESSAGE = 'Сессия истекла. Войдите в систему снова.';

    function loginUrl() {
        return document.body.dataset.loginUrl || '/login?expired=1';
    }

    function sessionExpiredMessage(data) {
        return (data && data.message) || DEFAULT_MESSAGE;
    }

    function isSessionExpiredPayload(data) {
        return data && data.detail === SESSION_EXPIRED_DETAIL;
    }

    function redirectToLogin(delayMs) {
        const url = loginUrl();
        if (delayMs && delayMs > 0) {
            window.setTimeout(function () {
                window.location.href = url;
            }, delayMs);
            return;
        }
        window.location.href = url;
    }

    async function authFetch(url, options) {
        const opts = Object.assign(
            {
                credentials: 'same-origin',
                redirect: 'manual',
            },
            options || {}
        );
        opts.headers = Object.assign({}, opts.headers || {});
        if (!opts.headers.Accept) {
            opts.headers.Accept = 'application/json';
        }

        const response = await fetch(url, opts);

        if (response.type === 'opaqueredirect' || response.status === 0) {
            return {
                response: response,
                sessionExpired: true,
                data: { detail: SESSION_EXPIRED_DETAIL, message: DEFAULT_MESSAGE },
            };
        }

        if (response.status === 401) {
            let data = null;
            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
                try {
                    data = await response.clone().json();
                } catch (e) {
                    data = null;
                }
            }
            if (isSessionExpiredPayload(data)) {
                return { response: response, sessionExpired: true, data: data };
            }
        }

        return { response: response, sessionExpired: false, data: null };
    }

    global.SessionAuth = {
        SESSION_EXPIRED_DETAIL: SESSION_EXPIRED_DETAIL,
        sessionExpiredMessage: sessionExpiredMessage,
        isSessionExpiredPayload: isSessionExpiredPayload,
        redirectToLogin: redirectToLogin,
        authFetch: authFetch,
    };
})(window);
