const CACHE = 'nilpdf-v3';
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

self.addEventListener('fetch', e => {
    if (e.request.method !== 'GET') return;

    // Set COOP/COEP on navigation responses so Pyodide can use SharedArrayBuffer
    if (e.request.mode === 'navigate') {
        e.respondWith(
            fetch(e.request)
                .then(res => {
                    if (!res || res.status === 0) return res;
                    const h = new Headers(res.headers);
                    h.set('Cross-Origin-Opener-Policy', 'same-origin');
                    h.set('Cross-Origin-Embedder-Policy', 'credentialless');
                    return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
                })
                .catch(() => caches.match(e.request))
        );
        return;
    }

    // Cache-first for app shell files
    if (SHELL.some(path => e.request.url.endsWith(path) || e.request.url.endsWith(path + '?v=' + Date.now().toString().slice(0,8)))) {
        e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(res => {
            const clone = res.clone();
            caches.open(CACHE).then(c => c.put(e.request, clone));
            return res;
        })));
    }
});
