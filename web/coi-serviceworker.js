/*! coi-serviceworker v0.1.7 - Guido Zuidhof and contributors, licensed under MIT */
const DIY_ARCADE_CACHE = "diy-arcade-pwa-v1";
const DIY_ARCADE_CORE_ASSETS = [
    "./",
    "index.html",
    "manifest.webmanifest",
    "favicon.ico",
    "favicon-16.png",
    "favicon-32.png",
    "icons/icon-192.png",
    "icons/icon-512.png",
    "icons/maskable-192.png",
    "icons/maskable-512.png",
    "og-image.png",
];

function withIsolationHeaders(response) {
    if (!response || response.status === 0 || response.type === "opaque") {
        return response;
    }
    const headers = new Headers(response.headers);
    headers.set("Cross-Origin-Embedder-Policy", "credentialless");
    headers.set("Cross-Origin-Opener-Policy", "same-origin");
    return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers,
    });
}

if (typeof window === "undefined") {
    self.addEventListener("install", (event) => {
        event.waitUntil(
            caches.open(DIY_ARCADE_CACHE)
                .then((cache) => Promise.all(DIY_ARCADE_CORE_ASSETS.map((asset) => {
                    const request = new Request(asset, { cache: "reload" });
                    return fetch(request)
                        .then((response) => cache.put(request, withIsolationHeaders(response.clone())))
                        .catch(() => undefined);
                })))
                .then(() => self.skipWaiting())
        );
    });

    self.addEventListener("activate", (event) => {
        event.waitUntil(
            caches.keys()
                .then((keys) => Promise.all(keys
                    .filter((key) => key !== DIY_ARCADE_CACHE)
                    .map((key) => caches.delete(key))))
                .then(() => self.clients.claim())
        );
    });

    self.addEventListener("message", (event) => {
        if (event.data && event.data.type === "deregister") {
            event.waitUntil(
                self.registration.unregister()
                    .then(() => self.clients.matchAll())
                    .then((clients) => clients.forEach((client) => client.navigate(client.url)))
            );
        }
    });

    self.addEventListener("fetch", (event) => {
        const { request } = event;
        if (request.method !== "GET" || (request.cache === "only-if-cached" && request.mode !== "same-origin")) {
            return;
        }

        const requestUrl = new URL(request.url);
        const sameOrigin = requestUrl.origin === self.location.origin;
        const cacheable = sameOrigin && !request.headers.has("range");
        const networkRequest = request.mode === "no-cors"
            ? new Request(request, { credentials: "omit" })
            : request;

        event.respondWith(
            fetch(networkRequest)
                .then((response) => {
                    const isolated = withIsolationHeaders(response.clone());
                    if (cacheable && response.ok) {
                        caches.open(DIY_ARCADE_CACHE)
                            .then((cache) => cache.put(request, isolated.clone()))
                            .catch(() => undefined);
                    }
                    return isolated;
                })
                .catch(() => caches.match(request)
                    .then((cached) => {
                        if (cached) {
                            return withIsolationHeaders(cached.clone());
                        }
                        if (request.mode === "navigate") {
                            return caches.match("index.html")
                                .then((fallback) => fallback && withIsolationHeaders(fallback.clone()));
                        }
                        return Response.error();
                    }))
        );
    });
} else {
    (() => {
        const reloadKey = "diyArcadeServiceWorkerReloaded";
        const wasReloaded = window.sessionStorage.getItem(reloadKey);
        window.sessionStorage.removeItem(reloadKey);

        function reloadOnce(reason) {
            if (wasReloaded) {
                return;
            }
            window.sessionStorage.setItem(reloadKey, reason);
            window.location.reload();
        }

        if (!window.isSecureContext || !navigator.serviceWorker) {
            return;
        }

        navigator.serviceWorker.register(window.document.currentScript.src)
            .then((registration) => {
                if (navigator.serviceWorker.controller) {
                    return;
                }
                if (registration.active) {
                    reloadOnce("active");
                    return;
                }
                registration.addEventListener("updatefound", () => {
                    const worker = registration.installing;
                    if (!worker) {
                        return;
                    }
                    worker.addEventListener("statechange", () => {
                        if (worker.state === "activated") {
                            reloadOnce("activated");
                        }
                    });
                });
            })
            .catch((error) => {
                console.error("DIY Arcade service worker failed to register:", error);
            });
    })();
}
