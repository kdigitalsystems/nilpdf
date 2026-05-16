const CACHE = 'nilpdf-v4';
// pdf_worker.js is intentionally excluded — it must always be fetched fresh
// so stale cached workers (e.g. with broken boot sequences) never get stuck.
const SHELL = ['/', '/index.html', '/assets/css/main.css'];

self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL).catch(() => {})));
    self.skipWaiting();
});

self.addEventListener('activate', e => {
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
    // Override CSP with a permissive policy — eval() is required by Pyodide (WASM) and Google Analytics.
    // Deletion alone is not enough; explicitly setting ensures no restrictive policy survives.
    h.set('Content-Security-Policy', "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; worker-src * blob:;");
    h.delete('Content-Security-Policy-Report-Only');
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
}

self.addEventListener('fetch', e => {
    if (e.request.method !== 'GET') return;
    const reqPath = new URL(e.request.url).pathname;

    // Set COOP/COEP on navigation responses so Pyodide can use SharedArrayBuffer
    if (e.request.mode === 'navigate') {
        e.respondWith(
            fetch(e.request).then(addSecurityHeaders).catch(() => caches.match(e.request))
        );
        return;
    }

    // Also stamp COEP on the worker script so it inherits cross-origin isolation.
    // Without this, Chrome blocks the Worker and Pyodide can't start.
    if (reqPath.includes('pdf_worker.js')) {
        e.respondWith(fetch(e.request).then(addSecurityHeaders));
        return;
    }

    // Cache-first for app shell files (match by pathname, ignoring any query params)
    if (SHELL.some(path => reqPath === path || reqPath.endsWith(path))) {
        e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(res => {
            const clone = res.clone();
            caches.open(CACHE).then(c => c.put(e.request, clone));
            return res;
        })));
    }
});
