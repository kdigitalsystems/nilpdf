// NilPDF single-page app.
//
// Extracted verbatim from the inline <script> block that used to live in
// index.html. Loaded as a classic (non-module) script from the same position
// in the body, so top-level function declarations stay global and the inline
// on*= handlers in the markup keep working exactly as before.
//
// Build-version and feedback-endpoint placeholders in this file are replaced at
// deploy time by .github/workflows/static.yml, using a plain replace-all. Any
// code that needs to detect an unstamped build must therefore test the value's
// shape, never compare it to a second copy of the placeholder text.
    /** 1. THEME — auto-detect system preference **/
    const themeBtn  = document.getElementById('theme-toggle');
    const savedTheme = localStorage.getItem('theme') ||
        (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', savedTheme);
    themeBtn.onclick = () => {
        const t = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', t);
        localStorage.setItem('theme', t);
    };

    /** 2. WORKER BRIDGE **/
    if (!crossOriginIsolated && !sessionStorage.getItem('sw-coi-reload')) {
        sessionStorage.setItem('sw-coi-reload', '1');
        document.querySelectorAll('.status-message').forEach(el => {
            el.textContent = 'Finishing setup, reloading…';
            el.className = 'status-message is-loading';
        });
        setTimeout(() => location.reload(), 800);
    }

    let worker = null;
    let isReady = false;
    let pendingAction = null;
    let pendingCompressInfo = null;
    const pendingStats = {}; // { [statusId]: parsed __STATS__ payload from the last processing run }
    const pendingDownloads = {}; // keyed by status id, since multiple tools can have jobs in flight at once
    const pendingFooters = {};
    let lastLoadedFile = null;
    let lastLoadedTool = null;

    const _bv = '__BUILD_VERSION__';
    if (!_bv.startsWith('__')) {
        document.getElementById('build-version').textContent = 'build ' + _bv;
    }
    function stem(filename) { return filename.replace(/\.[^/.]+$/, ''); }
    function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

    function ensureWorker() {
        if (worker) return;
        worker = new Worker('./assets/js/pdf_worker.js?v=__BUILD_VERSION__');
        worker.onmessage = workerMessageHandler;
    }

    function runWhenReady(statusId, fn) {
        ensureWorker();
        if (isReady) { fn(); return; }
        if (pendingAction) {
            updateStatus(statusId, 'Engine already starting, please wait…', '');
            return;
        }
        pendingAction = fn;
        updateStatus(statusId, 'Starting engine…', '');
        document.getElementById(statusId).classList.add('is-loading');
    }

    function workerMessageHandler(e) {
        const { type, id, result, error, isZip, isText } = e.data;

        if (type === 'BOOT_PROGRESS') {
            document.querySelectorAll('.status-message').forEach(el => {
                if (el.textContent.startsWith('Starting') ||
                    el.textContent.startsWith('Loading') ||
                    el.textContent.startsWith('Installing') ||
                    el.textContent.startsWith('Checking') ||
                    el.textContent.startsWith('Packages') ||
                    el.textContent.startsWith('Initializing')) {
                    el.textContent = e.data.msg;
                    el.classList.add('is-loading');
                }
            });

        } else if (type === 'BOOT_ERROR') {
            document.querySelectorAll('.status-message').forEach(el => {
                if (el.textContent.startsWith('Starting') ||
                    el.textContent.startsWith('Loading') ||
                    el.textContent.startsWith('Installing') ||
                    el.textContent.startsWith('Checking') ||
                    el.textContent.startsWith('Packages')) {
                    el.textContent = e.data.error || 'Engine failed to load.';
                    el.className = 'status-message text-red';
                }
            });
            const retryWrap = document.createElement('div');
            retryWrap.style.cssText = 'margin-top:0.75rem;text-align:center';
            const retryBtn = document.createElement('button');
            retryBtn.className = 'secondary-btn';
            retryBtn.textContent = 'Retry';
            retryBtn.onclick = () => location.reload();
            retryWrap.appendChild(retryBtn);
            const activeSection = document.querySelector('.active-tool');
            if (activeSection) activeSection.appendChild(retryWrap);

        } else if (type === 'SYSTEM_READY') {
            isReady = true;
            renderMergeList();
            document.querySelectorAll('.status-message').forEach(el => {
                if (el.textContent.startsWith('Starting') ||
                    el.textContent.startsWith('Loading') ||
                    el.textContent.startsWith('Installing') ||
                    el.textContent.startsWith('Checking') ||
                    el.textContent.startsWith('Packages')) {
                    el.textContent = 'Waiting for a PDF.';
                    el.className = 'status-message';
                }
            });
            updateStatus("status", mergeFilesArray.length >= 2
                ? `${mergeFilesArray.length} files ready.`
                : "Add at least 2 PDFs to merge.", "");
            if (pendingAction) {
                const fn = pendingAction;
                pendingAction = null;
                fn();
            }

        } else if (type === 'PROGRESS') {
            if (e.data.msg.startsWith('__STATS__:')) {
                try { pendingStats[e.data.id] = JSON.parse(e.data.msg.slice('__STATS__:'.length)); } catch (_) {}
                return;
            }
            updateStatus(e.data.id, e.data.msg, "");
            const progBar = document.getElementById(e.data.id.replace('-status', '-progress'));
            if (progBar) {
                progBar.style.display = 'block';
                if (e.data.pct >= 95) {
                    progBar.removeAttribute('value');
                } else {
                    progBar.value = e.data.pct;
                }
            }

        } else if (type === 'SUCCESS') {
            if (pendingFooters[id] && !isZip && !isText) {
                pendingFooters[id] = false;
                const transferBuf = result instanceof Uint8Array ? result : new Uint8Array(result);
                worker.postMessage(
                    { id, action: 'ADD_FOOTER', payload: { buffer: transferBuf, password: '' } },
                    [transferBuf.buffer]
                );
                return;
            }

            let mime, ext;
            if (isText)     { mime = 'text/plain';        ext = 'txt'; }
            else if (isZip) { mime = 'application/zip';   ext = 'zip'; }
            else            { mime = 'application/pdf';   ext = 'pdf'; }

            const blob = new Blob([result], { type: mime });
            const url  = URL.createObjectURL(blob);
            const a    = document.createElement('a');
            a.href = url;
            a.download = pendingDownloads[id] || `NilPDF_Export_${Date.now()}.${ext}`;
            delete pendingDownloads[id];

            if (id === 'totext-status' && isText) {
                const text = new TextDecoder().decode(result);
                document.getElementById('totext-preview').value = text;
                document.getElementById('totext-preview-area').style.display = 'block';
            }

            a.click();
            URL.revokeObjectURL(url);
            incrementCounter(toolForJob(id));
            if (!sessionStorage.getItem('nilpdf_nudged')) {
                sessionStorage.setItem('nilpdf_nudged', '1');
                setTimeout(showShareNudge, 1800);
            }

            if (id === 'status') {
                mergeFilesArray = []; renderMergeList();
            }
            if (id === 'reorder-status') {
                document.getElementById('thumbnail-grid').innerHTML = '';
                document.getElementById('reorder-btn').style.display = 'none';
                document.getElementById('reorder-password').style.display = 'none';
                document.getElementById('reorder-footer-label').style.display = 'none';
                document.getElementById('reorder-upload').value = '';
            }

            if (id === 'compress-status' && pendingCompressInfo && !pendingCompressInfo.isBulk) {
                const orig = pendingCompressInfo.origSize;
                const now  = result.byteLength;
                const pct  = ((orig - now) / orig * 100).toFixed(1);
                const fmt  = n => (n / 1048576).toFixed(2) + ' MB';
                const secs = pendingCompressInfo.startedAt
                    ? ((performance.now() - pendingCompressInfo.startedAt) / 1000).toFixed(1) + 's'
                    : '';
                let msg;
                if (pct > 0) {
                    msg = `Done: ${fmt(orig)} → ${fmt(now)} (${pct}% smaller)${secs ? ', ' + secs : ''}`;
                } else if (now > orig) {
                    msg = `Done: this PDF was already optimized; the result (${fmt(now)}) was not smaller than the original (${fmt(orig)}).`;
                } else {
                    msg = `Done: ${fmt(orig)} → ${fmt(now)} (already optimized, no further reduction possible)${secs ? ', ' + secs : ''}`;
                }
                updateStatus(id, msg, "text-green");
            } else if (id === 'repair-status' && pendingStats[id] && !isZip) {
                const s = pendingStats[id];
                const warnings = s.skipped > 0 ? `, ${s.skipped} page(s) could not be recovered` : '';
                updateStatus(id, `Done: recovered ${s.recovered} of ${s.total} page(s)${warnings}. Please check the downloaded file opens correctly before relying on it.`, "text-green");
            } else if (id === 'anonymize-status' && pendingStats[id] && !isZip) {
                const s = pendingStats[id];
                updateStatus(id, `Done: removed ${s.removedCount} metadata field(s): ${s.removedFields.join(', ') || 'none found'}.`, "text-green");
            } else {
                updateStatus(id, "Done! File downloaded.", "text-green");
            }
            delete pendingStats[id];
            pendingCompressInfo = null;
            const doneBar = document.getElementById(id.replace('-status', '-progress'));
            if (doneBar) { doneBar.style.display = 'none'; doneBar.value = 0; }

        } else if (type === 'ERROR') {
            updateStatus(id, formatProcessingError(error, id), "text-red");
            pendingFooters[id] = false;
            delete pendingDownloads[id];
            pendingCompressInfo = null;
            const errBar = document.getElementById(id.replace('-status', '-progress'));
            if (errBar) { errBar.style.display = 'none'; errBar.value = 0; }
        }
    };

    /** Turn a raw engine error message into a specific, actionable one where possible. */
    function formatProcessingError(raw, id) {
        const msg = String(raw || '');
        // Unlock's own errors are already specific, complete, user-facing
        // sentences ("not protected", "needs the owner password", "incorrect
        // password") — every generic remap below would either mislead or
        // needlessly re-wrap them, so Unlock is passed straight through.
        if (id === 'unlock-status') return msg;
        const lower = msg.toLowerCase();
        if (lower.includes('password') || lower.includes('decrypt')) {
            return 'This PDF is password protected, or the password entered was incorrect. Enter the correct document password and try again.';
        }
        if (lower.includes('memory') || lower.includes('allocation failed') || lower.includes('out of memory')) {
            return 'Your browser ran out of memory while processing this document. Try closing other tabs, using a smaller file, or processing fewer pages at a time.';
        }
        if (lower.includes('no pages') || lower.includes('contains no pages')) {
            return "This PDF doesn't contain any pages NilPDF could read. Choose another file or try the Repair PDF tool.";
        }
        if (lower.includes('not a valid pdf') || lower.includes('could not read') || lower.includes('invalid pdf') || lower.includes('eof') || lower.includes("doesn't appear")) {
            return 'This file does not appear to be a valid PDF. Choose another file, or try the Repair PDF tool if it was partially downloaded or corrupted.';
        }
        return `Something went wrong while processing this file: ${msg}. If this keeps happening, please report it using the feedback button.`;
    }

    function setAllStatus(msg, cls) {
        document.querySelectorAll('.status-message').forEach(el => {
            el.textContent = msg;
            el.className   = `status-message ${cls}`;
        });
    }
    function updateStatus(id, msg, cls) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = msg;
        el.className = `status-message ${cls}`;
        el.classList.toggle('is-loading', !cls && (msg.endsWith('...') || msg.endsWith('…')));
    }

    /** 3. NAVIGATION **/
    const TOOL_META = {
        merge:    { title: 'Merge PDF',               desc: 'Combine multiple PDF files into one. Runs privately in your browser, zero uploads.' },
        compress: { title: 'Compress PDF',            desc: 'Optimize PDF structure and embedded resources to reduce file size. Results vary by document.' },
        anonymize:{ title: 'Remove Metadata',         desc: 'Strip all hidden metadata from a PDF privately. Zero uploads.' },
        split:    { title: 'Split PDF',               desc: 'Extract specific pages from a PDF. Runs locally in your browser. No uploads.' },
        reorder:  { title: 'Reorder PDF Pages',       desc: 'Drag and drop to reorder pages in any PDF. Your file never leaves your device.' },
        rotate:   { title: 'Rotate PDF Pages',        desc: 'Rotate any pages in a PDF. Runs entirely in your browser.' },
        remove:   { title: 'Remove PDF Pages',        desc: 'Delete unwanted pages from a PDF privately. No uploads.' },
        totext:   { title: 'PDF to Text',             desc: 'Extract all text from a PDF privately. Zero uploads. Runs in your browser.' },
        topng:    { title: 'PDF to Images',           desc: 'Convert PDF pages to PNG images. Runs locally. No uploads.' },
        topdf:    { title: 'Images to PDF',           desc: 'Combine images into a PDF file. Your images never leave your device.' },
        watermark:{ title: 'Add Watermark',           desc: 'Add a custom text watermark to any PDF. Runs in your browser.' },
        pagenums: { title: 'Add Page Numbers to PDF', desc: 'Stamp page numbers onto a PDF. Your file never leaves your device.' },
        inspect:  { title: 'Inspect PDF',             desc: 'View PDF metadata, page count, fonts and more. Zero uploads.' },
        repair:   { title: 'Repair PDF',              desc: 'Attempt to recover pages from a corrupted or truncated PDF. Runs privately in your browser.' },
        redact:   { title: 'Redact PDF',              desc: 'Permanently black out sensitive areas of a PDF and add custom text notes. Runs privately in your browser.' },
        edit:     { title: 'Edit PDF',                desc: 'Click anywhere to write text onto a PDF page. Runs privately in your browser.' },
        sign:     { title: 'Sign PDF',                desc: 'Draw, type, or upload a signature and place it on any page. Runs privately in your browser.' },
        fillform: { title: 'Fill PDF Forms',          desc: 'Fill in PDF form fields and optionally flatten them. Runs privately in your browser.' },
        protect:  { title: 'Protect PDF',             desc: 'Encrypt a PDF with a password using AES-256. Runs privately in your browser.' },
        fillsign: { title: 'Fill & Sign PDF',          desc: 'Fill in form fields, write in blanks or dates, and sign, all in one pass. Runs privately in your browser.' },
        unlock:   { title: 'Unlock PDF',              desc: 'Permanently remove password encryption from a PDF you have the password for. Runs privately in your browser.' },
    };

    const SINGLE_FILE_TOOLS = ['split','reorder','rotate','remove','totext','topng','watermark','pagenums','inspect','repair','redact','edit','sign','fillform','protect','fillsign','unlock'];

    /** Category filter **/
    let _activeCategory = 'all';
    let _searchTerm = '';

    function filterTools(cat) {
        _activeCategory = cat;
        document.querySelectorAll('.cat-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.cat === cat);
        });
        applyToolFilters();
    }

    function searchTools(term) {
        _searchTerm = term.trim().toLowerCase();
        applyToolFilters();
    }

    function applyToolFilters() {
        let visibleCount = 0;
        document.querySelectorAll('.tool-card').forEach(card => {
            const matchesCategory = _activeCategory === 'all' || card.dataset.category === _activeCategory;
            const text = card.textContent.toLowerCase();
            const matchesSearch = !_searchTerm || text.includes(_searchTerm);
            const visible = matchesCategory && matchesSearch;
            card.style.display = visible ? '' : 'none';
            if (visible) visibleCount++;
        });
        document.getElementById('tool-search-empty').hidden = visibleCount > 0;
    }

    document.querySelectorAll('.tool-card').forEach(card => {
        card.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                e.stopPropagation();
                card.click();
            }
        });
    });

    /** ── Navigation helpers ── **/
    let _skipTabHistory = false;   // prevents switchTab overwriting pushState

    // DOM-only: show the landing page (no history change)
    function _showLanding() {
        document.getElementById('workspace').style.display = 'none';
        document.getElementById('landing').style.display = '';
        document.getElementById('site-footer').style.display = '';
        document.title = 'NilPDF: Free PDF Tools. Zero Uploads.';
        document.querySelector('meta[property="og:title"]').setAttribute('content', 'NilPDF: Free PDF Tools. Zero Uploads.');
        document.querySelector('meta[property="og:description"]').setAttribute('content', '21 PDF tools. Zero uploads. Your files never leave your device.');
        document.querySelector('meta[name="twitter:title"]').setAttribute('content', 'NilPDF: Free PDF Tools. Zero Uploads.');
        document.querySelector('meta[name="twitter:description"]').setAttribute('content', '21 PDF tools in your browser. Zero uploads. Your files never leave your device.');
    }

    // DOM-only: show workspace for a tool (no history change)
    function _showWorkspace(toolId) {
        document.getElementById('landing').style.display = 'none';
        document.getElementById('site-footer').style.display = 'none';
        document.getElementById('workspace').style.display = '';
        const meta = TOOL_META[toolId];
        document.getElementById('workspace-title').textContent = meta ? meta.title : toolId;
        _skipTabHistory = true;
        const btn = document.querySelector(`.tab-btn[onclick*="'${toolId}'"]`);
        if (btn) btn.click();
        _skipTabHistory = false;
    }

    /** Public: open a tool (pushes a history entry so browser-back works) **/
    function openTool(toolId) {
        _showWorkspace(toolId);
        history.pushState({ view: 'tool', tool: toolId }, '', '#' + toolId);
    }

    /** Public: go back to landing page **/
    function goHome() {
        _showLanding();
        history.replaceState(null, '', location.pathname);
    }

    /** Handle browser Back / Forward buttons **/
    window.addEventListener('popstate', function (e) {
        if (e.state && e.state.view === 'tool') {
            _showWorkspace(e.state.tool);
        } else {
            _showLanding();
        }
    });

    /** Toggle the tab-bar's edge fades to only hint at whichever side still has
     * tabs scrolled out of view, instead of a static fade that would dim the
     * first/last tab even once there's nothing left to scroll to. **/
    function updateTabsFade() {
        const nav = document.querySelector('.workspace .tabs');
        if (!nav) return;
        nav.classList.toggle('has-hidden-start', nav.scrollLeft > 1);
        nav.classList.toggle('has-hidden-end', nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 1);
    }
    document.querySelector('.workspace .tabs')?.addEventListener('scroll', updateTabsFade, { passive: true });
    window.addEventListener('resize', updateTabsFade);
    updateTabsFade();

    function switchTab(event, tool) {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tool-section').forEach(s => {
            s.classList.remove('active-tool'); s.classList.add('hidden-tool');
        });
        event.target.classList.add('active');
        event.target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        updateTabsFade();
        document.getElementById(`tool-${tool}`).classList.replace('hidden-tool', 'active-tool');
        if (!_skipTabHistory) history.replaceState({ view: 'tool', tool }, '', '#' + tool);
        const meta = TOOL_META[tool];
        if (meta) {
            document.title = `NilPDF: ${meta.title} (Free, No Uploads)`;
            document.querySelector('meta[property="og:title"]').setAttribute('content', `NilPDF: ${meta.title}`);
            document.querySelector('meta[property="og:description"]').setAttribute('content', meta.desc);
            document.querySelector('meta[name="twitter:title"]').setAttribute('content', `NilPDF: ${meta.title}`);
            document.querySelector('meta[name="twitter:description"]').setAttribute('content', meta.desc);
            // Keep workspace title in sync when switching tabs
            document.getElementById('workspace-title').textContent = meta.title;
        }
        document.getElementById('persistent-file-banner')?.remove();
        if (lastLoadedFile && SINGLE_FILE_TOOLS.includes(tool) && tool !== lastLoadedTool) {
            const targetInput = document.getElementById(`${tool}-upload`);
            if (targetInput && !targetInput.files[0]) {
                const banner = document.createElement('div');
                banner.id = 'persistent-file-banner';
                banner.className = 'persistent-file-banner';
                const short = lastLoadedFile.name.length > 28
                    ? lastLoadedFile.name.slice(0, 25) + '…'
                    : lastLoadedFile.name;
                banner.innerHTML = `<span>Use <strong>${escHtml(short)}</strong>?</span>
                    <button class="nudge-copy-btn" id="pf-use-btn">Use it</button>
                    <button class="nudge-dismiss" id="pf-dismiss-btn" aria-label="Dismiss">✕</button>`;
                document.getElementById(`tool-${tool}`).prepend(banner);
                document.getElementById('pf-use-btn').onclick = () => {
                    const dt = new DataTransfer();
                    dt.items.add(lastLoadedFile);
                    targetInput.files = dt.files;
                    targetInput.dispatchEvent(new Event('change'));
                    banner.remove();
                };
                document.getElementById('pf-dismiss-btn').onclick = () => banner.remove();
            }
        }
    }

    /** 4. FILE SIZE VALIDATION **/
    const MAX_BYTES  = 200 * 1024 * 1024;
    const WARN_BYTES =  50 * 1024 * 1024;

    function validateFileSizes(files) {
        for (const f of files) {
            if (f.size > MAX_BYTES)
                return { ok: false, msg: `"${f.name}" is ${(f.size / 1048576).toFixed(1)} MB, exceeds 200 MB limit.` };
        }
        const total = Array.from(files).reduce((s, f) => s + f.size, 0);
        if (total > WARN_BYTES)
            return { ok: true, warn: `Large files (${(total / 1048576).toFixed(1)} MB total), processing may take a while.` };
        return { ok: true };
    }

    /** 5. SHARED HELPERS **/
    async function toUint8(file) { return new Uint8Array(await file.arrayBuffer()); }
    async function toUint8All(files) { return Promise.all(Array.from(files).map(toUint8)); }

    function checkReady(statusId) {
        if (!isReady) {
            updateStatus(statusId, 'Engine still loading, please wait.', 'text-red');
            return false;
        }
        return true;
    }

    function parseRangePart(part) {
        const indices = [];
        part = part.trim();
        if (part.includes('-')) {
            let [s, e] = part.split('-').map(n => parseInt(n.trim()));
            if (!isNaN(s) && !isNaN(e)) {
                if (s > e) [s, e] = [e, s];
                for (let i = s; i <= e; i++) indices.push(i - 1);
            }
        } else {
            const n = parseInt(part);
            if (!isNaN(n)) indices.push(n - 1);
        }
        return indices;
    }

    /** Compress a sorted array of 0-based page indices into a "1, 3-5" 1-based range string. */
    function indicesToRangeString(indices) {
        const sorted = [...new Set(indices)].sort((a, b) => a - b);
        if (!sorted.length) return '';
        const parts = [];
        let start = sorted[0], prev = sorted[0];
        for (let i = 1; i <= sorted.length; i++) {
            const cur = sorted[i];
            if (cur === prev + 1) { prev = cur; continue; }
            parts.push(start === prev ? `${start + 1}` : `${start + 1}-${prev + 1}`);
            start = prev = cur;
        }
        return parts.join(', ');
    }

    /** Render page thumbnails for a pdf.js document into `grid`. onWrapperCreated(wrapper, index)
     *  fires right after each wrapper is appended, before its canvas finishes rendering.
     *  isStale() is checked before each page so a superseded render can bail out early. */
    async function renderThumbnailGrid(grid, pdf, { onWrapperCreated, isStale } = {}) {
        grid.innerHTML = '';
        for (let i = 1; i <= pdf.numPages; i++) {
            if (isStale && isStale()) return;
            const page = await pdf.getPage(i);
            const viewport = page.getViewport({ scale: 0.3 });
            const wrapper = document.createElement('div');
            wrapper.className = 'thumbnail-item'; wrapper.dataset.index = i - 1;
            const canvas = document.createElement('canvas');
            canvas.width = viewport.width; canvas.height = viewport.height;
            wrapper.appendChild(canvas);
            const badge = document.createElement('span');
            badge.className = 'page-badge'; badge.innerText = i;
            wrapper.appendChild(badge);
            grid.appendChild(wrapper);
            if (onWrapperCreated) onWrapperCreated(wrapper, i - 1);
            await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
        }
    }

    /** Toggle .className on each thumbnail whose index is in `indices` (null = all). */
    function highlightThumbnails(grid, indices, className = 'selected') {
        if (!grid) return;
        Array.from(grid.children).forEach(el => {
            const idx = parseInt(el.dataset.index);
            const on = indices === null || indices.includes(idx);
            el.classList.toggle(className, on);
            el.setAttribute('aria-checked', on ? 'true' : 'false');
        });
    }

    /** Make a thumbnail grid clickable/keyboard-operable, calling onToggle(index) per activation. */
    function makeThumbnailsSelectable(wrapper, idx, onToggle) {
        wrapper.classList.add('selectable');
        wrapper.setAttribute('role', 'checkbox');
        wrapper.setAttribute('tabindex', '0');
        wrapper.setAttribute('aria-checked', 'false');
        wrapper.setAttribute('aria-label', `Page ${idx + 1}`);
        wrapper.addEventListener('click', () => onToggle(idx));
        wrapper.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                e.stopPropagation();
                onToggle(idx);
            }
        });
    }

    function parsePageRange(rangeStr) {
        const indices = [];
        rangeStr.replace(/\s/g, '').split(',').forEach(p => indices.push(...parseRangePart(p)));
        return [...new Set(indices)].sort((a, b) => a - b);
    }

    /** 6. DRAG & DROP **/
    function bindDrop(zoneId, onDrop) {
        const zone = document.getElementById(zoneId);
        ['dragover', 'dragleave', 'drop'].forEach(evt =>
            zone.addEventListener(evt, e => { e.preventDefault(); e.stopPropagation(); }));
        zone.addEventListener('dragover',  () => zone.classList.add('drag-active'));
        zone.addEventListener('dragleave', () => zone.classList.remove('drag-active'));
        zone.addEventListener('drop', e => { zone.classList.remove('drag-active'); onDrop(e.dataTransfer.files); });
    }

    function bindSimpleDrop(zoneId, inputEl) {
        bindDrop(zoneId, files => {
            inputEl.files = files;
            inputEl.dispatchEvent(new Event('change'));
        });
    }

    /** ════ MERGE ════════════════════════════════════════════════════════════ */
    const mInput = document.getElementById('pdf-upload');
    let mergeFilesArray = [], fileIdCounter = 0, mergeSortable = null;

    function addMergeFiles(fileList) {
        for (const f of fileList) mergeFilesArray.push({ id: fileIdCounter++, file: f });
        renderMergeList();
    }
    function removeMergeFile(fileId) {
        mergeFilesArray = mergeFilesArray.filter(item => item.id !== fileId);
        renderMergeList();
    }
    function renderMergeList() {
        const list  = document.getElementById('file-list');
        list.innerHTML = '';
        mergeFilesArray.forEach(item => {
            const li = document.createElement('li');
            li.className = 'file-list-item';
            li.dataset.fileId = item.id;
            const kb = item.file.size < 1048576
                ? (item.file.size / 1024).toFixed(0) + ' KB'
                : (item.file.size / 1048576).toFixed(1) + ' MB';
            li.innerHTML =
                `<span class="drag-handle" title="Drag to reorder">⠿</span>` +
                `<span class="file-name">📄 ${escHtml(item.file.name)}</span>` +
                `<span class="file-size-badge">${kb}</span>` +
                `<button class="remove-file-btn" onclick="removeMergeFile(${item.id})" title="Remove" aria-label="Remove file">×</button>`;
            list.appendChild(li);
        });
        const count = mergeFilesArray.length;
        document.getElementById('merge-btn').disabled = count < 2;
        updateStatus('status', count === 0
            ? 'Add at least 2 PDFs to merge.'
            : count === 1 ? '1 file added, need at least one more.'
            : `${count} files ready to merge.`, count >= 2 ? 'text-green' : '');
        if (mergeSortable) { mergeSortable.destroy(); mergeSortable = null; }
        if (count > 1) {
            mergeSortable = new Sortable(list, {
                animation: 150, handle: '.drag-handle', dataIdAttr: 'data-file-id',
                onEnd: () => {
                    const newOrder = Array.from(list.children).map(el => parseInt(el.dataset.fileId));
                    const map = new Map(mergeFilesArray.map(i => [i.id, i.file]));
                    mergeFilesArray = newOrder.map(id => ({ id, file: map.get(id) })).filter(x => x.file);
                }
            });
        }
    }
    mInput.onchange = () => { addMergeFiles(mInput.files); mInput.value = ''; };
    bindDrop('drop-zone-merge', files => addMergeFiles(files));

    document.getElementById('merge-btn').onclick = async () => {
        if (mergeFilesArray.length < 2) { updateStatus('status', 'Add at least 2 PDFs.', 'text-red'); return; }
        const check = validateFileSizes(mergeFilesArray.map(i => i.file));
        if (!check.ok) { updateStatus('status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('status', check.warn, '');
        const password = document.getElementById('merge-password').value;
        const buffers = await toUint8All(mergeFilesArray.map(item => item.file));
        const count = mergeFilesArray.length;
        pendingDownloads['status'] = 'merged.pdf';
        runWhenReady('status', () => {
            pendingFooters['status'] = document.getElementById('merge-footer')?.checked ?? false;
            updateStatus('status', `Merging ${count} files...`, '');
            worker.postMessage({ id: 'status', action: 'MERGE', payload: { buffers, password } }, buffers.map(b => b.buffer));
        });
    };

    /** ════ COMPRESS ═════════════════════════════════════════════════════════ */
    const cInput = document.getElementById('compress-upload');

    function updateFileList(inputEl, listId, statusId) {
        const list = document.getElementById(listId);
        list.innerHTML = '';
        Array.from(inputEl.files).forEach(f => {
            const li = document.createElement('li');
            li.textContent = `📄 ${f.name}`;
            list.appendChild(li);
        });
        updateStatus(statusId, `${inputEl.files.length} file(s) selected.`, 'text-green');
    }

    cInput.onchange = () => updateFileList(cInput, 'compress-list', 'compress-status');
    bindSimpleDrop('drop-zone-compress', cInput);

    document.getElementById('compress-btn').onclick = async () => {
        const files = cInput.files;
        if (!files.length) { updateStatus('compress-status', 'Select at least one PDF.', 'text-red'); return; }
        const check = validateFileSizes(files);
        if (!check.ok) { updateStatus('compress-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('compress-status', check.warn, '');
        const password = document.getElementById('compress-password').value;
        const names = Array.from(files).map(f => f.name);
        const buffers = await toUint8All(files);
        const single = files.length === 1;
        const origSize = files[0].size; const fname = files[0].name; const fcount = files.length;
        runWhenReady('compress-status', () => {
            updateStatus('compress-status', `Compressing ${fcount} file(s)...`, '');
            if (single) {
                pendingFooters['compress-status'] = document.getElementById('compress-footer')?.checked ?? false;
                pendingCompressInfo = { origSize, isBulk: false, startedAt: performance.now() };
                pendingDownloads['compress-status'] = stem(fname) + '_compressed.pdf';
                worker.postMessage({ id: 'compress-status', action: 'COMPRESS', payload: { buffer: buffers[0], password } }, [buffers[0].buffer]);
            } else {
                pendingFooters['compress-status'] = false;
                pendingCompressInfo = { isBulk: true };
                pendingDownloads['compress-status'] = 'compressed_batch.zip';
                worker.postMessage({ id: 'compress-status', action: 'BULK_PROCESS', payload: { sub_action: 'COMPRESS', names, buffers, password } }, buffers.map(b => b.buffer));
            }
        });
    };

    /** ════ ANONYMIZE ════════════════════════════════════════════════════════ */
    const aInput = document.getElementById('anonymize-upload');
    aInput.onchange = () => updateFileList(aInput, 'anonymize-list', 'anonymize-status');
    bindSimpleDrop('drop-zone-anonymize', aInput);

    document.getElementById('anonymize-btn').onclick = async () => {
        const files = aInput.files;
        if (!files.length) { updateStatus('anonymize-status', 'Select at least one PDF.', 'text-red'); return; }
        const check = validateFileSizes(files);
        if (!check.ok) { updateStatus('anonymize-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('anonymize-status', check.warn, '');
        const password = document.getElementById('anonymize-password').value;
        const names = Array.from(files).map(f => f.name);
        const buffers = await toUint8All(files);
        const single = files.length === 1;
        const fname = files[0].name; const fcount = files.length;
        runWhenReady('anonymize-status', () => {
            pendingFooters['anonymize-status'] = false;
            updateStatus('anonymize-status', `Removing metadata from ${fcount} file(s)...`, '');
            if (single) {
                pendingDownloads['anonymize-status'] = stem(fname) + '_metadata_removed.pdf';
                worker.postMessage({ id: 'anonymize-status', action: 'ANONYMIZE', payload: { buffer: buffers[0], password } }, [buffers[0].buffer]);
            } else {
                pendingDownloads['anonymize-status'] = 'metadata_removed_batch.zip';
                worker.postMessage({ id: 'anonymize-status', action: 'BULK_PROCESS', payload: { sub_action: 'ANONYMIZE', names, buffers, password } }, buffers.map(b => b.buffer));
            }
        });
    };

    /** ════ SPLIT ════════════════════════════════════════════════════════════ */
    const sInput = document.getElementById('split-upload');
    let splitTotalPages = 0;

    sInput.onchange = async () => {
        const f = sInput.files[0];
        if (!f) return;
        lastLoadedFile = f; lastLoadedTool = 'split';
        splitTotalPages = 0;
        document.getElementById('page-range').value = '';
        document.getElementById('range-preview').textContent = '';
        updateStatus('split-status', `Loading ${f.name}...`, '');
        try {
            const password = document.getElementById('split-password').value;
            const pdf = await pdfjsLib.getDocument({ data: await f.arrayBuffer(), password: password || undefined }).promise;
            splitTotalPages = pdf.numPages;
            updateStatus('split-status', `${f.name}, ${splitTotalPages} page(s)`, 'text-green');
            validateSplitRange();
        } catch (err) {
            const msg = err.name === 'PasswordException'
                ? 'This PDF is password protected, or the password entered was incorrect. Enter the correct document password and try again.'
                : `Could not read "${f.name}": ${err.message || 'invalid PDF'}`;
            updateStatus('split-status', msg, 'text-red');
        }
    };
    bindSimpleDrop('drop-zone-split', sInput);

    document.getElementById('page-range').addEventListener('input', validateSplitRange);
    document.getElementById('split-multi').addEventListener('change', () => {
        const multi = document.getElementById('split-multi').checked;
        document.getElementById('page-range-label').textContent = multi
            ? 'Page groups, comma-separated (e.g. 1-3, 4-6, 7):'
            : 'Pages to extract (e.g. 1, 3-5):';
        document.getElementById('split-help').textContent = multi
            ? 'Each group becomes a separate PDF, downloaded as a ZIP.'
            : 'All selected pages combined into one PDF.';
        document.getElementById('split-btn').textContent = multi ? 'Split into Files' : 'Extract Pages';
        validateSplitRange();
    });

    function validateSplitRange() {
        const range   = document.getElementById('page-range').value.trim();
        const preview = document.getElementById('range-preview');
        if (!range || !splitTotalPages) { preview.textContent = ''; return; }
        const multi = document.getElementById('split-multi').checked;
        if (multi) {
            const groups = range.replace(/\s/g, '').split(',').map(p => parseRangePart(p)).filter(g => g.length);
            preview.textContent = `→ ${groups.length} separate file(s)`;
            preview.className   = 'range-preview text-green';
            return;
        }
        const indices = parsePageRange(range);
        const invalid = indices.filter(i => i < 0 || i >= splitTotalPages);
        if (invalid.length) {
            preview.textContent = `⚠ Page(s) ${invalid.map(i => i + 1).join(', ')} out of range (1-${splitTotalPages})`;
            preview.className   = 'range-preview text-red';
        } else if (indices.length) {
            preview.textContent = `✓ ${indices.length} page(s) of ${splitTotalPages}`;
            preview.className   = 'range-preview text-green';
        } else { preview.textContent = ''; }
    }

    document.getElementById('split-btn').onclick = async () => {
        const range = document.getElementById('page-range').value.trim();
        if (!sInput.files.length || !range) { updateStatus('split-status', 'Select a PDF and enter page numbers.', 'text-red'); return; }
        const check = validateFileSizes([sInput.files[0]]);
        if (!check.ok) { updateStatus('split-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('split-status', check.warn, '');
        const password = document.getElementById('split-password').value;
        const buffer   = await toUint8(sInput.files[0]);
        const multi    = document.getElementById('split-multi').checked;
        const fname    = sInput.files[0].name;
        if (multi) {
            const groups = range.replace(/\s/g, '').split(',').map(p => parseRangePart(p)).filter(g => g.length);
            if (!groups.length) { updateStatus('split-status', 'Enter valid page ranges.', 'text-red'); return; }
            pendingDownloads['split-status'] = stem(fname) + '_split.zip';
            runWhenReady('split-status', () => {
                pendingFooters['split-status'] = false;
                updateStatus('split-status', `Splitting into ${groups.length} file(s)...`, '');
                worker.postMessage({ id: 'split-status', action: 'SPLIT_MULTI', payload: { buffer, ranges: groups, password } }, [buffer.buffer]);
            });
        } else {
            const indices = parsePageRange(range);
            if (!indices.length) { updateStatus('split-status', 'Enter valid page numbers.', 'text-red'); return; }
            pendingDownloads['split-status'] = stem(fname) + '_split.pdf';
            runWhenReady('split-status', () => {
                pendingFooters['split-status'] = document.getElementById('split-footer')?.checked ?? false;
                updateStatus('split-status', 'Extracting pages...', '');
                worker.postMessage({ id: 'split-status', action: 'SPLIT', payload: { buffer, indices, password } }, [buffer.buffer]);
            });
        }
    };

    /** ════ REORDER ══════════════════════════════════════════════════════════ */
    const rInput = document.getElementById('reorder-upload');
    let sortable, reorderVersion = 0;
    rInput.onchange = async () => {
        const file = rInput.files[0];
        if (!file) return;
        lastLoadedFile = file; lastLoadedTool = 'reorder';
        const myVersion = ++reorderVersion;
        const grid = document.getElementById('thumbnail-grid');
        grid.innerHTML = '';
        document.getElementById('reorder-btn').style.display = 'none';
        document.getElementById('reorder-password').style.display = 'none';
        updateStatus('reorder-status', 'Generating previews...', '');
        let pdf;
        try {
            const password = document.getElementById('reorder-password').value;
            pdf = await pdfjsLib.getDocument({ data: await file.arrayBuffer(), password: password || undefined }).promise;
        } catch (err) {
            if (err.name === 'PasswordException') {
                document.getElementById('reorder-password').style.display = 'block';
                updateStatus('reorder-status', 'Incorrect or missing password. Enter it above and re-select the file.', 'text-red');
            } else {
                updateStatus('reorder-status', `Could not read "${file.name}": ${err.message || 'invalid PDF'}`, 'text-red');
            }
            return;
        }
        await renderThumbnailGrid(grid, pdf, { isStale: () => reorderVersion !== myVersion });
        if (reorderVersion !== myVersion) return;
        document.getElementById('reorder-btn').style.display   = 'block';
        document.getElementById('reorder-password').style.display = 'block';
        document.getElementById('reorder-footer-label').style.display = 'block';
        updateStatus('reorder-status', 'Drag to rearrange, then save.', 'text-green');
        if (sortable) sortable.destroy();
        sortable = new Sortable(grid, { animation: 150 });
    };
    bindSimpleDrop('drop-zone-reorder', rInput);

    document.getElementById('reorder-btn').onclick = async () => {
        const order    = Array.from(document.getElementById('thumbnail-grid').children).map(el => parseInt(el.dataset.index));
        const password = document.getElementById('reorder-password').value;
        const buffer   = await toUint8(rInput.files[0]);
        pendingDownloads['reorder-status'] = stem(rInput.files[0].name) + '_reordered.pdf';
        runWhenReady('reorder-status', () => {
            pendingFooters['reorder-status'] = document.getElementById('reorder-footer')?.checked ?? false;
            updateStatus('reorder-status', 'Saving new order...', '');
            worker.postMessage({ id: 'reorder-status', action: 'REORDER', payload: { buffer, order, password } }, [buffer.buffer]);
        });
    };

    /** ════ ROTATE ═══════════════════════════════════════════════════════════ */
    const rotateInput = document.getElementById('rotate-upload');
    let rotateTotalPages = 0, rotateThumbVersion = 0;

    rotateInput.onchange = async () => {
        const f = rotateInput.files[0];
        if (!f) return;
        lastLoadedFile = f; lastLoadedTool = 'rotate';
        rotateTotalPages = 0;
        document.getElementById('rotate-pages').value = '';
        const myVersion = ++rotateThumbVersion;
        const grid = document.getElementById('rotate-thumbnail-grid');
        grid.innerHTML = '';
        document.getElementById('rotate-thumb-toolbar').style.display = 'none';
        updateStatus('rotate-status', `Loading ${f.name}...`, '');
        try {
            const password = document.getElementById('rotate-password').value;
            const pdf = await pdfjsLib.getDocument({ data: await f.arrayBuffer(), password: password || undefined }).promise;
            rotateTotalPages = pdf.numPages;
            updateStatus('rotate-status', `${f.name}, ${rotateTotalPages} page(s)`, 'text-green');
            await renderThumbnailGrid(grid, pdf, {
                isStale: () => rotateThumbVersion !== myVersion,
                onWrapperCreated: (wrapper, idx) => makeThumbnailsSelectable(wrapper, idx, toggleRotateThumbnail)
            });
            if (rotateThumbVersion !== myVersion) return;
            document.getElementById('rotate-thumb-toolbar').style.display = 'flex';
            validateRotateRange();
        } catch (err) {
            const msg = err.name === 'PasswordException'
                ? 'This PDF is password protected, or the password entered was incorrect. Enter the correct document password and try again.'
                : `Could not read "${f.name}": ${err.message || 'invalid PDF'}`;
            updateStatus('rotate-status', msg, 'text-red');
        }
    };
    bindSimpleDrop('drop-zone-rotate', rotateInput);
    document.getElementById('rotate-pages').addEventListener('input', validateRotateRange);
    document.getElementById('rotate-degrees').addEventListener('change', validateRotateRange);

    function toggleRotateThumbnail(idx) {
        const current = document.getElementById('rotate-pages').value.trim();
        const indices = current ? parsePageRange(current) : [];
        const pos = indices.indexOf(idx);
        if (pos === -1) indices.push(idx); else indices.splice(pos, 1);
        document.getElementById('rotate-pages').value = indicesToRangeString(indices);
        validateRotateRange();
    }

    function validateRotateRange() {
        const range   = document.getElementById('rotate-pages').value.trim();
        const preview = document.getElementById('rotate-preview');
        const grid    = document.getElementById('rotate-thumbnail-grid');
        const degrees = parseInt(document.getElementById('rotate-degrees').value) || 0;
        if (!rotateTotalPages) { preview.textContent = ''; return; }
        if (!range) {
            preview.textContent = `No pages selected, leave blank to rotate all ${rotateTotalPages}, or click pages below to rotate only those`;
            preview.className   = 'range-preview';
            highlightThumbnails(grid, []);
            applyRotationPreview(grid, [], degrees);
            return;
        }
        const indices = parsePageRange(range);
        const invalid = indices.filter(i => i < 0 || i >= rotateTotalPages);
        const valid   = indices.filter(i => i >= 0 && i < rotateTotalPages);
        if (invalid.length) {
            preview.textContent = `⚠ Page(s) ${invalid.map(i => i + 1).join(', ')} out of range (1-${rotateTotalPages})`;
            preview.className   = 'range-preview text-red';
        } else {
            preview.textContent = `✓ Rotating ${indices.length} page(s)`;
            preview.className   = 'range-preview text-green';
        }
        highlightThumbnails(grid, valid);
        applyRotationPreview(grid, valid, degrees);
    }

    function applyRotationPreview(grid, indices, degrees) {
        if (!grid) return;
        Array.from(grid.children).forEach(el => {
            const idx = parseInt(el.dataset.index);
            const on = indices === null || indices.includes(idx);
            const canvas = el.querySelector('canvas');
            if (canvas) canvas.style.transform = on ? `rotate(${degrees}deg)` : '';
        });
    }

    document.getElementById('rotate-btn').onclick = async () => {
        if (!rotateInput.files[0]) { updateStatus('rotate-status', 'Select a PDF first.', 'text-red'); return; }
        const check = validateFileSizes([rotateInput.files[0]]);
        if (!check.ok) { updateStatus('rotate-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('rotate-status', check.warn, '');
        const degrees  = parseInt(document.getElementById('rotate-degrees').value);
        const pagesStr = document.getElementById('rotate-pages').value.trim();
        const indices  = pagesStr ? parsePageRange(pagesStr) : [];
        const password = document.getElementById('rotate-password').value;
        const buffer   = await toUint8(rotateInput.files[0]);
        pendingDownloads['rotate-status'] = stem(rotateInput.files[0].name) + '_rotated.pdf';
        runWhenReady('rotate-status', () => {
            pendingFooters['rotate-status'] = document.getElementById('rotate-footer')?.checked ?? false;
            updateStatus('rotate-status', 'Rotating pages...', '');
            worker.postMessage({ id: 'rotate-status', action: 'ROTATE', payload: { buffer, degrees, indices, password } }, [buffer.buffer]);
        });
    };

    /** ════ REMOVE PAGES ═════════════════════════════════════════════════════ */
    const removeInput = document.getElementById('remove-upload');
    let removeTotalPages = 0, removeThumbVersion = 0;

    removeInput.onchange = async () => {
        const f = removeInput.files[0];
        if (!f) return;
        lastLoadedFile = f; lastLoadedTool = 'remove';
        removeTotalPages = 0;
        document.getElementById('remove-pages').value = '';
        const myVersion = ++removeThumbVersion;
        const grid = document.getElementById('remove-thumbnail-grid');
        grid.innerHTML = '';
        document.getElementById('remove-thumb-toolbar').style.display = 'none';
        updateStatus('remove-status', `Loading ${f.name}...`, '');
        try {
            const password = document.getElementById('remove-password').value;
            const pdf = await pdfjsLib.getDocument({ data: await f.arrayBuffer(), password: password || undefined }).promise;
            removeTotalPages = pdf.numPages;
            updateStatus('remove-status', `${f.name}, ${removeTotalPages} page(s)`, 'text-green');
            await renderThumbnailGrid(grid, pdf, {
                isStale: () => removeThumbVersion !== myVersion,
                onWrapperCreated: (wrapper, idx) => makeThumbnailsSelectable(wrapper, idx, toggleRemoveThumbnail)
            });
            if (removeThumbVersion !== myVersion) return;
            document.getElementById('remove-thumb-toolbar').style.display = 'flex';
            validateRemoveRange();
        } catch (err) {
            const msg = err.name === 'PasswordException'
                ? 'This PDF is password protected, or the password entered was incorrect. Enter the correct document password and try again.'
                : `Could not read "${f.name}": ${err.message || 'invalid PDF'}`;
            updateStatus('remove-status', msg, 'text-red');
        }
    };
    bindSimpleDrop('drop-zone-remove', removeInput);
    document.getElementById('remove-pages').addEventListener('input', validateRemoveRange);

    function toggleRemoveThumbnail(idx) {
        const current = document.getElementById('remove-pages').value.trim();
        const indices = current ? parsePageRange(current) : [];
        const pos = indices.indexOf(idx);
        if (pos === -1) indices.push(idx); else indices.splice(pos, 1);
        document.getElementById('remove-pages').value = indicesToRangeString(indices);
        validateRemoveRange();
    }

    function validateRemoveRange() {
        const range   = document.getElementById('remove-pages').value.trim();
        const preview = document.getElementById('remove-preview');
        const grid    = document.getElementById('remove-thumbnail-grid');
        if (!range || !removeTotalPages) {
            preview.textContent = '';
            highlightThumbnails(grid, [], 'marked-remove');
            return;
        }
        const indices = parsePageRange(range);
        const invalid = indices.filter(i => i < 0 || i >= removeTotalPages);
        const valid   = indices.filter(i => i >= 0 && i < removeTotalPages);
        if (invalid.length) {
            preview.textContent = `⚠ Page(s) ${invalid.map(i => i + 1).join(', ')} out of range`;
            preview.className   = 'range-preview text-red';
        } else {
            const remaining = removeTotalPages - indices.length;
            if (remaining <= 0) {
                preview.textContent = `⚠ Cannot remove all ${removeTotalPages} pages`;
                preview.className   = 'range-preview text-red';
            } else {
                preview.textContent = `✓ Removing ${indices.length}, keeping ${remaining} page(s)`;
                preview.className   = 'range-preview text-green';
            }
        }
        highlightThumbnails(grid, valid, 'marked-remove');
    }

    document.getElementById('remove-btn').onclick = async () => {
        if (!removeInput.files[0]) { updateStatus('remove-status', 'Select a PDF first.', 'text-red'); return; }
        const range = document.getElementById('remove-pages').value.trim();
        if (!range) { updateStatus('remove-status', 'Enter page numbers to remove.', 'text-red'); return; }
        const check = validateFileSizes([removeInput.files[0]]);
        if (!check.ok) { updateStatus('remove-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('remove-status', check.warn, '');
        const indices  = parsePageRange(range);
        if (!indices.length) { updateStatus('remove-status', 'Enter valid page numbers.', 'text-red'); return; }
        if (removeTotalPages > 0 && indices.length >= removeTotalPages) {
            updateStatus('remove-status', 'Cannot remove all pages, at least one must remain.', 'text-red'); return;
        }
        const password = document.getElementById('remove-password').value;
        const buffer   = await toUint8(removeInput.files[0]);
        pendingDownloads['remove-status'] = stem(removeInput.files[0].name) + '_pages_removed.pdf';
        runWhenReady('remove-status', () => {
            pendingFooters['remove-status'] = document.getElementById('remove-footer')?.checked ?? false;
            updateStatus('remove-status', 'Removing pages...', '');
            worker.postMessage({ id: 'remove-status', action: 'REMOVE_PAGES', payload: { buffer, indices, password } }, [buffer.buffer]);
        });
    };

    /** ════ PDF TO TEXT ══════════════════════════════════════════════════════ */
    const totextInput = document.getElementById('totext-upload');
    totextInput.onchange = () => {
        if (totextInput.files[0]) {
            lastLoadedFile = totextInput.files[0]; lastLoadedTool = 'totext';
            updateStatus('totext-status', `Loaded: ${totextInput.files[0].name}`, 'text-green');
        }
    };
    bindSimpleDrop('drop-zone-totext', totextInput);

    document.getElementById('totext-btn').onclick = async () => {
        if (!totextInput.files[0]) { updateStatus('totext-status', 'Select a PDF first.', 'text-red'); return; }
        const check = validateFileSizes([totextInput.files[0]]);
        if (!check.ok) { updateStatus('totext-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('totext-status', check.warn, '');
        const password = document.getElementById('totext-password').value;
        const buffer   = await toUint8(totextInput.files[0]);
        pendingDownloads['totext-status'] = stem(totextInput.files[0].name) + '.txt';
        runWhenReady('totext-status', () => {
            pendingFooters['totext-status'] = false;
            updateStatus('totext-status', 'Extracting text...', '');
            worker.postMessage({ id: 'totext-status', action: 'EXTRACT_TEXT', payload: { buffer, password } }, [buffer.buffer]);
        });
    };

    /** ════ PDF TO IMAGES ════════════════════════════════════════════════════ */
    const topngInput = document.getElementById('topng-upload');
    topngInput.onchange = () => {
        if (topngInput.files[0]) {
            lastLoadedFile = topngInput.files[0]; lastLoadedTool = 'topng';
            updateStatus('topng-status', `Loaded: ${topngInput.files[0].name}`, 'text-green');
        }
    };
    bindSimpleDrop('drop-zone-topng', topngInput);

    document.getElementById('topng-btn').onclick = async () => {
        if (!topngInput.files[0]) { updateStatus('topng-status', 'Select a PDF first.', 'text-red'); return; }
        const check = validateFileSizes([topngInput.files[0]]);
        if (!check.ok) { updateStatus('topng-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('topng-status', check.warn, '');
        const format   = document.getElementById('topng-format').value;
        const mimeType = format === 'jpeg' ? 'image/jpeg' : 'image/png';
        const ext      = format === 'jpeg' ? 'jpg' : 'png';
        const password = document.getElementById('topng-password').value;
        updateStatus('topng-status', 'Rendering pages...', '');
        try {
            const pdf      = await pdfjsLib.getDocument({ data: await topngInput.files[0].arrayBuffer(), password: password || undefined }).promise;
            const numPages = pdf.numPages;
            const blobs    = [];
            for (let i = 1; i <= numPages; i++) {
                updateStatus('topng-status', `Rendering page ${i} of ${numPages}...`, '');
                const page     = await pdf.getPage(i);
                const viewport = page.getViewport({ scale: 2.0 });
                const canvas   = document.createElement('canvas');
                canvas.width   = viewport.width;
                canvas.height  = viewport.height;
                await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
                const blob = await new Promise(res => canvas.toBlob(res, mimeType, 0.92));
                blobs.push({ blob, name: `page_${String(i).padStart(3, '0')}.${ext}` });
            }
            const topngBase = stem(topngInput.files[0].name);
            if (numPages === 1) {
                const url = URL.createObjectURL(blobs[0].blob);
                const a   = document.createElement('a');
                a.href = url; a.download = `${topngBase}_page_1.${ext}`; a.click();
                URL.revokeObjectURL(url);
                incrementCounter('topng');
                if (!sessionStorage.getItem('nilpdf_nudged')) {
                    sessionStorage.setItem('nilpdf_nudged', '1');
                    setTimeout(showShareNudge, 1800);
                }
                updateStatus('topng-status', 'Done! Image downloaded.', 'text-green');
            } else {
                updateStatus('topng-status', 'Packing into ZIP...', '');
                const zip = new JSZip();
                for (const { blob, name } of blobs) zip.file(name, blob);
                const zipBlob = await zip.generateAsync({ type: 'blob' });
                const url = URL.createObjectURL(zipBlob);
                const a   = document.createElement('a');
                a.href = url; a.download = `${topngBase}_images.zip`; a.click();
                URL.revokeObjectURL(url);
                incrementCounter('topng');
                if (!sessionStorage.getItem('nilpdf_nudged')) {
                    sessionStorage.setItem('nilpdf_nudged', '1');
                    setTimeout(showShareNudge, 1800);
                }
                updateStatus('topng-status', `Done! ${numPages} images in ZIP.`, 'text-green');
            }
        } catch (err) {
            if (err.name === 'PasswordException') {
                document.getElementById('topng-password').style.display = 'block';
                updateStatus('topng-status', 'This PDF is password protected, or the password entered was incorrect. Enter the password above and try again.', 'text-red');
            } else {
                updateStatus('topng-status', formatProcessingError(err.message), 'text-red');
            }
        }
    };

    /** ════ IMAGES TO PDF ════════════════════════════════════════════════════ */
    const topdfInput = document.getElementById('topdf-upload');
    let topdfFilesArray = [], topdfIdCounter = 0, topdfSortable = null;

    function addTopdfFiles(fileList) {
        for (const f of fileList) topdfFilesArray.push({ id: topdfIdCounter++, file: f });
        renderTopdfList();
    }
    function removeTopdfFile(fileId) {
        topdfFilesArray = topdfFilesArray.filter(item => item.id !== fileId);
        renderTopdfList();
    }
    function renderTopdfList() {
        const list = document.getElementById('topdf-list');
        list.innerHTML = '';
        topdfFilesArray.forEach(item => {
            const li = document.createElement('li');
            li.className = 'file-list-item'; li.dataset.fileId = item.id;
            li.innerHTML =
                `<span class="drag-handle" title="Drag to reorder">⠿</span>` +
                `<span class="file-name">🖼 ${escHtml(item.file.name)}</span>` +
                `<button class="remove-file-btn" onclick="removeTopdfFile(${item.id})" title="Remove" aria-label="Remove file">×</button>`;
            list.appendChild(li);
        });
        const count = topdfFilesArray.length;
        document.getElementById('topdf-btn').disabled = count === 0;
        updateStatus('topdf-status', count === 0
            ? 'Add JPG or PNG images to convert.'
            : `${count} image(s) ready, drag to reorder.`,
            count > 0 ? 'text-green' : '');
        if (topdfSortable) { topdfSortable.destroy(); topdfSortable = null; }
        if (count > 1) {
            topdfSortable = new Sortable(list, {
                animation: 150, handle: '.drag-handle', dataIdAttr: 'data-file-id',
                onEnd: () => {
                    const order = Array.from(list.children).map(el => parseInt(el.dataset.fileId));
                    const map   = new Map(topdfFilesArray.map(i => [i.id, i.file]));
                    topdfFilesArray = order.map(id => ({ id, file: map.get(id) })).filter(x => x.file);
                }
            });
        }
    }
    topdfInput.onchange = () => { addTopdfFiles(topdfInput.files); topdfInput.value = ''; };
    bindDrop('drop-zone-topdf', files => addTopdfFiles(files));

    document.getElementById('topdf-btn').onclick = async () => {
        if (topdfFilesArray.length === 0) { updateStatus('topdf-status', 'Add at least one image.', 'text-red'); return; }
        const check = validateFileSizes(topdfFilesArray.map(i => i.file));
        if (!check.ok) { updateStatus('topdf-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('topdf-status', check.warn, '');
        updateStatus('topdf-status', 'Creating PDF...', '');
        try {
            const { PDFDocument } = PDFLib;
            const pdfDoc = await PDFDocument.create();
            let added = 0;
            for (let i = 0; i < topdfFilesArray.length; i++) {
                const file  = topdfFilesArray[i].file;
                updateStatus('topdf-status', `Adding image ${i + 1} of ${topdfFilesArray.length}...`, '');
                const bytes = new Uint8Array(await file.arrayBuffer());
                const mime  = file.type;
                let img;
                try {
                    if (mime === 'image/jpeg' || mime === 'image/jpg') img = await pdfDoc.embedJpg(bytes);
                    else if (mime === 'image/png') img = await pdfDoc.embedPng(bytes);
                    else { updateStatus('topdf-status', `Skipped "${file.name}": only JPG and PNG are supported.`, 'text-red'); continue; }
                } catch (e) { updateStatus('topdf-status', `Skipped "${file.name}": ${e.message}`, 'text-red'); continue; }
                const page = pdfDoc.addPage([img.width, img.height]);
                page.drawImage(img, { x: 0, y: 0, width: img.width, height: img.height });
                added++;
            }
            if (added === 0) { updateStatus('topdf-status', 'No valid images were added.', 'text-red'); return; }
            const pdfBytes = await pdfDoc.save();
            const blob = new Blob([pdfBytes], { type: 'application/pdf' });
            const url  = URL.createObjectURL(blob);
            const a    = document.createElement('a');
            const topdfName = topdfFilesArray.length === 1
                ? stem(topdfFilesArray[0].file.name) + '_converted.pdf'
                : 'images_combined.pdf';
            a.href = url; a.download = topdfName; a.click();
            URL.revokeObjectURL(url);
            incrementCounter('topdf');
            if (!sessionStorage.getItem('nilpdf_nudged')) {
                sessionStorage.setItem('nilpdf_nudged', '1');
                setTimeout(showShareNudge, 1800);
            }
            updateStatus('topdf-status', `Done! PDF with ${added} page(s) downloaded.`, 'text-green');
        } catch (err) {
            updateStatus('topdf-status', formatProcessingError(err.message), 'text-red');
        }
    };

    /** ════ WATERMARK ════════════════════════════════════════════════════════ */
    const watermarkInput = document.getElementById('watermark-upload');
    watermarkInput.onchange = () => {
        if (watermarkInput.files[0]) {
            lastLoadedFile = watermarkInput.files[0]; lastLoadedTool = 'watermark';
            updateStatus('watermark-status', `Loaded: ${watermarkInput.files[0].name}`, 'text-green');
        }
    };
    bindSimpleDrop('drop-zone-watermark', watermarkInput);
    document.getElementById('watermark-opacity').addEventListener('input', function () {
        document.getElementById('opacity-value').textContent = this.value + '%';
    });

    document.getElementById('watermark-btn').onclick = async () => {
        if (!watermarkInput.files[0]) { updateStatus('watermark-status', 'Select a PDF first.', 'text-red'); return; }
        const text = document.getElementById('watermark-text').value.trim();
        if (!text) { updateStatus('watermark-status', 'Enter watermark text.', 'text-red'); return; }
        const check = validateFileSizes([watermarkInput.files[0]]);
        if (!check.ok) { updateStatus('watermark-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('watermark-status', check.warn, '');
        const opacity  = parseInt(document.getElementById('watermark-opacity').value) / 100;
        const password = document.getElementById('watermark-password').value;
        const buffer   = await toUint8(watermarkInput.files[0]);
        pendingDownloads['watermark-status'] = stem(watermarkInput.files[0].name) + '_watermarked.pdf';
        runWhenReady('watermark-status', () => {
            pendingFooters['watermark-status'] = document.getElementById('watermark-footer')?.checked ?? false;
            updateStatus('watermark-status', 'Applying watermark...', '');
            worker.postMessage({ id: 'watermark-status', action: 'WATERMARK', payload: { buffer, text, opacity, password } }, [buffer.buffer]);
        });
    };

    /** ════ PAGE NUMBERS ═════════════════════════════════════════════════════ */
    const pagenumInput = document.getElementById('pagenums-upload');
    pagenumInput.onchange = () => {
        if (pagenumInput.files[0]) {
            lastLoadedFile = pagenumInput.files[0]; lastLoadedTool = 'pagenums';
            updateStatus('pagenums-status', `Loaded: ${pagenumInput.files[0].name}`, 'text-green');
        }
    };
    bindSimpleDrop('drop-zone-pagenums', pagenumInput);

    document.getElementById('pagenums-btn').onclick = async () => {
        if (!pagenumInput.files[0]) { updateStatus('pagenums-status', 'Select a PDF first.', 'text-red'); return; }
        const check = validateFileSizes([pagenumInput.files[0]]);
        if (!check.ok) { updateStatus('pagenums-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('pagenums-status', check.warn, '');
        const position = document.getElementById('pagenums-position').value;
        const startNum = Math.max(1, parseInt(document.getElementById('pagenums-start').value) || 1);
        const password = document.getElementById('pagenums-password').value;
        const buffer   = await toUint8(pagenumInput.files[0]);
        pendingDownloads['pagenums-status'] = stem(pagenumInput.files[0].name) + '_numbered.pdf';
        runWhenReady('pagenums-status', () => {
            pendingFooters['pagenums-status'] = document.getElementById('pagenums-footer')?.checked ?? false;
            updateStatus('pagenums-status', 'Adding page numbers...', '');
            worker.postMessage({ id: 'pagenums-status', action: 'ADD_PAGE_NUMBERS', payload: { buffer, position, startNum, password } }, [buffer.buffer]);
        });
    };

    /** ════ INSPECT ══════════════════════════════════════════════════════════ */
    const inspectInput = document.getElementById('inspect-upload');
    inspectInput.onchange = () => {
        if (inspectInput.files[0]) {
            lastLoadedFile = inspectInput.files[0]; lastLoadedTool = 'inspect';
            updateStatus('inspect-status', `Loaded: ${inspectInput.files[0].name}`, 'text-green');
        }
    };
    bindSimpleDrop('drop-zone-inspect', inspectInput);

    function parsePdfDate(d) {
        if (!d) return null;
        const m = d.match(/D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?/);
        if (!m) return d;
        return `${m[1]}-${m[2]}-${m[3]}${m[4] ? ' ' + m[4] + ':' + (m[5] || '00') : ''}`;
    }

    function buildInspectResults(file, pdf, info) {
        const container = document.getElementById('inspect-results');
        container.innerHTML = '';
        const val   = (v, fallback = 'Not set') => (v != null && v !== '') ? String(v) : fallback;
        const fmtSz = n => n < 1048576 ? (n / 1024).toFixed(1) + ' KB' : (n / 1048576).toFixed(2) + ' MB';

        function section(title, rows) {
            const wrap = document.createElement('div');
            const hdr  = document.createElement('div');
            hdr.className   = 'inspect-section-title';
            hdr.textContent = title;
            wrap.appendChild(hdr);
            rows.forEach(([key, value, cls]) => {
                const row  = document.createElement('div');
                row.className = 'inspect-row';
                const isEmpty = (value === 'Not set');
                const valCls  = cls ? cls : (isEmpty ? 'empty' : '');
                const keySpan = document.createElement('span');
                keySpan.className = 'inspect-key';
                keySpan.textContent = key;
                const valSpan = document.createElement('span');
                valSpan.className = `inspect-val ${valCls}`;
                valSpan.textContent = value;
                row.appendChild(keySpan);
                row.appendChild(valSpan);
                wrap.appendChild(row);
            });
            container.appendChild(wrap);
        }

        section('File', [
            ['Name',        file.name],
            ['Size',        fmtSz(file.size)],
            ['Pages',       String(pdf.numPages), 'highlight'],
            ['PDF Version', val(info.PDFFormatVersion)],
            ['Linearized',  info.IsLinearized ? 'Yes' : 'No'],
        ]);
        section('Metadata', [
            ['Title',    val(info.Title)],
            ['Author',   val(info.Author)],
            ['Subject',  val(info.Subject)],
            ['Keywords', val(info.Keywords)],
            ['Creator',  val(info.Creator)],
            ['Producer', val(info.Producer)],
            ['Created',  val(parsePdfDate(info.CreationDate))],
            ['Modified', val(parsePdfDate(info.ModDate))],
        ]);
        const encrypted = !!info.IsEncrypted;
        const hasForms  = info.IsAcroFormPresent ? 'Yes (AcroForm)'
                        : info.IsXFAPresent      ? 'Yes (XFA)'
                        : 'No';
        section('Security & Forms', [
            ['Encrypted', encrypted ? 'Yes' : 'No', encrypted ? 'warn' : ''],
            ['Has Forms', hasForms],
        ]);
    }

    document.getElementById('inspect-btn').onclick = async () => {
        if (!inspectInput.files[0]) { updateStatus('inspect-status', 'Select a PDF first.', 'text-red'); return; }
        const check = validateFileSizes([inspectInput.files[0]]);
        if (!check.ok) { updateStatus('inspect-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('inspect-status', check.warn, '');
        document.getElementById('inspect-results').innerHTML = '';
        updateStatus('inspect-status', 'Reading metadata...', '');
        const password = document.getElementById('inspect-password').value;
        try {
            const buf  = await inspectInput.files[0].arrayBuffer();
            const pdf  = await pdfjsLib.getDocument({ data: buf, password: password || undefined }).promise;
            const meta = await pdf.getMetadata();
            buildInspectResults(inspectInput.files[0], pdf, meta.info || {});
            updateStatus('inspect-status', `Done: ${pdf.numPages} page(s) inspected.`, 'text-green');
        } catch (err) {
            const msg = err.name === 'PasswordException'
                ? 'This PDF is password protected, or the password entered was incorrect. Enter the correct document password and try again.'
                : formatProcessingError(err.message);
            updateStatus('inspect-status', msg, 'text-red');
        }
    };

    /** ════ REPAIR ═══════════════════════════════════════════════════════════ */
    const repairInput = document.getElementById('repair-upload');
    repairInput.onchange = () => {
        if (repairInput.files[0]) {
            lastLoadedFile = repairInput.files[0]; lastLoadedTool = 'repair';
            updateStatus('repair-status', `Loaded: ${repairInput.files[0].name}`, 'text-green');
        }
    };
    bindSimpleDrop('drop-zone-repair', repairInput);

    document.getElementById('repair-btn').onclick = async () => {
        if (!repairInput.files[0]) { updateStatus('repair-status', 'Select a PDF first.', 'text-red'); return; }
        const check = validateFileSizes([repairInput.files[0]]);
        if (!check.ok) { updateStatus('repair-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('repair-status', check.warn, '');
        const password = document.getElementById('repair-password').value;
        const buffer   = await toUint8(repairInput.files[0]);
        pendingDownloads['repair-status'] = stem(repairInput.files[0].name) + '_repaired.pdf';
        runWhenReady('repair-status', () => {
            updateStatus('repair-status', 'Attempting recovery…', '');
            worker.postMessage({ id: 'repair-status', action: 'REPAIR', payload: { buffer, password } }, [buffer.buffer]);
        });
    };

    /** ════ REDACT / EDIT (shared page-editor: click to add text, optionally draw redaction boxes) ════ */
    function initPageEditor({ prefix, allowBoxes, suffix, emptyEditsMsg }) {
        const input = document.getElementById(`${prefix}-upload`);
        const SCALE = 1.5;
        const state = { pdfDoc: null, currentPage: 0, totalPages: 0, pageEdits: {}, idCounter: 0, mode: 'redact', file: null };
        const el = id => document.getElementById(`${prefix}-${id}`);

        if (allowBoxes) {
            el('mode-redact').onclick = () => setMode('redact');
            el('mode-text').onclick = () => setMode('text');
        }
        function setMode(mode) {
            state.mode = mode;
            el('mode-redact').classList.toggle('active', mode === 'redact');
            el('mode-text').classList.toggle('active', mode === 'text');
        }

        input.onchange = async () => {
            const f = input.files[0];
            if (!f) return;
            lastLoadedFile = f; lastLoadedTool = prefix;
            state.file = f;
            state.pageEdits = {};
            state.currentPage = 0;
            updateStatus(`${prefix}-status`, `Loading ${f.name}...`, '');
            try {
                const password = el('password').value;
                state.pdfDoc = await pdfjsLib.getDocument({ data: await f.arrayBuffer(), password: password || undefined }).promise;
                state.totalPages = state.pdfDoc.numPages;
                el('workspace').style.display = '';
                await renderPage();
                updateStatus(`${prefix}-status`, `${f.name}, ${state.totalPages} page(s)`, 'text-green');
            } catch (err) {
                el('workspace').style.display = 'none';
                const msg = err.name === 'PasswordException'
                    ? 'This PDF is password protected, or the password entered was incorrect. Enter the correct document password and try again.'
                    : `Could not read "${f.name}": ${err.message || 'invalid PDF'}`;
                updateStatus(`${prefix}-status`, msg, 'text-red');
            }
        };
        bindSimpleDrop(`drop-zone-${prefix}`, input);

        async function renderPage() {
            const page = await state.pdfDoc.getPage(state.currentPage + 1);
            const viewport = page.getViewport({ scale: SCALE });
            const canvas = el('canvas');
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
            el('page-indicator').textContent = `Page ${state.currentPage + 1} / ${state.totalPages}`;
            el('prev-page').disabled = state.currentPage === 0;
            el('next-page').disabled = state.currentPage === state.totalPages - 1;
            renderOverlay();
        }

        function renderOverlay() {
            const overlay = el('overlay');
            const canvas  = el('canvas');
            overlay.style.width  = canvas.width + 'px';
            overlay.style.height = canvas.height + 'px';
            overlay.innerHTML = '';
            const items = state.pageEdits[state.currentPage] || [];
            items.forEach(item => {
                const box = document.createElement('div');
                if (item.type === 'redact') {
                    box.className = 'redact-box';
                    box.style.left   = (item.x * SCALE) + 'px';
                    box.style.top    = (canvas.height - (item.y + item.height) * SCALE) + 'px';
                    box.style.width  = (item.width * SCALE) + 'px';
                    box.style.height = (item.height * SCALE) + 'px';
                } else {
                    box.className = 'redact-text-box';
                    box.style.left = (item.x * SCALE) + 'px';
                    box.style.top  = (canvas.height - (item.y + item.size) * SCALE) + 'px';
                    box.style.fontSize = (item.size * SCALE) + 'px';
                    box.textContent = item.text;
                }
                const rm = document.createElement('button');
                rm.type = 'button';
                rm.className = 'redact-item-remove';
                rm.setAttribute('aria-label', 'Remove');
                rm.textContent = '×';
                rm.onclick = e => { e.stopPropagation(); removeItem(item.id); };
                box.appendChild(rm);
                overlay.appendChild(box);
            });
        }

        function removeItem(id) {
            const items = state.pageEdits[state.currentPage] || [];
            state.pageEdits[state.currentPage] = items.filter(i => i.id !== id);
            renderOverlay();
        }

        function addBox(pxLeft, pxTop, pxWidth, pxHeight) {
            const canvas = el('canvas');
            const x = pxLeft / SCALE;
            const width  = pxWidth  / SCALE;
            const height = pxHeight / SCALE;
            const y = (canvas.height - pxTop - pxHeight) / SCALE;
            const items = state.pageEdits[state.currentPage] || (state.pageEdits[state.currentPage] = []);
            items.push({ id: ++state.idCounter, type: 'redact', x, y, width, height });
            renderOverlay();
        }

        function addText(px, py, text) {
            const canvas = el('canvas');
            const size = 14;
            const x = px / SCALE;
            const y = (canvas.height - py) / SCALE - size;
            const items = state.pageEdits[state.currentPage] || (state.pageEdits[state.currentPage] = []);
            items.push({ id: ++state.idCounter, type: 'text', x, y, text, size });
            renderOverlay();
        }

        el('prev-page').onclick = () => { if (state.currentPage > 0) { state.currentPage--; renderPage(); } };
        el('next-page').onclick = () => { if (state.currentPage < state.totalPages - 1) { state.currentPage++; renderPage(); } };

        (function bindCanvasEvents() {
            // Pointer Events unify mouse, touch, and pen so drawing a redaction box
            // works the same way on a phone/tablet as it does with a mouse.
            const overlay = el('overlay');
            let dragStart = null, dragEl = null, dragPointerId = null;

            function pointerPos(e) {
                const rect = overlay.getBoundingClientRect();
                return { px: e.clientX - rect.left, py: e.clientY - rect.top };
            }
            function onPointerMove(e) {
                if (dragPointerId === null || e.pointerId !== dragPointerId) return;
                const { px, py } = pointerPos(e);
                dragEl.style.left   = Math.min(px, dragStart.px) + 'px';
                dragEl.style.top    = Math.min(py, dragStart.py) + 'px';
                dragEl.style.width  = Math.abs(px - dragStart.px) + 'px';
                dragEl.style.height = Math.abs(py - dragStart.py) + 'px';
            }
            function onPointerUp(e) {
                if (dragPointerId === null || e.pointerId !== dragPointerId) return;
                overlay.removeEventListener('pointermove', onPointerMove);
                overlay.removeEventListener('pointerup', onPointerUp);
                overlay.removeEventListener('pointercancel', onPointerUp);
                const left = parseFloat(dragEl.style.left) || 0;
                const top  = parseFloat(dragEl.style.top) || 0;
                const w    = parseFloat(dragEl.style.width) || 0;
                const h    = parseFloat(dragEl.style.height) || 0;
                dragEl.remove();
                dragStart = null; dragEl = null; dragPointerId = null;
                if (w > 3 && h > 3) addBox(left, top, w, h);
            }

            overlay.addEventListener('pointerdown', e => {
                if (e.target !== overlay || dragPointerId !== null) return;
                const { px, py } = pointerPos(e);
                if (allowBoxes && state.mode === 'redact') {
                    dragStart = { px, py };
                    dragPointerId = e.pointerId;
                    dragEl = document.createElement('div');
                    dragEl.className = 'redact-box redact-box-drawing';
                    dragEl.style.left = px + 'px'; dragEl.style.top = py + 'px';
                    dragEl.style.width = '0px'; dragEl.style.height = '0px';
                    overlay.appendChild(dragEl);
                    try {
                        overlay.setPointerCapture(e.pointerId);
                    } catch (err) {
                        // No active pointer to capture (can happen with synthetic/test input) —
                        // abandon this drag cleanly instead of leaving dragPointerId stuck forever.
                        dragEl.remove();
                        dragStart = null; dragEl = null; dragPointerId = null;
                        return;
                    }
                    overlay.addEventListener('pointermove', onPointerMove);
                    overlay.addEventListener('pointerup', onPointerUp);
                    overlay.addEventListener('pointercancel', onPointerUp);
                } else {
                    const text = prompt('Text to add on this page:');
                    if (text && text.trim()) addText(px, py, text.trim());
                }
            });
        })();

        // High-resolution scale used only when flattening a redacted page to an
        // image (~180 DPI), deliberately higher than the SCALE used for the
        // interactive on-screen editor, since this is what actually ships.
        const FLATTEN_SCALE = 2.5;

        async function renderFlattenedPage(pageIdx) {
            const page = await state.pdfDoc.getPage(pageIdx + 1);
            const viewport = page.getViewport({ scale: FLATTEN_SCALE });
            const canvas = document.createElement('canvas');
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            const ctx = canvas.getContext('2d');
            await page.render({ canvasContext: ctx, viewport }).promise;

            (state.pageEdits[pageIdx] || []).forEach(item => {
                if (item.type === 'redact') {
                    ctx.fillStyle = '#000';
                    ctx.fillRect(
                        item.x * FLATTEN_SCALE,
                        canvas.height - (item.y + item.height) * FLATTEN_SCALE,
                        item.width * FLATTEN_SCALE,
                        item.height * FLATTEN_SCALE
                    );
                } else if (item.type === 'text') {
                    const size = (item.size || 14) * FLATTEN_SCALE;
                    ctx.fillStyle = '#000';
                    ctx.font = `${size}px Helvetica, Arial, sans-serif`;
                    ctx.textBaseline = 'alphabetic';
                    ctx.fillText(item.text, item.x * FLATTEN_SCALE, canvas.height - item.y * FLATTEN_SCALE);
                }
            });

            return canvas.toDataURL('image/png');
        }

        el('btn').onclick = async () => {
            if (!state.file) { updateStatus(`${prefix}-status`, 'Select a PDF first.', 'text-red'); return; }

            if (allowBoxes) {
                // Secure redaction: every page with a black box is fully re-rendered
                // at high resolution with the box (and any notes on that same page)
                // baked into the pixels, then rebuilt server-side as an image-only
                // page. Nothing under a black box survives into the output.
                const redactedPages = Object.keys(state.pageEdits)
                    .map(k => parseInt(k))
                    .filter(idx => (state.pageEdits[idx] || []).length > 0);
                if (!redactedPages.length) { updateStatus(`${prefix}-status`, emptyEditsMsg, 'text-red'); return; }
                const check = validateFileSizes([state.file]);
                if (!check.ok) { updateStatus(`${prefix}-status`, check.msg, 'text-red'); return; }
                if (check.warn) updateStatus(`${prefix}-status`, check.warn, '');

                const pageImages = {};
                for (let i = 0; i < redactedPages.length; i++) {
                    const pageIdx = redactedPages[i];
                    updateStatus(`${prefix}-status`, `Flattening page ${pageIdx + 1} (${i + 1} of ${redactedPages.length})...`, '');
                    pageImages[pageIdx] = await renderFlattenedPage(pageIdx);
                }

                const password = el('password').value;
                const buffer = await toUint8(state.file);
                pendingDownloads[`${prefix}-status`] = stem(state.file.name) + suffix;
                runWhenReady(`${prefix}-status`, () => {
                    pendingFooters[`${prefix}-status`] = el('footer')?.checked ?? false;
                    updateStatus(`${prefix}-status`, 'Rebuilding redacted pages...', '');
                    worker.postMessage({ id: `${prefix}-status`, action: 'REDACT', payload: { buffer, pageImages, password } }, [buffer.buffer]);
                });
                return;
            }

            // Text-only tool (Edit): unchanged, a lightweight overlay merge is fine
            // since nothing is being claimed as removed.
            const allEdits = [];
            Object.keys(state.pageEdits).forEach(pageIdx => {
                (state.pageEdits[pageIdx] || []).forEach(item => {
                    allEdits.push({ page: parseInt(pageIdx), type: 'text', x: item.x, y: item.y, text: item.text, size: item.size });
                });
            });
            if (!allEdits.length) { updateStatus(`${prefix}-status`, emptyEditsMsg, 'text-red'); return; }
            const check = validateFileSizes([state.file]);
            if (!check.ok) { updateStatus(`${prefix}-status`, check.msg, 'text-red'); return; }
            if (check.warn) updateStatus(`${prefix}-status`, check.warn, '');
            const password = el('password').value;
            const buffer   = await toUint8(state.file);
            pendingDownloads[`${prefix}-status`] = stem(state.file.name) + suffix;
            runWhenReady(`${prefix}-status`, () => {
                pendingFooters[`${prefix}-status`] = el('footer')?.checked ?? false;
                updateStatus(`${prefix}-status`, 'Applying edits...', '');
                worker.postMessage({ id: `${prefix}-status`, action: 'EDIT', payload: { buffer, edits: allEdits, password } }, [buffer.buffer]);
            });
        };
    }

    initPageEditor({
        prefix: 'redact', allowBoxes: true, suffix: '_redacted.pdf',
        emptyEditsMsg: 'Add at least one redaction box or text note first.'
    });
    initPageEditor({
        prefix: 'edit', allowBoxes: false, suffix: '_edited.pdf',
        emptyEditsMsg: 'Click the page to add at least one text note first.'
    });

    /** ════ SIGN ══════════════════════════════════════════════════════════════ */
    (function initSignTool() {
        const input = document.getElementById('sign-upload');
        const SCALE = 1.5;
        const SAVED_SIG_KEY = 'nilpdf_saved_signature';
        const FONT_FAMILY_MAP = {
            'sign-font-dancing': 'Dancing Script',
            'sign-font-caveat': 'Caveat',
            'sign-font-pacifico': 'Pacifico',
            'sign-font-sacramento': 'Sacramento',
        };
        const state = {
            pdfDoc: null, currentPage: 0, totalPages: 0, file: null,
            pageItems: {},  // { pageIndex: [{ id, dataUrl, x, y, width, height }] }, PDF points, bottom-left origin
            idCounter: 0,
            padMode: 'draw',
            typeFont: 'sign-font-dancing',
            uploadedDataUrl: null,
        };
        const el = id => document.getElementById(`sign-${id}`);

        /* ---- Upload + page rendering (same shape as Redact/Edit) ---- */
        input.onchange = async () => {
            const f = input.files[0];
            if (!f) return;
            lastLoadedFile = f; lastLoadedTool = 'sign';
            state.file = f;
            state.pageItems = {};
            state.currentPage = 0;
            el('workspace').style.display = 'none';
            updateStatus('sign-status', `Loading ${f.name}...`, '');
            try {
                const password = el('password').value;
                state.pdfDoc = await pdfjsLib.getDocument({ data: await f.arrayBuffer(), password: password || undefined }).promise;
                state.totalPages = state.pdfDoc.numPages;
                el('workspace').style.display = '';
                await renderSignPage();
                updateStatus('sign-status', `${f.name}, ${state.totalPages} page(s)`, 'text-green');
            } catch (err) {
                el('workspace').style.display = 'none';
                const msg = err.name === 'PasswordException'
                    ? 'This PDF is password protected, or the password entered was incorrect. Enter the correct document password and try again.'
                    : `Could not read "${f.name}": ${err.message || 'invalid PDF'}`;
                updateStatus('sign-status', msg, 'text-red');
            }
        };
        bindSimpleDrop('drop-zone-sign', input);

        async function renderSignPage() {
            const page = await state.pdfDoc.getPage(state.currentPage + 1);
            const viewport = page.getViewport({ scale: SCALE });
            const canvas = el('canvas');
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
            el('page-indicator').textContent = `Page ${state.currentPage + 1} / ${state.totalPages}`;
            el('prev-page').disabled = state.currentPage === 0;
            el('next-page').disabled = state.currentPage === state.totalPages - 1;
            renderSignOverlay();
        }
        el('prev-page').onclick = () => { if (state.currentPage > 0) { state.currentPage--; renderSignPage(); } };
        el('next-page').onclick = () => { if (state.currentPage < state.totalPages - 1) { state.currentPage++; renderSignPage(); } };

        /* ---- Placed signature items: draggable + resizable ---- */
        function renderSignOverlay() {
            const overlay = el('overlay');
            const canvas  = el('canvas');
            overlay.style.width  = canvas.width + 'px';
            overlay.style.height = canvas.height + 'px';
            overlay.innerHTML = '';
            const items = state.pageItems[state.currentPage] || [];
            items.forEach(item => {
                const wrap = document.createElement('div');
                wrap.className = 'sign-item';
                wrap.dataset.id = item.id;
                wrap.style.left   = (item.x * SCALE) + 'px';
                wrap.style.top    = (canvas.height - (item.y + item.height) * SCALE) + 'px';
                wrap.style.width  = (item.width * SCALE) + 'px';
                wrap.style.height = (item.height * SCALE) + 'px';

                const img = document.createElement('img');
                img.src = item.dataUrl;
                img.alt = 'Signature';
                wrap.appendChild(img);

                const toolbar = document.createElement('div');
                toolbar.className = 'sign-item-toolbar';
                const dupBtn = document.createElement('button');
                dupBtn.type = 'button'; dupBtn.className = 'sign-item-btn sign-item-duplicate';
                dupBtn.textContent = '⧉'; dupBtn.setAttribute('aria-label', 'Duplicate signature');
                dupBtn.onclick = e => { e.stopPropagation(); duplicateItem(item.id); };
                const rmBtn = document.createElement('button');
                rmBtn.type = 'button'; rmBtn.className = 'sign-item-btn sign-item-remove';
                rmBtn.textContent = '×'; rmBtn.setAttribute('aria-label', 'Remove signature');
                rmBtn.onclick = e => { e.stopPropagation(); removeItem(item.id); };
                toolbar.appendChild(dupBtn);
                toolbar.appendChild(rmBtn);
                wrap.appendChild(toolbar);

                const handle = document.createElement('div');
                handle.className = 'sign-item-handle';
                handle.setAttribute('aria-hidden', 'true');
                wrap.appendChild(handle);

                bindItemInteraction(wrap, item, handle);
                overlay.appendChild(wrap);
            });
        }

        function bindItemInteraction(wrap, item, handle) {
            let mode = null; // 'move' | 'resize'
            let startClientX = 0, startClientY = 0, startLeft = 0, startTop = 0, startWidth = 0, startHeight = 0;
            let activePointerId = null;

            function applyPdfCoords(leftPx, topPx, widthPx, heightPx) {
                const canvas = el('canvas');
                item.width  = widthPx / SCALE;
                item.height = heightPx / SCALE;
                item.x = leftPx / SCALE;
                item.y = (canvas.height - topPx - heightPx) / SCALE;
            }
            function onPointerMove(e) {
                if (activePointerId === null || e.pointerId !== activePointerId) return;
                const dx = e.clientX - startClientX;
                const dy = e.clientY - startClientY;
                if (mode === 'move') {
                    const newLeft = startLeft + dx, newTop = startTop + dy;
                    wrap.style.left = newLeft + 'px';
                    wrap.style.top  = newTop + 'px';
                    applyPdfCoords(newLeft, newTop, startWidth, startHeight);
                } else if (mode === 'resize') {
                    const newWidth  = Math.max(20, startWidth + dx);
                    const newHeight = Math.max(12, startHeight + dy);
                    wrap.style.width  = newWidth + 'px';
                    wrap.style.height = newHeight + 'px';
                    applyPdfCoords(startLeft, startTop, newWidth, newHeight);
                }
            }
            function onPointerUp(e) {
                if (activePointerId === null || e.pointerId !== activePointerId) return;
                wrap.removeEventListener('pointermove', onPointerMove);
                wrap.removeEventListener('pointerup', onPointerUp);
                wrap.removeEventListener('pointercancel', onPointerUp);
                mode = null; activePointerId = null;
            }
            function beginDrag(e, dragMode) {
                mode = dragMode;
                activePointerId = e.pointerId;
                startClientX = e.clientX; startClientY = e.clientY;
                startLeft   = parseFloat(wrap.style.left)   || 0;
                startTop    = parseFloat(wrap.style.top)    || 0;
                startWidth  = parseFloat(wrap.style.width)  || 0;
                startHeight = parseFloat(wrap.style.height) || 0;
                try { wrap.setPointerCapture(e.pointerId); } catch (_) { /* no active pointer (e.g. synthetic input) */ }
                wrap.addEventListener('pointermove', onPointerMove);
                wrap.addEventListener('pointerup', onPointerUp);
                wrap.addEventListener('pointercancel', onPointerUp);
                e.preventDefault();
            }
            wrap.addEventListener('pointerdown', e => {
                if (e.target === handle || e.target.closest('.sign-item-btn')) return;
                beginDrag(e, 'move');
            });
            handle.addEventListener('pointerdown', e => {
                e.stopPropagation();
                beginDrag(e, 'resize');
            });

            // Keyboard alternative to dragging: arrow keys move, Alt+arrow keys resize,
            // Delete removes. Without this, placing a signature would work but nobody
            // using a keyboard or screen reader could ever move or resize it.
            wrap.tabIndex = 0;
            wrap.setAttribute('role', 'group');
            wrap.setAttribute('aria-label', 'Placed signature. Arrow keys move it, Alt plus arrow keys resize it, Delete removes it.');
            wrap.addEventListener('keydown', e => {
                if (e.key === 'Delete' || e.key === 'Backspace') {
                    e.preventDefault();
                    removeItem(item.id);
                    return;
                }
                const arrowKeys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'];
                if (!arrowKeys.includes(e.key)) return;
                e.preventDefault();
                const step = e.shiftKey ? 10 : 2;
                let left   = parseFloat(wrap.style.left)   || 0;
                let top    = parseFloat(wrap.style.top)    || 0;
                let width  = parseFloat(wrap.style.width)  || 0;
                let height = parseFloat(wrap.style.height) || 0;
                if (e.altKey) {
                    if (e.key === 'ArrowRight') width  = Math.max(20, width + step);
                    if (e.key === 'ArrowLeft')  width  = Math.max(20, width - step);
                    if (e.key === 'ArrowDown')  height = Math.max(12, height + step);
                    if (e.key === 'ArrowUp')    height = Math.max(12, height - step);
                } else {
                    if (e.key === 'ArrowRight') left += step;
                    if (e.key === 'ArrowLeft')  left -= step;
                    if (e.key === 'ArrowDown')  top  += step;
                    if (e.key === 'ArrowUp')    top  -= step;
                }
                wrap.style.left = left + 'px'; wrap.style.top = top + 'px';
                wrap.style.width = width + 'px'; wrap.style.height = height + 'px';
                applyPdfCoords(left, top, width, height);
            });
        }

        function duplicateItem(id) {
            const items = state.pageItems[state.currentPage] || [];
            const item = items.find(i => i.id === id);
            if (!item) return;
            const offset = 10 / SCALE;
            items.push({ ...item, id: ++state.idCounter, x: item.x + offset, y: Math.max(0, item.y - offset) });
            renderSignOverlay();
        }
        function removeItem(id) {
            const items = state.pageItems[state.currentPage] || [];
            state.pageItems[state.currentPage] = items.filter(i => i.id !== id);
            renderSignOverlay();
        }

        /* ---- Signature pad: Draw / Type / Upload ---- */
        function setPadMode(mode) {
            state.padMode = mode;
            ['draw', 'type', 'upload'].forEach(m => {
                el(`mode-${m}`).classList.toggle('active', m === mode);
                el(`mode-${m}`).setAttribute('aria-selected', m === mode ? 'true' : 'false');
                el(`pad-${m}`).hidden = m !== mode;
            });
        }
        el('mode-draw').onclick   = () => setPadMode('draw');
        el('mode-type').onclick   = () => setPadMode('type');
        el('mode-upload').onclick = () => setPadMode('upload');

        (function bindDrawCanvas() {
            const canvas = el('draw-canvas');
            const ctx = canvas.getContext('2d');
            let drawing = false, lastX = 0, lastY = 0, activePointerId = null;
            ctx.strokeStyle = '#15181d';
            ctx.lineWidth = 2.5;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';

            function pos(e) {
                const rect = canvas.getBoundingClientRect();
                return {
                    x: (e.clientX - rect.left) * (canvas.width / rect.width),
                    y: (e.clientY - rect.top) * (canvas.height / rect.height),
                };
            }
            canvas.addEventListener('pointerdown', e => {
                drawing = true;
                activePointerId = e.pointerId;
                try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
                const p = pos(e);
                lastX = p.x; lastY = p.y;
                e.preventDefault();
            });
            canvas.addEventListener('pointermove', e => {
                if (!drawing || e.pointerId !== activePointerId) return;
                const p = pos(e);
                ctx.beginPath();
                ctx.moveTo(lastX, lastY);
                ctx.lineTo(p.x, p.y);
                ctx.stroke();
                lastX = p.x; lastY = p.y;
            });
            ['pointerup', 'pointercancel'].forEach(evt => canvas.addEventListener(evt, e => {
                if (e.pointerId !== activePointerId) return;
                drawing = false; activePointerId = null;
            }));
            el('draw-clear').onclick = () => ctx.clearRect(0, 0, canvas.width, canvas.height);
        })();

        el('type-input').addEventListener('input', () => {
            el('type-preview').textContent = el('type-input').value.trim() || 'Your Name';
        });
        document.querySelectorAll('#sign-pad-type .sign-font-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#sign-pad-type .sign-font-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                state.typeFont = btn.dataset.font;
                const preview = el('type-preview');
                Object.keys(FONT_FAMILY_MAP).forEach(f => preview.classList.remove(f));
                preview.classList.add(state.typeFont);
            });
        });

        el('upload-image-btn').onclick = () => el('upload-image').click();
        el('upload-image').onchange = () => {
            const f = el('upload-image').files[0];
            if (!f) return;
            if (!f.type.startsWith('image/')) {
                updateStatus('sign-status', 'Please choose an image file.', 'text-red');
                return;
            }
            const reader = new FileReader();
            reader.onload = () => {
                state.uploadedDataUrl = reader.result;
                const preview = el('upload-preview');
                preview.src = state.uploadedDataUrl;
                preview.hidden = false;
            };
            reader.readAsDataURL(f);
        };

        function captureActiveSignature() {
            if (state.padMode === 'draw') {
                const canvas = el('draw-canvas');
                const ctx = canvas.getContext('2d');
                const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
                let hasInk = false;
                for (let i = 3; i < data.length; i += 4) { if (data[i] !== 0) { hasInk = true; break; } }
                if (!hasInk) return null;
                return { dataUrl: canvas.toDataURL('image/png'), aspect: canvas.width / canvas.height };
            }
            if (state.padMode === 'type') {
                const text = el('type-input').value.trim();
                if (!text) return null;
                const family = FONT_FAMILY_MAP[state.typeFont] || 'Dancing Script';
                const fontSize = 64;
                const measure = document.createElement('canvas').getContext('2d');
                measure.font = `${fontSize}px "${family}", cursive`;
                const textWidth = Math.max(50, measure.measureText(text).width);
                const padding = 20;
                const off = document.createElement('canvas');
                off.width  = Math.ceil(textWidth + padding * 2);
                off.height = Math.ceil(fontSize * 1.6);
                const ctx = off.getContext('2d');
                ctx.font = `${fontSize}px "${family}", cursive`;
                ctx.textBaseline = 'middle';
                ctx.fillStyle = '#15181d';
                ctx.fillText(text, padding, off.height / 2);
                return { dataUrl: off.toDataURL('image/png'), aspect: off.width / off.height };
            }
            if (state.padMode === 'upload') {
                if (!state.uploadedDataUrl) return null;
                const img = el('upload-preview');
                const aspect = (img.naturalWidth && img.naturalHeight) ? img.naturalWidth / img.naturalHeight : 400 / 140;
                return { dataUrl: state.uploadedDataUrl, aspect };
            }
            return null;
        }

        function addItemToCurrentPage(dataUrl, aspect) {
            const canvas = el('canvas');
            const pageWidthPt  = canvas.width / SCALE;
            const pageHeightPt = canvas.height / SCALE;
            const widthPt  = Math.min(180, canvas.width * 0.4) / SCALE;
            const heightPt = widthPt / (aspect || 2.5);
            const items = state.pageItems[state.currentPage] || (state.pageItems[state.currentPage] = []);
            items.push({
                id: ++state.idCounter, dataUrl,
                x: (pageWidthPt - widthPt) / 2,
                y: pageHeightPt * 0.15,
                width: widthPt, height: heightPt,
            });
            renderSignOverlay();
            updateStatus('sign-status', 'Signature added. Drag to position it, or use the corner handle to resize.', 'text-green');
        }

        function refreshSavedSignatureButton() {
            let saved = null;
            try { saved = localStorage.getItem(SAVED_SIG_KEY); } catch (_) {}
            el('use-saved').hidden = !saved;
            el('forget-saved').hidden = !saved;
        }
        el('use-saved').onclick = () => {
            let saved = null;
            try { saved = localStorage.getItem(SAVED_SIG_KEY); } catch (_) {}
            if (!saved) return;
            addItemToCurrentPage(saved, 400 / 140);
        };
        el('forget-saved').onclick = () => {
            try { localStorage.removeItem(SAVED_SIG_KEY); } catch (_) {}
            refreshSavedSignatureButton();
        };
        refreshSavedSignatureButton();

        el('add-btn').onclick = async () => {
            if (!state.pdfDoc) { updateStatus('sign-status', 'Select a PDF first.', 'text-red'); return; }
            if (state.padMode === 'type') {
                const family = FONT_FAMILY_MAP[state.typeFont] || 'Dancing Script';
                try { await document.fonts.load(`64px "${family}"`); } catch (_) { /* fall back to generic cursive */ }
            }
            const captured = captureActiveSignature();
            if (!captured) {
                const msg = state.padMode === 'draw' ? 'Draw a signature first.'
                    : state.padMode === 'type' ? 'Type a name first.'
                    : 'Choose an image first.';
                updateStatus('sign-status', msg, 'text-red');
                return;
            }
            addItemToCurrentPage(captured.dataUrl, captured.aspect);
            if (el('remember').checked) {
                try { localStorage.setItem(SAVED_SIG_KEY, captured.dataUrl); } catch (_) {}
                refreshSavedSignatureButton();
            }
        };

        el('btn').onclick = async () => {
            if (!state.file) { updateStatus('sign-status', 'Select a PDF first.', 'text-red'); return; }
            const allSignatures = [];
            Object.keys(state.pageItems).forEach(pageIdx => {
                (state.pageItems[pageIdx] || []).forEach(item => {
                    allSignatures.push({
                        page: parseInt(pageIdx), x: item.x, y: item.y,
                        width: item.width, height: item.height, image: item.dataUrl,
                    });
                });
            });
            if (!allSignatures.length) { updateStatus('sign-status', 'Add at least one signature to the page first.', 'text-red'); return; }
            const check = validateFileSizes([state.file]);
            if (!check.ok) { updateStatus('sign-status', check.msg, 'text-red'); return; }
            if (check.warn) updateStatus('sign-status', check.warn, '');
            const password = el('password').value;
            const buffer = await toUint8(state.file);
            pendingDownloads['sign-status'] = stem(state.file.name) + '_signed.pdf';
            runWhenReady('sign-status', () => {
                pendingFooters['sign-status'] = el('footer')?.checked ?? false;
                updateStatus('sign-status', 'Applying signatures...', '');
                worker.postMessage({ id: 'sign-status', action: 'SIGN', payload: { buffer, signatures: allSignatures, password } }, [buffer.buffer]);
            });
        };
    })();

    /** ════ FILL FORM ═══════════════════════════════════════════════════════ */
    const fillformInput = document.getElementById('fillform-upload');
    let fillformPdfDoc = null, fillformCurrentPage = 0, fillformTotalPages = 0;
    let fillformFieldsByPage = {};  // { pageIndex: [{ fieldName, fieldType, rect, exportValue, options, multiLine, radioButton }] }
    let fillformValues = {};        // { fieldName: value }, persists across page navigation
    let fillformFile = null;
    let fillformScale = 1.5;

    fillformInput.onchange = async () => {
        const f = fillformInput.files[0];
        if (!f) return;
        lastLoadedFile = f; lastLoadedTool = 'fillform';
        fillformFile = f;
        fillformFieldsByPage = {};
        fillformValues = {};
        fillformCurrentPage = 0;
        document.getElementById('fillform-workspace').style.display = 'none';
        const password = document.getElementById('fillform-password').value;
        updateStatus('fillform-status', `Loading ${f.name}...`, '');
        try {
            const buf = await f.arrayBuffer();
            fillformPdfDoc = await pdfjsLib.getDocument({ data: buf, password: password || undefined }).promise;
            fillformTotalPages = fillformPdfDoc.numPages;

            // Fetch each page's annotations concurrently (independent reads) — merging into
            // fillformValues still happens in page order afterward, so field-value precedence
            // ("first page a field appears on wins") is unaffected by fetch order.
            const pagesFields = await Promise.all(
                Array.from({ length: fillformTotalPages }, async (_, i) => {
                    const page = await fillformPdfDoc.getPage(i + 1);
                    const annots = await page.getAnnotations({ intent: 'display' });
                    return annots.filter(a => a.subtype === 'Widget' && a.fieldName && a.fieldType && a.fieldType !== 'Sig');
                })
            );
            let fieldCount = 0;
            pagesFields.forEach((fields, i) => {
                fillformFieldsByPage[i] = fields;
                fields.forEach(field => {
                    fieldCount++;
                    if (!(field.fieldName in fillformValues)) {
                        fillformValues[field.fieldName] = field.fieldValue || '';
                    }
                });
            });

            if (fieldCount === 0) {
                updateStatus('fillform-status', `"${f.name}" has no fillable form fields.`, 'text-red');
                return;
            }

            document.getElementById('fillform-workspace').style.display = '';
            await renderFillFormPage();
            updateStatus('fillform-status', `${f.name}, ${fieldCount} field(s) across ${fillformTotalPages} page(s)`, 'text-green');
        } catch (err) {
            document.getElementById('fillform-workspace').style.display = 'none';
            const msg = err.name === 'PasswordException'
                ? 'This PDF is password protected, or the password entered was incorrect. Enter the correct document password and try again.'
                : `Could not read "${f.name}": ${err.message || 'invalid PDF'}`;
            updateStatus('fillform-status', msg, 'text-red');
        }
    };
    bindSimpleDrop('drop-zone-fillform', fillformInput);

    async function renderFillFormPage() {
        const page = await fillformPdfDoc.getPage(fillformCurrentPage + 1);
        const unscaled = page.getViewport({ scale: 1 });
        const availWidth = document.getElementById('fillform-canvas-wrap').parentElement.clientWidth;
        fillformScale = availWidth > 0 ? Math.min(availWidth / unscaled.width, 2.5) : 1.5;
        const viewport = page.getViewport({ scale: fillformScale });
        const canvas = document.getElementById('fillform-canvas');
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        await page.render({ canvasContext: canvas.getContext('2d'), viewport, annotationMode: 0 }).promise;
        const pager = document.getElementById('fillform-pager');
        pager.style.display = fillformTotalPages > 1 ? '' : 'none';
        document.getElementById('fillform-page-indicator').textContent = `Page ${fillformCurrentPage + 1} / ${fillformTotalPages}`;
        document.getElementById('fillform-prev-page').disabled = fillformCurrentPage === 0;
        document.getElementById('fillform-next-page').disabled = fillformCurrentPage === fillformTotalPages - 1;
        renderFillFormOverlay();
    }

    function renderFillFormOverlay() {
        const overlay = document.getElementById('fillform-overlay');
        const canvas  = document.getElementById('fillform-canvas');
        overlay.style.width  = canvas.width + 'px';
        overlay.style.height = canvas.height + 'px';
        overlay.innerHTML = '';
        const fields = fillformFieldsByPage[fillformCurrentPage] || [];

        fields.forEach(field => {
            if (field.hidden) return;
            const [x1, y1, x2, y2] = field.rect;
            const left   = x1 * fillformScale;
            const top    = canvas.height - y2 * fillformScale;
            const width  = (x2 - x1) * fillformScale;
            const height = (y2 - y1) * fillformScale;
            let el;

            if (field.fieldType === 'Btn' && field.radioButton) {
                el = document.createElement('input');
                el.type = 'radio';
                el.name = field.fieldName;
                el.className = 'fillform-field';
                el.checked = fillformValues[field.fieldName] === field.exportValue;
                el.onchange = () => { fillformValues[field.fieldName] = field.exportValue; };
            } else if (field.fieldType === 'Btn') {
                el = document.createElement('input');
                el.type = 'checkbox';
                el.className = 'fillform-field';
                el.checked = fillformValues[field.fieldName] === field.exportValue;
                el.onchange = () => { fillformValues[field.fieldName] = el.checked ? field.exportValue : '/Off'; };
            } else if (field.fieldType === 'Ch') {
                el = document.createElement('select');
                el.className = 'fillform-field';
                (field.options || []).forEach(opt => {
                    const o = document.createElement('option');
                    o.value = opt.exportValue;
                    o.textContent = opt.displayValue;
                    el.appendChild(o);
                });
                el.value = fillformValues[field.fieldName] || '';
                el.onchange = () => { fillformValues[field.fieldName] = el.value; };
            } else if (field.multiLine) {
                el = document.createElement('textarea');
                el.className = 'fillform-field';
                el.value = fillformValues[field.fieldName] || '';
                el.oninput = () => { fillformValues[field.fieldName] = el.value; };
            } else {
                el = document.createElement('input');
                el.type = 'text';
                el.className = 'fillform-field';
                el.value = fillformValues[field.fieldName] || '';
                el.oninput = () => { fillformValues[field.fieldName] = el.value; };
            }

            if (el.tagName !== 'INPUT' || (el.type !== 'checkbox' && el.type !== 'radio')) {
                el.style.fontSize = Math.max(9, Math.min(height * 0.6, 11 * fillformScale)) + 'px';
            }

            if (field.readOnly) {
                if (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && el.type === 'text')) {
                    el.readOnly = true;
                } else {
                    el.disabled = true;
                }
            }

            el.style.left   = left + 'px';
            el.style.top    = top + 'px';
            el.style.width  = width + 'px';
            el.style.height = height + 'px';
            overlay.appendChild(el);
        });
    }

    document.getElementById('fillform-prev-page').onclick = () => {
        if (fillformCurrentPage > 0) { fillformCurrentPage--; renderFillFormPage(); }
    };
    document.getElementById('fillform-next-page').onclick = () => {
        if (fillformCurrentPage < fillformTotalPages - 1) { fillformCurrentPage++; renderFillFormPage(); }
    };

    document.getElementById('fillform-btn').onclick = async () => {
        if (!fillformFile) { updateStatus('fillform-status', 'Select a PDF first.', 'text-red'); return; }
        const check = validateFileSizes([fillformFile]);
        if (!check.ok) { updateStatus('fillform-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('fillform-status', check.warn, '');
        const password = document.getElementById('fillform-password').value;
        const flatten  = document.getElementById('fillform-flatten').checked;
        const buffer   = await toUint8(fillformFile);
        pendingDownloads['fillform-status'] = stem(fillformFile.name) + (flatten ? '_filled_flat.pdf' : '_filled.pdf');
        runWhenReady('fillform-status', () => {
            pendingFooters['fillform-status'] = document.getElementById('fillform-footer')?.checked ?? false;
            updateStatus('fillform-status', 'Filling form...', '');
            worker.postMessage({ id: 'fillform-status', action: 'FILL_FORM', payload: { buffer, fields: fillformValues, flatten, password } }, [buffer.buffer]);
        });
    };

    /** ════ PROTECT ══════════════════════════════════════════════════════════ */
    const protectInput = document.getElementById('protect-upload');
    protectInput.onchange = () => {
        if (protectInput.files[0]) {
            lastLoadedFile = protectInput.files[0]; lastLoadedTool = 'protect';
            updateStatus('protect-status', `Loaded: ${protectInput.files[0].name}`, 'text-green');
        }
    };
    bindSimpleDrop('drop-zone-protect', protectInput);

    function bindPasswordToggle(inputId, btnId) {
        const input = document.getElementById(inputId);
        const btn = document.getElementById(btnId);
        btn.onclick = () => {
            const showing = input.type === 'text';
            input.type = showing ? 'password' : 'text';
            btn.setAttribute('aria-pressed', String(!showing));
            btn.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
            btn.innerHTML = showing
                ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>'
                : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.94 10.94 0 0112 20c-7 0-11-8-11-8a20.3 20.3 0 015.06-5.94M9.9 4.24A10.94 10.94 0 0112 4c7 0 11 8 11 8a20.3 20.3 0 01-3.22 4.44M14.12 14.12a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
        };
    }
    bindPasswordToggle('protect-new-password', 'protect-new-password-toggle');
    bindPasswordToggle('protect-confirm-password', 'protect-confirm-password-toggle');

    function scorePasswordStrength(pw) {
        if (!pw) return null;
        if (pw.length < 8) return { level: 'weak', label: 'Weak', pct: 20 };

        let variety = 0;
        if (/[a-z]/.test(pw)) variety++;
        if (/[A-Z]/.test(pw)) variety++;
        if (/[0-9]/.test(pw)) variety++;
        if (/[^A-Za-z0-9]/.test(pw)) variety++;
        const long = pw.length >= 12;

        // variety: how many of {lower, upper, digit, symbol} appear. long: 12+ chars.
        if (variety <= 1) return { level: 'weak',   label: 'Weak',   pct: 35 };
        if (variety === 2) return long
            ? { level: 'fair',   label: 'Fair',   pct: 65 }
            : { level: 'fair',   label: 'Fair',   pct: 55 };
        return long
            ? { level: 'strong', label: 'Strong', pct: 100 }
            : { level: 'strong', label: 'Strong', pct: 90 };
    }
    const protectStrengthColors = { weak: '#dc2626', fair: '#d97706', strong: '#059669' };
    document.getElementById('protect-new-password').addEventListener('input', function () {
        const wrap = document.getElementById('protect-strength');
        const fill = document.getElementById('protect-strength-fill');
        const label = document.getElementById('protect-strength-label');
        const score = scorePasswordStrength(this.value);
        if (!score) { wrap.hidden = true; return; }
        wrap.hidden = false;
        fill.style.width = score.pct + '%';
        fill.style.backgroundColor = protectStrengthColors[score.level];
        label.textContent = score.label;
        label.className = 'password-strength-label strength-' + score.level;
    });

    document.getElementById('protect-btn').onclick = async () => {
        if (!protectInput.files[0]) { updateStatus('protect-status', 'Select a PDF first.', 'text-red'); return; }
        const check = validateFileSizes([protectInput.files[0]]);
        if (!check.ok) { updateStatus('protect-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('protect-status', check.warn, '');

        const currentPassword = document.getElementById('protect-current-password').value;
        const newPassword     = document.getElementById('protect-new-password').value;
        const confirmPassword = document.getElementById('protect-confirm-password').value;
        const mismatchEl = document.getElementById('protect-mismatch');

        if (!newPassword) {
            mismatchEl.hidden = true;
            updateStatus('protect-status', 'Enter a password to protect this PDF.', 'text-red');
            return;
        }
        if (newPassword !== confirmPassword) {
            mismatchEl.hidden = false;
            updateStatus('protect-status', "Passwords don't match.", 'text-red');
            return;
        }
        mismatchEl.hidden = true;

        const buffer = await toUint8(protectInput.files[0]);
        pendingDownloads['protect-status'] = stem(protectInput.files[0].name) + '_protected.pdf';
        runWhenReady('protect-status', () => {
            pendingFooters['protect-status'] = false; // never chain into ADD_FOOTER — it would try to reopen the newly-encrypted file with a blank password
            updateStatus('protect-status', 'Encrypting...', '');
            worker.postMessage(
                { id: 'protect-status', action: 'PROTECT', payload: { buffer, newPassword, password: currentPassword } },
                [buffer.buffer]
            );
        });
    };

    /** ════ UNLOCK ═══════════════════════════════════════════════════════════ */
    const unlockInput = document.getElementById('unlock-upload');
    unlockInput.onchange = () => {
        if (unlockInput.files[0]) {
            lastLoadedFile = unlockInput.files[0]; lastLoadedTool = 'unlock';
            updateStatus('unlock-status', `Loaded: ${unlockInput.files[0].name}`, 'text-green');
        }
    };
    bindSimpleDrop('drop-zone-unlock', unlockInput);
    bindPasswordToggle('unlock-password', 'unlock-password-toggle');

    document.getElementById('unlock-btn').onclick = async () => {
        if (!unlockInput.files[0]) { updateStatus('unlock-status', 'Select a PDF first.', 'text-red'); return; }
        const check = validateFileSizes([unlockInput.files[0]]);
        if (!check.ok) { updateStatus('unlock-status', check.msg, 'text-red'); return; }
        if (check.warn) updateStatus('unlock-status', check.warn, '');

        const password = document.getElementById('unlock-password').value;
        const buffer = await toUint8(unlockInput.files[0]);
        pendingDownloads['unlock-status'] = stem(unlockInput.files[0].name) + '_unlocked.pdf';
        runWhenReady('unlock-status', () => {
            pendingFooters['unlock-status'] = false;
            updateStatus('unlock-status', 'Removing encryption...', '');
            worker.postMessage(
                { id: 'unlock-status', action: 'UNLOCK', payload: { buffer, password } },
                [buffer.buffer]
            );
        });
    };

    /** ════ FILL & SIGN ══════════════════════════════════════════════════════ */
    (function initFillSignTool() {
        const input = document.getElementById('fillsign-upload');
        const SAVED_SIG_KEY = 'nilpdf_saved_signature';
        const FONT_FAMILY_MAP = {
            'sign-font-dancing': 'Dancing Script',
            'sign-font-caveat': 'Caveat',
            'sign-font-pacifico': 'Pacifico',
            'sign-font-sacramento': 'Sacramento',
        };
        const state = {
            pdfDoc: null, currentPage: 0, totalPages: 0, file: null,
            scale: 1.5,  // recomputed to fit the container on each page render, see renderFillSignPage
            fieldsByPage: {}, fieldValues: {}, hasFields: false,
            textItems: {},  // { pageIndex: [{ id, x, y, text, size }] }
            sigItems: {},   // { pageIndex: [{ id, dataUrl, x, y, width, height }] }
            idCounter: 0,
            mode: 'text',
            padMode: 'draw', typeFont: 'sign-font-dancing', uploadedDataUrl: null,
        };
        const el = id => document.getElementById(`fillsign-${id}`);

        function setMode(mode) {
            state.mode = mode;
            el('mode-fields').classList.toggle('active', mode === 'fields');
            el('mode-text').classList.toggle('active', mode === 'text');
            el('mode-sign').classList.toggle('active', mode === 'sign');
            el('mode-fields').setAttribute('aria-pressed', String(mode === 'fields'));
            el('mode-text').setAttribute('aria-pressed', String(mode === 'text'));
            el('mode-sign').setAttribute('aria-pressed', String(mode === 'sign'));
            el('hint-fields').hidden = mode !== 'fields';
            el('hint-text').hidden = mode !== 'text';
            el('hint-sign').hidden = mode !== 'sign';
            el('sign-pad').hidden = mode !== 'sign';
        }
        el('mode-fields').onclick = () => setMode('fields');
        el('mode-text').onclick = () => setMode('text');
        el('mode-sign').onclick = () => setMode('sign');

        input.onchange = async () => {
            const f = input.files[0];
            if (!f) return;
            lastLoadedFile = f; lastLoadedTool = 'fillsign';
            state.file = f;
            state.fieldsByPage = {}; state.fieldValues = {}; state.hasFields = false;
            state.textItems = {}; state.sigItems = {};
            state.currentPage = 0;
            el('workspace').style.display = 'none';
            updateStatus('fillsign-status', `Loading ${f.name}...`, '');
            try {
                const password = el('password').value;
                state.pdfDoc = await pdfjsLib.getDocument({ data: await f.arrayBuffer(), password: password || undefined }).promise;
                state.totalPages = state.pdfDoc.numPages;

                // Fetch each page's annotations concurrently — same approach as Fill Forms.
                const pagesFields = await Promise.all(
                    Array.from({ length: state.totalPages }, async (_, i) => {
                        const page = await state.pdfDoc.getPage(i + 1);
                        const annots = await page.getAnnotations({ intent: 'display' });
                        return annots.filter(a => a.subtype === 'Widget' && a.fieldName && a.fieldType && a.fieldType !== 'Sig');
                    })
                );
                let fieldCount = 0;
                pagesFields.forEach((fields, i) => {
                    state.fieldsByPage[i] = fields;
                    fields.forEach(field => {
                        fieldCount++;
                        if (!(field.fieldName in state.fieldValues)) {
                            state.fieldValues[field.fieldName] = field.fieldValue || '';
                        }
                    });
                });
                state.hasFields = fieldCount > 0;
                el('mode-fields').hidden = !state.hasFields;
                el('flatten-label').hidden = !state.hasFields;
                setMode(state.hasFields ? 'fields' : 'text');

                el('workspace').style.display = '';
                await renderFillSignPage();
                const fieldMsg = state.hasFields ? `${fieldCount} field(s) across ` : '';
                updateStatus('fillsign-status', `${f.name}, ${fieldMsg}${state.totalPages} page(s)`, 'text-green');
            } catch (err) {
                el('workspace').style.display = 'none';
                const msg = err.name === 'PasswordException'
                    ? 'This PDF is password protected, or the password entered was incorrect. Enter the correct document password and try again.'
                    : `Could not read "${f.name}": ${err.message || 'invalid PDF'}`;
                updateStatus('fillsign-status', msg, 'text-red');
            }
        };
        bindSimpleDrop('drop-zone-fillsign', input);

        async function renderFillSignPage() {
            const page = await state.pdfDoc.getPage(state.currentPage + 1);
            // Adaptive scale-to-fit, same approach as the standalone Fill Forms
            // tool, so a large-format form doesn't overflow the workspace.
            const unscaled = page.getViewport({ scale: 1 });
            const availWidth = el('canvas-wrap').parentElement.clientWidth;
            state.scale = availWidth > 0 ? Math.min(availWidth / unscaled.width, 2.5) : 1.5;
            const viewport = page.getViewport({ scale: state.scale });
            const canvas = el('canvas');
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            await page.render({ canvasContext: canvas.getContext('2d'), viewport, annotationMode: 0 }).promise;
            el('page-indicator').textContent = `Page ${state.currentPage + 1} / ${state.totalPages}`;
            el('prev-page').disabled = state.currentPage === 0;
            el('next-page').disabled = state.currentPage === state.totalPages - 1;
            renderFillSignOverlay();
        }
        el('prev-page').onclick = () => { if (state.currentPage > 0) { state.currentPage--; renderFillSignPage(); } };
        el('next-page').onclick = () => { if (state.currentPage < state.totalPages - 1) { state.currentPage++; renderFillSignPage(); } };

        function renderFillSignOverlay() {
            const overlay = el('overlay');
            const canvas  = el('canvas');
            overlay.style.width  = canvas.width + 'px';
            overlay.style.height = canvas.height + 'px';
            overlay.innerHTML = '';

            // Form fields — always rendered and interactive, independent of mode,
            // the same way the standalone Fill Forms tool does it.
            (state.fieldsByPage[state.currentPage] || []).forEach(field => {
                if (field.hidden) return;
                const [x1, y1, x2, y2] = field.rect;
                const left   = x1 * state.scale;
                const top    = canvas.height - y2 * state.scale;
                const width  = (x2 - x1) * state.scale;
                const height = (y2 - y1) * state.scale;
                let fieldEl;

                if (field.fieldType === 'Btn' && field.radioButton) {
                    fieldEl = document.createElement('input');
                    fieldEl.type = 'radio';
                    fieldEl.name = field.fieldName;
                    fieldEl.className = 'fillform-field';
                    fieldEl.checked = state.fieldValues[field.fieldName] === field.exportValue;
                    fieldEl.onchange = () => { state.fieldValues[field.fieldName] = field.exportValue; };
                } else if (field.fieldType === 'Btn') {
                    fieldEl = document.createElement('input');
                    fieldEl.type = 'checkbox';
                    fieldEl.className = 'fillform-field';
                    fieldEl.checked = state.fieldValues[field.fieldName] === field.exportValue;
                    fieldEl.onchange = () => { state.fieldValues[field.fieldName] = fieldEl.checked ? field.exportValue : '/Off'; };
                } else if (field.fieldType === 'Ch') {
                    fieldEl = document.createElement('select');
                    fieldEl.className = 'fillform-field';
                    (field.options || []).forEach(opt => {
                        const o = document.createElement('option');
                        o.value = opt.exportValue;
                        o.textContent = opt.displayValue;
                        fieldEl.appendChild(o);
                    });
                    fieldEl.value = state.fieldValues[field.fieldName] || '';
                    fieldEl.onchange = () => { state.fieldValues[field.fieldName] = fieldEl.value; };
                } else if (field.multiLine) {
                    fieldEl = document.createElement('textarea');
                    fieldEl.className = 'fillform-field';
                    fieldEl.value = state.fieldValues[field.fieldName] || '';
                    fieldEl.oninput = () => { state.fieldValues[field.fieldName] = fieldEl.value; };
                } else {
                    fieldEl = document.createElement('input');
                    fieldEl.type = 'text';
                    fieldEl.className = 'fillform-field';
                    fieldEl.value = state.fieldValues[field.fieldName] || '';
                    fieldEl.oninput = () => { state.fieldValues[field.fieldName] = fieldEl.value; };
                }

                if (fieldEl.tagName !== 'INPUT' || (fieldEl.type !== 'checkbox' && fieldEl.type !== 'radio')) {
                    fieldEl.style.fontSize = Math.max(9, Math.min(height * 0.6, 11 * state.scale)) + 'px';
                }
                if (field.readOnly) {
                    if (fieldEl.tagName === 'TEXTAREA' || (fieldEl.tagName === 'INPUT' && fieldEl.type === 'text')) fieldEl.readOnly = true;
                    else fieldEl.disabled = true;
                }
                fieldEl.style.left   = left + 'px';
                fieldEl.style.top    = top + 'px';
                fieldEl.style.width  = width + 'px';
                fieldEl.style.height = height + 'px';
                overlay.appendChild(fieldEl);
            });

            // Text notes — same box/remove-button shape as Edit PDF.
            (state.textItems[state.currentPage] || []).forEach(item => {
                const box = document.createElement('div');
                box.className = 'redact-text-box';
                box.style.left = (item.x * state.scale) + 'px';
                box.style.top  = (canvas.height - (item.y + item.size) * state.scale) + 'px';
                box.style.fontSize = (item.size * state.scale) + 'px';
                box.textContent = item.text;
                const rm = document.createElement('button');
                rm.type = 'button';
                rm.className = 'redact-item-remove';
                rm.setAttribute('aria-label', 'Remove');
                rm.textContent = '×';
                rm.onclick = e => { e.stopPropagation(); removeTextItem(item.id); };
                box.appendChild(rm);
                overlay.appendChild(box);
            });

            // Signatures — same drag/resize/duplicate/remove shape as Sign PDF.
            (state.sigItems[state.currentPage] || []).forEach(item => {
                const wrap = document.createElement('div');
                wrap.className = 'sign-item';
                wrap.dataset.id = item.id;
                wrap.style.left   = (item.x * state.scale) + 'px';
                wrap.style.top    = (canvas.height - (item.y + item.height) * state.scale) + 'px';
                wrap.style.width  = (item.width * state.scale) + 'px';
                wrap.style.height = (item.height * state.scale) + 'px';

                const img = document.createElement('img');
                img.src = item.dataUrl;
                img.alt = 'Signature';
                wrap.appendChild(img);

                const toolbar = document.createElement('div');
                toolbar.className = 'sign-item-toolbar';
                const dupBtn = document.createElement('button');
                dupBtn.type = 'button'; dupBtn.className = 'sign-item-btn sign-item-duplicate';
                dupBtn.textContent = '⧉'; dupBtn.setAttribute('aria-label', 'Duplicate signature');
                dupBtn.onclick = e => { e.stopPropagation(); duplicateSigItem(item.id); };
                const rmBtn = document.createElement('button');
                rmBtn.type = 'button'; rmBtn.className = 'sign-item-btn sign-item-remove';
                rmBtn.textContent = '×'; rmBtn.setAttribute('aria-label', 'Remove signature');
                rmBtn.onclick = e => { e.stopPropagation(); removeSigItem(item.id); };
                toolbar.appendChild(dupBtn);
                toolbar.appendChild(rmBtn);
                wrap.appendChild(toolbar);

                const handle = document.createElement('div');
                handle.className = 'sign-item-handle';
                handle.setAttribute('aria-hidden', 'true');
                wrap.appendChild(handle);

                bindSigItemInteraction(wrap, item, handle);
                overlay.appendChild(wrap);
            });
        }

        function addTextItem(px, py, text) {
            const canvas = el('canvas');
            const size = 14;
            const x = px / state.scale;
            const y = (canvas.height - py) / state.scale - size;
            const items = state.textItems[state.currentPage] || (state.textItems[state.currentPage] = []);
            items.push({ id: ++state.idCounter, x, y, text, size });
            renderFillSignOverlay();
        }
        function removeTextItem(id) {
            const items = state.textItems[state.currentPage] || [];
            state.textItems[state.currentPage] = items.filter(i => i.id !== id);
            renderFillSignOverlay();
        }

        el('overlay').addEventListener('pointerdown', e => {
            if (e.target !== el('overlay') || state.mode !== 'text') return;
            const rect = el('overlay').getBoundingClientRect();
            const px = e.clientX - rect.left, py = e.clientY - rect.top;
            const text = prompt('Text to add on this page:');
            if (text && text.trim()) addTextItem(px, py, text.trim());
        });

        /* ---- Placed signatures: draggable + resizable (same as Sign PDF) ---- */
        function bindSigItemInteraction(wrap, item, handle) {
            let mode = null; // 'move' | 'resize'
            let startClientX = 0, startClientY = 0, startLeft = 0, startTop = 0, startWidth = 0, startHeight = 0;
            let activePointerId = null;

            function applyPdfCoords(leftPx, topPx, widthPx, heightPx) {
                const canvas = el('canvas');
                item.width  = widthPx / state.scale;
                item.height = heightPx / state.scale;
                item.x = leftPx / state.scale;
                item.y = (canvas.height - topPx - heightPx) / state.scale;
            }
            function onPointerMove(e) {
                if (activePointerId === null || e.pointerId !== activePointerId) return;
                const dx = e.clientX - startClientX;
                const dy = e.clientY - startClientY;
                if (mode === 'move') {
                    const newLeft = startLeft + dx, newTop = startTop + dy;
                    wrap.style.left = newLeft + 'px';
                    wrap.style.top  = newTop + 'px';
                    applyPdfCoords(newLeft, newTop, startWidth, startHeight);
                } else if (mode === 'resize') {
                    const newWidth  = Math.max(20, startWidth + dx);
                    const newHeight = Math.max(12, startHeight + dy);
                    wrap.style.width  = newWidth + 'px';
                    wrap.style.height = newHeight + 'px';
                    applyPdfCoords(startLeft, startTop, newWidth, newHeight);
                }
            }
            function onPointerUp(e) {
                if (activePointerId === null || e.pointerId !== activePointerId) return;
                wrap.removeEventListener('pointermove', onPointerMove);
                wrap.removeEventListener('pointerup', onPointerUp);
                wrap.removeEventListener('pointercancel', onPointerUp);
                mode = null; activePointerId = null;
            }
            function beginDrag(e, dragMode) {
                mode = dragMode;
                activePointerId = e.pointerId;
                startClientX = e.clientX; startClientY = e.clientY;
                startLeft   = parseFloat(wrap.style.left)   || 0;
                startTop    = parseFloat(wrap.style.top)    || 0;
                startWidth  = parseFloat(wrap.style.width)  || 0;
                startHeight = parseFloat(wrap.style.height) || 0;
                try { wrap.setPointerCapture(e.pointerId); } catch (_) { /* no active pointer (e.g. synthetic input) */ }
                wrap.addEventListener('pointermove', onPointerMove);
                wrap.addEventListener('pointerup', onPointerUp);
                wrap.addEventListener('pointercancel', onPointerUp);
                e.preventDefault();
            }
            wrap.addEventListener('pointerdown', e => {
                if (e.target === handle || e.target.closest('.sign-item-btn')) return;
                beginDrag(e, 'move');
            });
            handle.addEventListener('pointerdown', e => {
                e.stopPropagation();
                beginDrag(e, 'resize');
            });

            wrap.tabIndex = 0;
            wrap.setAttribute('role', 'group');
            wrap.setAttribute('aria-label', 'Placed signature. Arrow keys move it, Alt plus arrow keys resize it, Delete removes it.');
            wrap.addEventListener('keydown', e => {
                if (e.key === 'Delete' || e.key === 'Backspace') {
                    e.preventDefault();
                    removeSigItem(item.id);
                    return;
                }
                const arrowKeys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'];
                if (!arrowKeys.includes(e.key)) return;
                e.preventDefault();
                const step = e.shiftKey ? 10 : 2;
                let left   = parseFloat(wrap.style.left)   || 0;
                let top    = parseFloat(wrap.style.top)    || 0;
                let width  = parseFloat(wrap.style.width)  || 0;
                let height = parseFloat(wrap.style.height) || 0;
                if (e.altKey) {
                    if (e.key === 'ArrowRight') width  = Math.max(20, width + step);
                    if (e.key === 'ArrowLeft')  width  = Math.max(20, width - step);
                    if (e.key === 'ArrowDown')  height = Math.max(12, height + step);
                    if (e.key === 'ArrowUp')    height = Math.max(12, height - step);
                } else {
                    if (e.key === 'ArrowRight') left += step;
                    if (e.key === 'ArrowLeft')  left -= step;
                    if (e.key === 'ArrowDown')  top  += step;
                    if (e.key === 'ArrowUp')    top  -= step;
                }
                wrap.style.left = left + 'px'; wrap.style.top = top + 'px';
                wrap.style.width = width + 'px'; wrap.style.height = height + 'px';
                applyPdfCoords(left, top, width, height);
            });
        }
        function duplicateSigItem(id) {
            const items = state.sigItems[state.currentPage] || [];
            const item = items.find(i => i.id === id);
            if (!item) return;
            const offset = 10 / state.scale;
            items.push({ ...item, id: ++state.idCounter, x: item.x + offset, y: Math.max(0, item.y - offset) });
            renderFillSignOverlay();
        }
        function removeSigItem(id) {
            const items = state.sigItems[state.currentPage] || [];
            state.sigItems[state.currentPage] = items.filter(i => i.id !== id);
            renderFillSignOverlay();
        }

        /* ---- Signature pad: Draw / Type / Upload (same as Sign PDF) ---- */
        function setPadMode(mode) {
            state.padMode = mode;
            ['draw', 'type', 'upload'].forEach(m => {
                el(`padmode-${m}`).classList.toggle('active', m === mode);
                el(`padmode-${m}`).setAttribute('aria-selected', m === mode ? 'true' : 'false');
                el(`pad-${m}`).hidden = m !== mode;
            });
        }
        el('padmode-draw').onclick   = () => setPadMode('draw');
        el('padmode-type').onclick   = () => setPadMode('type');
        el('padmode-upload').onclick = () => setPadMode('upload');

        (function bindDrawCanvas() {
            const canvas = el('draw-canvas');
            const ctx = canvas.getContext('2d');
            let drawing = false, lastX = 0, lastY = 0, activePointerId = null;
            ctx.strokeStyle = '#15181d';
            ctx.lineWidth = 2.5;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';

            function pos(e) {
                const rect = canvas.getBoundingClientRect();
                return {
                    x: (e.clientX - rect.left) * (canvas.width / rect.width),
                    y: (e.clientY - rect.top) * (canvas.height / rect.height),
                };
            }
            canvas.addEventListener('pointerdown', e => {
                drawing = true;
                activePointerId = e.pointerId;
                try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
                const p = pos(e);
                lastX = p.x; lastY = p.y;
                e.preventDefault();
            });
            canvas.addEventListener('pointermove', e => {
                if (!drawing || e.pointerId !== activePointerId) return;
                const p = pos(e);
                ctx.beginPath();
                ctx.moveTo(lastX, lastY);
                ctx.lineTo(p.x, p.y);
                ctx.stroke();
                lastX = p.x; lastY = p.y;
            });
            ['pointerup', 'pointercancel'].forEach(evt => canvas.addEventListener(evt, e => {
                if (e.pointerId !== activePointerId) return;
                drawing = false; activePointerId = null;
            }));
            el('draw-clear').onclick = () => ctx.clearRect(0, 0, canvas.width, canvas.height);
        })();

        el('type-input').addEventListener('input', () => {
            el('type-preview').textContent = el('type-input').value.trim() || 'Your Name';
        });
        document.querySelectorAll('#fillsign-pad-type .sign-font-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#fillsign-pad-type .sign-font-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                state.typeFont = btn.dataset.font;
                const preview = el('type-preview');
                Object.keys(FONT_FAMILY_MAP).forEach(f => preview.classList.remove(f));
                preview.classList.add(state.typeFont);
            });
        });

        el('upload-image-btn').onclick = () => el('upload-image').click();
        el('upload-image').onchange = () => {
            const f = el('upload-image').files[0];
            if (!f) return;
            if (!f.type.startsWith('image/')) {
                updateStatus('fillsign-status', 'Please choose an image file.', 'text-red');
                return;
            }
            const reader = new FileReader();
            reader.onload = () => {
                state.uploadedDataUrl = reader.result;
                const preview = el('upload-preview');
                preview.src = state.uploadedDataUrl;
                preview.hidden = false;
            };
            reader.readAsDataURL(f);
        };

        function captureActiveSignature() {
            if (state.padMode === 'draw') {
                const canvas = el('draw-canvas');
                const ctx = canvas.getContext('2d');
                const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
                let hasInk = false;
                for (let i = 3; i < data.length; i += 4) { if (data[i] !== 0) { hasInk = true; break; } }
                if (!hasInk) return null;
                return { dataUrl: canvas.toDataURL('image/png'), aspect: canvas.width / canvas.height };
            }
            if (state.padMode === 'type') {
                const text = el('type-input').value.trim();
                if (!text) return null;
                const family = FONT_FAMILY_MAP[state.typeFont] || 'Dancing Script';
                const fontSize = 64;
                const measure = document.createElement('canvas').getContext('2d');
                measure.font = `${fontSize}px "${family}", cursive`;
                const textWidth = Math.max(50, measure.measureText(text).width);
                const padding = 20;
                const off = document.createElement('canvas');
                off.width  = Math.ceil(textWidth + padding * 2);
                off.height = Math.ceil(fontSize * 1.6);
                const ctx = off.getContext('2d');
                ctx.font = `${fontSize}px "${family}", cursive`;
                ctx.textBaseline = 'middle';
                ctx.fillStyle = '#15181d';
                ctx.fillText(text, padding, off.height / 2);
                return { dataUrl: off.toDataURL('image/png'), aspect: off.width / off.height };
            }
            if (state.padMode === 'upload') {
                if (!state.uploadedDataUrl) return null;
                const img = el('upload-preview');
                const aspect = (img.naturalWidth && img.naturalHeight) ? img.naturalWidth / img.naturalHeight : 400 / 140;
                return { dataUrl: state.uploadedDataUrl, aspect };
            }
            return null;
        }

        function addSigToCurrentPage(dataUrl, aspect) {
            const canvas = el('canvas');
            const pageWidthPt  = canvas.width / state.scale;
            const pageHeightPt = canvas.height / state.scale;
            const widthPt  = Math.min(180, canvas.width * 0.4) / state.scale;
            const heightPt = widthPt / (aspect || 2.5);
            const items = state.sigItems[state.currentPage] || (state.sigItems[state.currentPage] = []);
            items.push({
                id: ++state.idCounter, dataUrl,
                x: (pageWidthPt - widthPt) / 2,
                y: pageHeightPt * 0.15,
                width: widthPt, height: heightPt,
            });
            renderFillSignOverlay();
            updateStatus('fillsign-status', 'Signature added. Drag to position it, or use the corner handle to resize.', 'text-green');
        }

        function refreshSavedSignatureButton() {
            let saved = null;
            try { saved = localStorage.getItem(SAVED_SIG_KEY); } catch (_) {}
            el('use-saved').hidden = !saved;
            el('forget-saved').hidden = !saved;
        }
        el('use-saved').onclick = () => {
            let saved = null;
            try { saved = localStorage.getItem(SAVED_SIG_KEY); } catch (_) {}
            if (!saved) return;
            addSigToCurrentPage(saved, 400 / 140);
        };
        el('forget-saved').onclick = () => {
            try { localStorage.removeItem(SAVED_SIG_KEY); } catch (_) {}
            refreshSavedSignatureButton();
        };
        refreshSavedSignatureButton();

        el('add-btn').onclick = async () => {
            if (!state.pdfDoc) { updateStatus('fillsign-status', 'Select a PDF first.', 'text-red'); return; }
            if (state.padMode === 'type') {
                const family = FONT_FAMILY_MAP[state.typeFont] || 'Dancing Script';
                try { await document.fonts.load(`64px "${family}"`); } catch (_) { /* fall back to generic cursive */ }
            }
            const captured = captureActiveSignature();
            if (!captured) {
                const msg = state.padMode === 'draw' ? 'Draw a signature first.'
                    : state.padMode === 'type' ? 'Type a name first.'
                    : 'Choose an image first.';
                updateStatus('fillsign-status', msg, 'text-red');
                return;
            }
            addSigToCurrentPage(captured.dataUrl, captured.aspect);
            if (el('remember').checked) {
                try { localStorage.setItem(SAVED_SIG_KEY, captured.dataUrl); } catch (_) {}
                refreshSavedSignatureButton();
            }
        };

        el('btn').onclick = async () => {
            if (!state.file) { updateStatus('fillsign-status', 'Select a PDF first.', 'text-red'); return; }

            const hasAnyText = Object.values(state.textItems).some(arr => (arr || []).length > 0);
            const hasAnySig  = Object.values(state.sigItems).some(arr => (arr || []).length > 0);
            if (!state.hasFields && !hasAnyText && !hasAnySig) {
                updateStatus('fillsign-status', 'Fill in a field, add a text note, or add a signature first.', 'text-red');
                return;
            }
            const check = validateFileSizes([state.file]);
            if (!check.ok) { updateStatus('fillsign-status', check.msg, 'text-red'); return; }
            if (check.warn) updateStatus('fillsign-status', check.warn, '');

            const edits = [];
            Object.keys(state.textItems).forEach(pageIdx => {
                (state.textItems[pageIdx] || []).forEach(item => {
                    edits.push({ page: parseInt(pageIdx), type: 'text', x: item.x, y: item.y, text: item.text, size: item.size });
                });
            });
            const signatures = [];
            Object.keys(state.sigItems).forEach(pageIdx => {
                (state.sigItems[pageIdx] || []).forEach(item => {
                    signatures.push({ page: parseInt(pageIdx), x: item.x, y: item.y, width: item.width, height: item.height, image: item.dataUrl });
                });
            });
            const fields  = state.hasFields ? state.fieldValues : {};
            const flatten = state.hasFields ? (el('flatten').checked) : false;

            const password = el('password').value;
            const buffer = await toUint8(state.file);
            pendingDownloads['fillsign-status'] = stem(state.file.name) + '_filled_signed.pdf';
            runWhenReady('fillsign-status', () => {
                pendingFooters['fillsign-status'] = el('footer')?.checked ?? false;
                updateStatus('fillsign-status', 'Applying...', '');
                worker.postMessage(
                    { id: 'fillsign-status', action: 'FILL_AND_SIGN', payload: { buffer, fields, edits, signatures, flatten, password } },
                    [buffer.buffer]
                );
            });
        };
    })();

    /** ════ TOAST + PROCESSED-FILES COUNTER ══════════════════════════════════ */
    function showToast(msg) {
        const t = document.createElement('div');
        t.className = 'toast';
        t.textContent = msg;
        document.body.appendChild(t);
        requestAnimationFrame(() => t.classList.add('toast-visible'));
        setTimeout(() => { t.classList.remove('toast-visible'); setTimeout(() => t.remove(), 400); }, 2800);
    }

    // Aggregate usage: which tool finished, and nothing else. Without this,
    // analytics only sees page views and can't tell a visitor from someone who
    // actually processed a file. The payload is deliberately a single field,
    // taken from the fixed TOOL_META allowlist, so no file name, size, page
    // count or content can ever reach it, even by mistake at a call site.
    function recordToolUse(tool) {
        if (typeof gtag !== 'function' || !Object.prototype.hasOwnProperty.call(TOOL_META, tool)) return;
        gtag('event', 'tool_complete', { tool });
    }

    // Worker jobs are keyed by their status element id: 'status' for merge,
    // '<tool>-status' for every other tool.
    function toolForJob(id) {
        return id === 'status' ? 'merge' : String(id).replace(/-status$/, '');
    }

    function incrementCounter(tool) {
        recordToolUse(tool);
        const n = (parseInt(localStorage.getItem('nilpdf_count') || '0')) + 1;
        localStorage.setItem('nilpdf_count', n);
        const el = document.getElementById('counter-display');
        if (el) el.textContent = `${n} file${n === 1 ? '' : 's'} processed privately`;
        const milestones = [10, 50, 100, 500];
        if (milestones.includes(n)) showToast(`🎉 ${n} files processed, all privately!`);
    }

    (function loadCounter() {
        const n = parseInt(localStorage.getItem('nilpdf_count') || '0');
        if (n > 0) {
            const el = document.getElementById('counter-display');
            if (el) el.textContent = `${n} file${n === 1 ? '' : 's'} processed privately`;
        }
    })();

    /** ════ SHARE BUTTON ══════════════════════════════════════════════════════ */
    function getSharePayload() {
        const hash = location.hash.replace('#', '');
        const meta = TOOL_META[hash];
        const url  = 'https://nilpdf.com/' + (hash ? '#' + hash : '');
        const title = meta ? `NilPDF: ${meta.title}` : 'NilPDF: Free PDF Tools';
        const text  = meta
            ? `${meta.title}, free, no uploads, runs in your browser: ${url}`
            : 'NilPDF: 21 free PDF tools that run entirely in your browser. Zero uploads: https://nilpdf.com/';
        return { title, text, url };
    }

    document.getElementById('share-btn').onclick = () => {
        const payload = getSharePayload();
        if (navigator.share) {
            navigator.share(payload).catch(() => {});
        } else {
            navigator.clipboard.writeText(payload.url).then(() => showToast('Link copied!')).catch(() => {});
        }
    };

    function showShareNudge() {
        if (document.getElementById('share-nudge')) return;
        const payload = getSharePayload();
        const tweetText = encodeURIComponent(payload.text);
        const nudge = document.createElement('div');
        nudge.id = 'share-nudge';
        nudge.className = 'share-nudge';
        nudge.innerHTML = `
            <span>Liked it? Help others find NilPDF</span>
            <a class="nudge-tweet-btn" href="https://twitter.com/intent/tweet?text=${tweetText}" target="_blank" rel="noopener">Post on X</a>
            <button class="nudge-copy-btn" onclick="navigator.clipboard.writeText('${payload.url}').then(()=>showToast('Link copied!'));this.textContent='Copied!'">Copy link</button>
            <button class="nudge-dismiss" onclick="this.closest('.share-nudge').remove()" aria-label="Dismiss">✕</button>
        `;
        document.body.appendChild(nudge);
        requestAnimationFrame(() => nudge.classList.add('share-nudge-visible'));
        setTimeout(() => { nudge.classList.remove('share-nudge-visible'); setTimeout(() => nudge.remove(), 400); }, 12000);
    }

    /** ════ TOTEXT COPY-TO-CLIPBOARD ══════════════════════════════════════════ */
    document.getElementById('totext-copy-btn').onclick = () => {
        const text = document.getElementById('totext-preview').value;
        navigator.clipboard.writeText(text).then(() => showToast('Text copied!')).catch(() => {});
    };

    /** ════ KEYBOARD SHORTCUTS ════════════════════════════════════════════════ */
    document.addEventListener('keydown', e => {
        // Escape closes any open overlay regardless of focused element
        if (e.key === 'Escape') {
            document.getElementById('shortcuts-modal').style.display = 'none';
            if (!document.getElementById('feedback-modal').hidden) closeFeedback();
            return;
        }
        const typingTags = ['INPUT', 'TEXTAREA', 'SELECT'];
        if (typingTags.includes(e.target.tagName) || e.target.isContentEditable) return;
        if (e.target.closest('[role="dialog"], .modal-overlay, dialog')) return;
        const modal = document.getElementById('shortcuts-modal');
        if (e.key === '?' || e.key === '/') {
            modal.style.display = modal.style.display === 'flex' ? 'none' : 'flex';
            return;
        }
        if (e.key === 'Enter') {
            if (document.getElementById('workspace').style.display === 'none') return;
            const activeBtn = document.querySelector('.active-tool .primary-btn:not(:disabled)');
            if (activeBtn) activeBtn.click();
            return;
        }
        const num = parseInt(e.key);
        if (!isNaN(num)) {
            // Only digits 1-9 and 0 are bindable (10 slots), so only the first 10 tools are reachable here.
            const TOOL_NAMES = ['merge','compress','anonymize','split','reorder','rotate','remove','totext','topng','topdf'];
            const idx = num === 0 ? 9 : num - 1;
            const toolId = TOOL_NAMES[idx];
            if (toolId) openTool(toolId);
        }
    });

    /** ════ HASH ROUTING (init) ═══════════════════════════════════════════════ */
    (function initHash() {
        const hash = location.hash.replace('#', '');
        if (Object.prototype.hasOwnProperty.call(TOOL_META, hash)) {
            // Use replaceState so the initial load doesn't add a spurious history entry
            _showWorkspace(hash);
            history.replaceState({ view: 'tool', tool: hash }, '', '#' + hash);
        }
    })();

    /** ════ FEEDBACK MODAL ══════════════════════════════════════════════════════ */
    // Feedback is relayed through the Cloudflare Worker in feedback-worker/, which
    // holds the GitHub token server-side and creates the issue on our behalf.
    //
    // This page deliberately holds no GitHub credential of any kind. An earlier
    // version stamped a real PAT into the deployed HTML and called the GitHub API
    // straight from the browser; anything served to a browser is readable by
    // everyone who loads it, and a `public_repo` token grants write access to every
    // public repository on the account, not just this one. The Worker exists so the
    // credential never reaches the client.
    //
    // The endpoint is stamped at deploy time by static.yml from the
    // FEEDBACK_ENDPOINT Actions variable; unstamped builds disable the form.
    const _FEEDBACK_ENDPOINT = '__FEEDBACK_ENDPOINT__';

    // When the relay is not configured, feedback falls back to a pre-filled GitHub
    // issue that the visitor reviews and submits from their own account. No
    // credential and no server are involved: the page only builds a URL. The
    // labels are applied only for accounts with triage access and are otherwise
    // ignored by GitHub, which is harmless.
    const _FEEDBACK_ISSUE_URL = 'https://github.com/kdigitalsystems/nilpdf/issues/new';
    const _FEEDBACK_LABELS = { bug: 'bug', feature: 'enhancement', general: '' };
    const _FEEDBACK_TYPE_NAMES = { bug: 'Bug report', feature: 'Feature request', general: 'General feedback' };

    function _feedbackRelayConfigured() {
        return /^https:\/\//.test(_FEEDBACK_ENDPOINT);
    }

    function _buildFeedbackIssueUrl(type, name, message) {
        const typeName = _FEEDBACK_TYPE_NAMES[type] || _FEEDBACK_TYPE_NAMES.general;
        const title = `[${typeName}] ${message.slice(0, 72)}${message.length > 72 ? '...' : ''}`;
        const body = [
            `**Type:** ${typeName}`,
            ...(name ? [`**From:** ${name}`] : []),
            '',
            '**Message:**',
            message,
            '',
            '---',
            '*Submitted from the NilPDF in-app feedback form*',
        ].join('\n');
        const params = new URLSearchParams({ title, body });
        const label = _FEEDBACK_LABELS[type];
        if (label) params.set('labels', label);
        return `${_FEEDBACK_ISSUE_URL}?${params.toString()}`;
    }

    function openFeedback() {
        document.getElementById('feedback-form-state').hidden    = false;
        document.getElementById('feedback-success-state').hidden = true;
        document.getElementById('feedback-github-state').hidden  = true;
        document.getElementById('feedback-form').reset();
        // Say which path this submission takes before the visitor types anything,
        // since the GitHub fallback produces a public issue.
        const viaGitHub = !_feedbackRelayConfigured();
        document.getElementById('feedback-subtitle').textContent = viaGitHub
            ? 'This opens a public GitHub issue for you to review and submit.'
            : 'Your thoughts help us improve NilPDF.';
        document.getElementById('feedback-submit-text').textContent = viaGitHub
            ? 'Continue on GitHub'
            : 'Send Feedback';
        const errDiv = document.getElementById('feedback-error');
        errDiv.hidden = true;
        errDiv.textContent = '';
        document.getElementById('feedback-submit').disabled = false;
        document.getElementById('feedback-submit-text').hidden    = false;
        // The spinner is an <svg>, and SVG elements have no `hidden` property, so
        // assigning .hidden is a silent no-op. Toggle the attribute instead.
        document.getElementById('feedback-submit-spinner').toggleAttribute('hidden', true);
        document.getElementById('feedback-modal').hidden = false;
        document.body.style.overflow = 'hidden';
        requestAnimationFrame(() => document.getElementById('feedback-type').focus());
    }

    function closeFeedback() {
        document.getElementById('feedback-modal').hidden = true;
        document.body.style.overflow = '';
    }

    async function submitFeedback(e) {
        e.preventDefault();
        const message = document.getElementById('feedback-message').value.trim();
        if (!message) return;

        // Relay not configured (unstamped build): fall back to a pre-filled GitHub issue.
        //
        // Test the *shape* of the value rather than comparing it to the placeholder
        // literal. The deploy step does a plain replace-all, so a second copy of the
        // placeholder written here would be rewritten to the stamped URL too, turning
        // this into `endpoint === endpoint` and disabling the form on the live site
        // precisely when it is configured correctly. That is not hypothetical: the
        // previous token-based version of this guard had exactly that bug, and the
        // production feedback form silently reported itself unavailable for every
        // submission. An unstamped build still holds the placeholder, which is not a
        // URL, so this check catches it.
        if (!/^https:\/\//.test(_FEEDBACK_ENDPOINT)) {
            const url = _buildFeedbackIssueUrl(
                document.getElementById('feedback-type').value,
                document.getElementById('feedback-name').value.trim(),
                message,
            );
            // Opened synchronously, inside the submit gesture, so popup blockers
            // allow it. The link in the next state covers the case where it is
            // blocked anyway.
            window.open(url, '_blank', 'noopener');
            document.getElementById('feedback-github-link').href = url;
            document.getElementById('feedback-form-state').hidden   = true;
            document.getElementById('feedback-github-state').hidden = false;
            return;
        }

        const submitBtn     = document.getElementById('feedback-submit');
        const submitText    = document.getElementById('feedback-submit-text');
        const submitSpinner = document.getElementById('feedback-submit-spinner');
        const errDiv        = document.getElementById('feedback-error');

        submitBtn.disabled   = true;
        submitText.hidden    = true;
        submitSpinner.toggleAttribute('hidden', false);
        errDiv.hidden        = true;

        const type = document.getElementById('feedback-type').value;
        const name = document.getElementById('feedback-name').value.trim();

        // Send the raw fields only. The Worker validates and truncates them, then
        // composes the issue title and body, so the client can't dictate either.
        try {
            const res = await fetch(_FEEDBACK_ENDPOINT, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ type, name, message }),
            });

            if (!res.ok) {
                throw new Error(`Feedback relay returned ${res.status}`);
            }
            document.getElementById('feedback-form-state').hidden    = true;
            document.getElementById('feedback-success-state').hidden = false;
        } catch (_err) {
            errDiv.textContent = 'Could not send feedback, please try again in a moment.';
            errDiv.hidden      = false;
            submitBtn.disabled   = false;
            submitText.hidden    = false;
            submitSpinner.toggleAttribute('hidden', true);
        }
    }

    document.addEventListener('click', function (e) {
        if (e.target.id === 'feedback-modal') closeFeedback();
    });

