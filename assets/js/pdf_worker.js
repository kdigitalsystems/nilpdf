// Load the base Pyodide WASM engine
importScripts("https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js");

async function bootEngine() {
    self.pyodide = await loadPyodide();
    await self.pyodide.loadPackage("micropip");
    const micropip = self.pyodide.pyimport("micropip");
    
    // Install dependencies
    await micropip.install(["pypdf", "cryptography"]);
    
    // Dynamically fetch our Python logic based on the worker's location
    const baseUrl = location.href.split('assets/js/')[0];
    const response = await fetch(baseUrl + 'core/pdf_engine.py');
    const pythonCode = await response.text();
    
    // Inject the Python code into the WASM environment
    self.pyodide.runPython(pythonCode);
    
    // Tell the main thread we are ready to accept hardware workloads
    postMessage({ type: 'SYSTEM_READY' });
}

let engineBooting = bootEngine();

// Listen for tasks from the main UI thread
self.onmessage = async (event) => {
    await engineBooting; // Ensure boot is complete before processing
    
    const { id, action, payload } = event.data;
    
    try {
        let result_bytes;
        
        // Route the task to the correct Python function
        if (action === 'MERGE') {
            const merge_func = self.pyodide.globals.get('process_merge');
            result_bytes = merge_func(payload.buffers);
        } 
        else if (action === 'SPLIT') {
            const split_func = self.pyodide.globals.get('process_split');
            result_bytes = split_func(payload.buffer, payload.indices);
        }
        else if (action === 'REORDER') {
            const reorder_func = self.pyodide.globals.get('process_reorder');
            result_bytes = reorder_func(payload.buffer, payload.order);
        }

        // Send the compiled binary back to the main thread
        postMessage({ type: 'SUCCESS', id, result: result_bytes });
        
    } catch (error) {
        postMessage({ type: 'ERROR', id, error: error.message });
    }
};
