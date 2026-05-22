// __SW_VERSION__ is replaced by the commit SHA during CI (see .github/workflows/static.yml).
// Changing the cache name on every deploy forces the activate handler to delete all
// stale caches, so users always receive fresh files after a deployment.
const CACHE = 'nilpdf-__SW_VERSION__';

// Only pre-cache the bare minimum. CSS is loaded with a ?v= query string that
// changes every deploy, so it is intentionally excluded here — it will be cached
// automatically on first request with the versioned URL as the key.
const SHELL = ['/', '/index.html'];

self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL).catch(() => {})));
    // Activate immediately — don't wait for existing tabs to close
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    // Delete every cache whose name isn't the current one
    e.waitUntil(
        caches.keys()
            .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

function addSecurityHeaders(res) {
    if (!res || res.status === 0) return res;
    const h = new Headers(res.headers);
    h.set('Cross-Origin-Opener-Policy', 'same-origin');
    h.set('Cross-Origin-Embedder-Policy', 'credentialless');
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
}

self.addEventListener('fetch', e => {
    if (e.request.method !== 'GET') return;
    const reqPath = new URL(e.request.url).pathname;

    // Navigation requests (index.html): always try network first so the user
    // gets the latest HTML; fall back to cache only when offline.
    if (e.request.mode === 'navigate') {
        e.respondWith(
            fetch(e.request).then(addSecurityHeaders).catch(() => caches.match(e.request))
        );
        return;
    }

    // The worker script must always be fetched fresh and needs COEP so that
    // Chrome allows it to use SharedArrayBuffer (required by Pyodide).
    if (reqPath.includes('pdf_worker.js')) {
        e.respondWith(fetch(e.request).then(addSecurityHeaders));
        return;
    }

    // Assets (CSS, icons, JS, etc.): network-first so every online visit
    // gets the latest files; update the cache in the background; serve cache
    // only when the user is offline. Navigate requests are already handled above,
    // so SHELL paths never reach this branch.
    if (reqPath.startsWith('/assets/')) {
        e.respondWith(
            fetch(e.request)
                .then(res => {
                    const clone = res.clone();
                    caches.open(CACHE).then(c => c.put(e.request, clone));
                    return res;
                })
                .catch(() => caches.match(e.request))
        );
    }
});
