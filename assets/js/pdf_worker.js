importScripts("https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js");

const PYODIDE_VERSION = 'v0.25.0';
// Bump the trailing integer whenever packages change so stale caches are evicted.
const PKG_CACHE_KEY = `nilpdf-pkgs-${PYODIDE_VERSION}-1`;

function withTimeout(promise, ms, label) {
    return Promise.race([
        promise,
        new Promise((_, reject) =>
            setTimeout(() => reject(new Error(`Timed out after ${ms / 1000}s: ${label}`)), ms)
        )
    ]);
}

// ── OPFS helpers ─────────────────────────────────────────────────────────────

async function loadPackagesFromOPFS(pyodide) {
    try {
        const root = await navigator.storage.getDirectory();
        const vHandle = await root.getFileHandle('pkg-version.txt').catch(() => null);
        if (!vHandle) return false;
        const version = await (await vHandle.getFile()).text();
        if (version.trim() !== PKG_CACHE_KEY) return false;

        const pkgHandle = await root.getFileHandle('packages.bin').catch(() => null);
        if (!pkgHandle) return false;
        const buf = await (await pkgHandle.getFile()).arrayBuffer();

        const view = new DataView(buf);
        let offset = 0;
        const numFiles = view.getUint32(offset); offset += 4;
        const dec = new TextDecoder();
        for (let i = 0; i < numFiles; i++) {
            const pathLen = view.getUint32(offset); offset += 4;
            const path = dec.decode(new Uint8Array(buf, offset, pathLen)); offset += pathLen;
            const dataLen = view.getUint32(offset); offset += 4;
            const data = new Uint8Array(buf, offset, dataLen); offset += dataLen;
            // Ensure parent dirs exist
            const parts = path.split('/');
            let cur = '';
            for (let j = 1; j < parts.length - 1; j++) {
                cur += '/' + parts[j];
                try { pyodide.FS.mkdir(cur); } catch (_) {}
            }
            pyodide.FS.writeFile(path, data);
        }
        return true;
    } catch (e) { return false; }
}

async function savePackagesToOPFS(pyodide) {
    try {
        const files = {};
        function walk(dir) {
            for (const name of pyodide.FS.readdir(dir)) {
                if (name === '.' || name === '..') continue;
                const full = dir + '/' + name;
                const stat = pyodide.FS.stat(full);
                if (pyodide.FS.isDir(stat.mode)) walk(full);
                else files[full] = pyodide.FS.readFile(full);
            }
        }
        walk('/lib/python3.11/site-packages');

        const enc = new TextEncoder();
        const entries = Object.entries(files);
        let totalBytes = 4;
        const encoded = entries.map(([p, d]) => {
            const pe = enc.encode(p);
            totalBytes += 4 + pe.byteLength + 4 + d.byteLength;
            return [pe, d];
        });

        const buf = new ArrayBuffer(totalBytes);
        const view = new DataView(buf);
        let offset = 0;
        view.setUint32(offset, entries.length); offset += 4;
        for (const [pe, d] of encoded) {
            view.setUint32(offset, pe.byteLength); offset += 4;
            new Uint8Array(buf, offset, pe.byteLength).set(pe); offset += pe.byteLength;
            view.setUint32(offset, d.byteLength); offset += 4;
            new Uint8Array(buf, offset, d.byteLength).set(d); offset += d.byteLength;
        }

        const root = await navigator.storage.getDirectory();
        const pkgH = await root.getFileHandle('packages.bin', { create: true });
        const w1 = await pkgH.createWritable(); await w1.write(buf); await w1.close();
        const verH = await root.getFileHandle('pkg-version.txt', { create: true });
        const w2 = await verH.createWritable(); await w2.write(PKG_CACHE_KEY); await w2.close();
    } catch (e) { /* non-fatal — OPFS write failures don't affect functionality */ }
}

// ── Boot ─────────────────────────────────────────────────────────────────────

async function bootEngine() {
    postMessage({ type: 'BOOT_PROGRESS', msg: 'Loading Python runtime…' });
    self.pyodide = await withTimeout(loadPyodide(), 60000, 'loadPyodide');

    postMessage({ type: 'BOOT_PROGRESS', msg: 'Checking package cache…' });
    const fromCache = await loadPackagesFromOPFS(self.pyodide);

    if (!fromCache) {
        postMessage({ type: 'BOOT_PROGRESS', msg: 'Installing packages (first visit ~30 s)…' });
        await withTimeout(self.pyodide.loadPackage("micropip"), 30000, 'loadPackage micropip');
        const micropip = self.pyodide.pyimport("micropip");
        await withTimeout(
            micropip.install(["pypdf", "cryptography", "Pillow", "reportlab"]),
            120000,
            'micropip.install'
        );
        // Save to OPFS in background — does not delay SYSTEM_READY
        savePackagesToOPFS(self.pyodide).catch(() => {});
    } else {
        postMessage({ type: 'BOOT_PROGRESS', msg: 'Packages ready (cached)…' });
    }

    self.reportProgress = (id, pct, msg) => {
        postMessage({ type: 'PROGRESS', id: String(id), pct: Number(pct), msg: String(msg) });
    };

    postMessage({ type: 'BOOT_PROGRESS', msg: 'Loading engine…' });
    const baseUrl = location.href.split('assets/js/')[0];
    const response = await fetch(baseUrl + 'core/pdf_engine.py?v=' + Date.now());
    const pythonCode = await response.text();
    self.pyodide.runPython(pythonCode);

    postMessage({ type: 'SYSTEM_READY' });
}

let engineBooting = bootEngine().catch(err => {
    postMessage({ type: 'BOOT_ERROR', error: err.message || String(err) });
});

// ── Message handler ───────────────────────────────────────────────────────────

self.onmessage = async (event) => {
    await engineBooting;
    const { id, action, payload } = event.data;

    try {
        let result_py;
        let isZip  = false;
        let isText = false;
        const password = payload.password || "";

        if (action === 'MERGE') {
            result_py = self.pyodide.globals.get('process_merge')(payload.buffers, id, password);
        } else if (action === 'SPLIT') {
            result_py = self.pyodide.globals.get('process_split')(payload.buffer, payload.indices, id, password);
        } else if (action === 'SPLIT_MULTI') {
            result_py = self.pyodide.globals.get('process_split_ranges')(payload.buffer, payload.ranges, id, password);
            isZip = true;
        } else if (action === 'REORDER') {
            result_py = self.pyodide.globals.get('process_reorder')(payload.buffer, payload.order, id, password);
        } else if (action === 'ANONYMIZE') {
            result_py = self.pyodide.globals.get('process_anonymize')(payload.buffer, id, password);
        } else if (action === 'COMPRESS') {
            result_py = self.pyodide.globals.get('process_compress')(payload.buffer, id, password);
        } else if (action === 'BULK_PROCESS') {
            result_py = self.pyodide.globals.get('process_bulk')(payload.sub_action, payload.names, payload.buffers, id, password);
            isZip = true;
        } else if (action === 'ROTATE') {
            result_py = self.pyodide.globals.get('process_rotate')(payload.buffer, payload.degrees, payload.indices, id, password);
        } else if (action === 'REMOVE_PAGES') {
            result_py = self.pyodide.globals.get('process_remove_pages')(payload.buffer, payload.indices, id, password);
        } else if (action === 'EXTRACT_TEXT') {
            result_py = self.pyodide.globals.get('process_extract_text')(payload.buffer, id, password);
            isText = true;
        } else if (action === 'WATERMARK') {
            result_py = self.pyodide.globals.get('process_watermark')(payload.buffer, payload.text, payload.opacity, id, password);
        } else if (action === 'ADD_PAGE_NUMBERS') {
            result_py = self.pyodide.globals.get('process_add_page_numbers')(payload.buffer, payload.position, payload.startNum, id, password);
        } else if (action === 'ADD_FOOTER') {
            result_py = self.pyodide.globals.get('process_add_footer')(payload.buffer, id, password);
        } else if (action === 'REPAIR') {
            result_py = self.pyodide.globals.get('process_repair')(payload.buffer, id, password);
        } else {
            throw new Error(`Unknown action: ${action}`);
        }

        const result_uint8 = result_py.toJs();
        result_py.destroy();

        postMessage({ type: 'SUCCESS', id, result: result_uint8, isZip, isText }, [result_uint8.buffer]);

    } catch (error) {
        let msg = error.message || String(error);
        if (msg.includes('Incorrect password') || msg.includes('password')) {
            msg = 'Incorrect or missing password.';
        }
        postMessage({ type: 'ERROR', id, error: msg });
    }
};
