self.addEventListener("push", (event) => {
    let payload = {};
    if (event.data) {
        try {
            payload = event.data.json();
        } catch (e) {
            payload = { message: event.data.text() };
        }
    }

    const title = payload.title || "Архив документов";
    const options = {
        body: payload.message || "",
        tag: payload.tag || "archive-notification",
        renotify: true,
        data: {
            document_id: payload.document_id || null,
        },
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

function resolveNotificationUrl(documentId) {
    const base = self.registration.scope.replace(/\/?$/, "/");
    if (documentId) {
        return base + "documents/" + documentId;
    }
    return base + "notifications";
}

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const targetUrl = resolveNotificationUrl(event.notification.data && event.notification.data.document_id);
    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
            for (const client of windowClients) {
                if ("focus" in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
            return undefined;
        })
    );
});
