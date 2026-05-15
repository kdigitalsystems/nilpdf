importScripts("https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js");

async function bootEngine() {
    self.pyodide = await loadPyodide();
    // Pyodide-native packages: fetched from the same CDN as pyodide.js and
    // cached by the browser after the first visit — no re-download on return visits.
    await self.pyodide.loadPackage(["Pillow", "cryptography"]);
    // PyPI-only packages still need micropip, but this is now a much smaller install.
    await self.pyodide.loadPackage("micropip");
    const micropip = self.pyodide.pyimport("micropip");
    await micropip.install(["pypdf", "reportlab"]);

    // Expose a JS-global progress reporter so Python can call it via `from js import reportProgress`
    self.reportProgress = (id, pct, msg) => {
        postMessage({ type: 'PROGRESS', id: String(id), pct: Number(pct), msg: String(msg) });
    };

    const baseUrl = location.href.split('assets/js/')[0];
    const response = await fetch(baseUrl + 'core/pdf_engine.py?v=' + Date.now());
    const pythonCode = await response.text();
    self.pyodide.runPython(pythonCode);

    postMessage({ type: 'SYSTEM_READY' });
}

let engineBooting = bootEngine();

self.onmessage = async (event) => {
    await engineBooting;
    const { id, action, payload } = event.data;

    try {
        let result_py;
        let isZip  = false;
        let isText = false;
        const password = payload.password || "";

        // ── Existing tools ──────────────────────────────────────────────
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

        // ── New tools (Part 3) ───────────────────────────────────────────
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
        }

        const result_uint8 = result_py.toJs();
        result_py.destroy();

        postMessage({ type: 'SUCCESS', id, result: result_uint8, isZip, isText }, [result_uint8.buffer]);

    } catch (error) {
        postMessage({ type: 'ERROR', id, error: error.message });
    }
};
