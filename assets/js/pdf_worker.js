importScripts("https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js");

async function bootEngine() {
    self.pyodide = await loadPyodide();
    await self.pyodide.loadPackage("micropip");
    const micropip = self.pyodide.pyimport("micropip");
    await micropip.install(["pypdf", "cryptography"]);
    
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
        if (action === 'MERGE') {
            result_py = self.pyodide.globals.get('process_merge')(payload.buffers);
        } else if (action === 'SPLIT') {
            result_py = self.pyodide.globals.get('process_split')(payload.buffer, payload.indices);
        } else if (action === 'REORDER') {
            result_py = self.pyodide.globals.get('process_reorder')(payload.buffer, payload.order);
        } else if (action === 'ANONYMIZE') {
 	    const func = self.pyodide.globals.get('process_anonymize');
	    result_py = func(payload.buffer);
	}

        // Convert Python Proxy to standard JS Uint8Array
        const result_uint8 = result_py.toJs();
        result_py.destroy(); // Free memory

        postMessage({ type: 'SUCCESS', id, result: result_uint8 }, [result_uint8.buffer]);
        
    } catch (error) {
        postMessage({ type: 'ERROR', id, error: error.message });
    }
};
