// __SW_VERSION__ is replaced by the commit SHA during CI (see .github/workflows/static.yml).
// Changing the cache name on every deploy forces the activate handler to delete all
// stale caches, so users always receive fresh files after a deployment.
const CACHE = 'nilpdf-__SW_VERSION__';

// Pre-cache the files the app cannot start without. All of them except the HTML
// are requested with a ?v=<build> query string, so they are listed here without
// one and looked up below with ignoreSearch — see the fetch handler.
//
// Pre-caching these is what makes offline work on the visit after the first one.
// A service worker does not control the page that registers it, so on a first
// visit these files are fetched straight from the network and never pass through
// the fetch handler that would have cached them. Without an install-time copy,
// the next load offline would serve index.html from cache and then fail to fetch
// app.js, leaving a page that renders but does nothing.
const SHELL = [
    '/',
    '/index.html',
    '/assets/css/main.css',
    '/assets/js/app.js',
    '/assets/js/pdf_worker.js',
    '/core/pdf_engine.py',
];

self.addEventListener('install', e => {
    // Cache each entry independently: addAll() is atomic, so one 404 would throw
    // away the whole pre-cache and silently leave the app with no offline copy.
    e.waitUntil(
        caches.open(CACHE).then(c => Promise.all(
            SHELL.map(url => c.add(url).catch(() => {}))
        ))
    );
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
            fetch(e.request).then(addSecurityHeaders)
                .catch(() => caches.match(e.request).then(addSecurityHeaders))
        );
        return;
    }

    // The worker script and Python engine source: network-first (so online
    // visits always get the latest code and COEP headers needed for
    // SharedArrayBuffer), but cached so the app can still boot offline after
    // the first successful visit.
    if (reqPath.includes('pdf_worker.js') || reqPath.includes('pdf_engine.py')) {
        e.respondWith(
            fetch(e.request)
                .then(res => {
                    const clone = res.clone();
                    caches.open(CACHE).then(c => c.put(e.request, clone));
                    return addSecurityHeaders(res);
                })
                .catch(() => caches.match(e.request, { ignoreSearch: true }).then(addSecurityHeaders))
        );
        return;
    }

    // Assets (CSS, icons, JS, etc.): network-first so every online visit
    // gets the latest files; update the cache in the background; serve cache
    // only when the user is offline. The SHELL assets are handled here too and
    // simply overwrite their pre-cached copy with the versioned one.
    if (reqPath.startsWith('/assets/')) {
        e.respondWith(
            fetch(e.request)
                .then(res => {
                    const clone = res.clone();
                    caches.open(CACHE).then(c => c.put(e.request, clone));
                    return res;
                })
                // ignoreSearch so ?v=<build> still matches the pre-cached copy.
                .catch(() => caches.match(e.request, { ignoreSearch: true }))
        );
    }
});
