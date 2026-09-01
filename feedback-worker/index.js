/**
 * NilPDF Feedback Worker — Cloudflare Workers
 *
 * Receives a POST from the NilPDF in-app feedback form and creates a GitHub
 * issue on the kdigitalsystems/nilpdf repository.
 *
 * This Worker exists so the GitHub credential lives server-side. The site is a
 * static page on GitHub Pages: anything the browser can read, every visitor can
 * read, so the token cannot be shipped with the page. The browser posts
 * {type, name, message} here; only this Worker ever sees the token.
 *
 * ── Setup ────────────────────────────────────────────────────────────────────
 * 1. Install Wrangler:  npm install -g wrangler
 * 2. Login:             wrangler login
 * 3. Deploy:            wrangler deploy   (from this directory)
 * 4. Set the token:
 *      wrangler secret put GITHUB_TOKEN
 *
 *    Prefer a fine-grained PAT scoped to this single repository with
 *    Issues: Read and write — nothing else. A classic `public_repo` token also
 *    works but is a far worse trade: it grants write access to every public
 *    repository on the account, so a Worker compromise would reach all of them.
 * 5. Point the site at this Worker. Set the deployed URL
 *      https://nilpdf-feedback.<your-account>.workers.dev
 *    as the FEEDBACK_ENDPOINT repository *variable* (Settings → Secrets and
 *    variables → Actions → Variables). The deploy job stamps it over the
 *    __FEEDBACK_ENDPOINT__ placeholder in assets/js/app.js. It is a variable
 *    rather than a secret because the URL is public by nature — it ends up in
 *    the shipped JavaScript either way.
 *
 *    With the variable unset the placeholder survives and the in-app form shows
 *    an "unavailable" message instead of failing silently.
 * ─────────────────────────────────────────────────────────────────────────────
 *
 * Environment variables (set via `wrangler secret put` or the dashboard):
 *   GITHUB_TOKEN  — GitHub PAT; fine-grained with Issues: write on this repo
 *
 * Constants (edit below or override via wrangler.toml [vars]):
 *   GITHUB_REPO   — "owner/repo" string for the target repository
 */

const GITHUB_REPO = 'kdigitalsystems/nilpdf';

// Origins allowed to call this Worker. Add your custom domain here if needed.
const ALLOWED_ORIGINS = [
    'https://nilpdf.com',
    'https://kdigitalsystems.github.io',
    'http://localhost:8080',
    'http://127.0.0.1:8080',
    'http://localhost:3000',
    // Port used by dev_server.py, the documented local dev server.
    'http://localhost:8123',
    'http://127.0.0.1:8123',
];

export default {
    async fetch(request, env) {
        const origin = request.headers.get('Origin') || '';
        const corsOrigin = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];

        const cors = {
            'Access-Control-Allow-Origin': corsOrigin,
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Vary': 'Origin',
        };

        // CORS preflight
        if (request.method === 'OPTIONS') {
            return new Response(null, { status: 204, headers: cors });
        }

        if (request.method !== 'POST') {
            return json({ error: 'Method not allowed' }, 405, cors);
        }

        // Parse body
        let body;
        try {
            body = await request.json();
        } catch {
            return json({ error: 'Invalid JSON body' }, 400, cors);
        }

        const { type = 'general', name = '', message = '' } = body;

        if (!message || !message.trim()) {
            return json({ error: 'message is required' }, 400, cors);
        }

        // Sanitise / truncate inputs
        const safeType    = ['bug', 'feature', 'general'].includes(type) ? type : 'general';
        const safeName    = String(name).slice(0, 100).trim();
        const safeMessage = String(message).slice(0, 2000).trim();

        const typeLabels = {
            bug:     'Bug report',
            feature: 'Feature request',
            general: 'General feedback',
        };
        const typeLabel = typeLabels[safeType];

        // Build issue title (keep it short)
        const titleSuffix = safeMessage.slice(0, 72);
        const issueTitle  = `[${typeLabel}] ${titleSuffix}${safeMessage.length > 72 ? '…' : ''}`;

        const issueBody = [
            `**Type:** ${typeLabel}`,
            safeName ? `**From:** ${safeName}` : '**From:** Anonymous',
            '',
            '**Message:**',
            safeMessage,
            '',
            '---',
            '*Submitted via NilPDF in-app feedback form*',
            'cc @saqibkh',
        ].join('\n');

        // Create GitHub issue
        const ghRes = await fetch(`https://api.github.com/repos/${GITHUB_REPO}/issues`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
                'Accept':        'application/vnd.github.v3+json',
                'Content-Type':  'application/json',
                'User-Agent':    'nilpdf-feedback-worker/1.0',
            },
            body: JSON.stringify({
                title:  issueTitle,
                body:   issueBody,
                labels: ['feedback'],
            }),
        });

        if (!ghRes.ok) {
            const errText = await ghRes.text().catch(() => '');
            console.error('GitHub API error', ghRes.status, errText);
            return json({ error: 'Failed to create issue' }, 502, cors);
        }

        const issue = await ghRes.json();
        return json({ issue_url: issue.html_url, issue_number: issue.number }, 200, cors);
    },
};

function json(data, status, extraHeaders = {}) {
    return new Response(JSON.stringify(data), {
        status,
        headers: { 'Content-Type': 'application/json', ...extraHeaders },
    });
}
