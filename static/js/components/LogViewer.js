import { html } from '../../vendor/standalone-preact.esm.js';
import { useState, useEffect, useRef } from '../../vendor/standalone-preact.esm.js';

const LEVEL_CLASS = {
    CRITICAL: 'text-red-400',
    ERROR: 'text-red-400',
    WARNING: 'text-amber-400',
    INFO: 'text-gray-300',
    DEBUG: 'text-gray-500',
};

function lineLevel(line) {
    const m = line.match(/\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\]/);
    return m ? m[1] : null;
}

function lineClass(line) {
    const level = lineLevel(line);
    return level ? (LEVEL_CLASS[level] || '') : 'text-gray-400';
}

export function LogViewer({ data }) {
    const [follow, setFollow] = useState(true);
    const [levelFilter, setLevelFilter] = useState('');
    const [search, setSearch] = useState('');
    const bodyRef = useRef(null);

    useEffect(() => {
        if (follow && bodyRef.current) {
            bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
        }
    }, [data, follow]);

    function onScroll() {
        const el = bodyRef.current;
        if (!el) return;
        const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
        if (atBottom !== follow) setFollow(atBottom);
    }

    const query = search.trim().toLowerCase();
    const filtered = data.filter(line => {
        if (levelFilter) {
            const level = lineLevel(line);
            if (level !== levelFilter) return false;
        }
        if (query && !line.toLowerCase().includes(query)) return false;
        return true;
    });

    return html`
        <div class="flex flex-col h-full min-h-0">
            <div class="flex flex-col sm:flex-row sm:items-center gap-2 mb-3 shrink-0">
                <select value=${levelFilter}
                    onChange=${(ev) => setLevelFilter(ev.target.value)}
                    class="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700/60 rounded-lg px-2 py-1.5 text-gray-700 dark:text-gray-300">
                    <option value="">All levels</option>
                    <option value="INFO">Info</option>
                    <option value="WARNING">Warning</option>
                    <option value="ERROR">Error</option>
                    <option value="DEBUG">Debug</option>
                </select>
                <input type="text" value=${search}
                    onInput=${(ev) => setSearch(ev.target.value)}
                    placeholder="Filter lines..."
                    class="flex-1 min-w-0 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700/60 rounded-lg px-2.5 py-1.5 text-gray-700 dark:text-gray-300 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-violet-500" />
                <button onClick=${() => setFollow(!follow)}
                    class="text-xs font-medium px-2.5 py-1.5 rounded-lg border transition inline-flex items-center gap-1.5 ${follow
                        ? 'bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20 text-green-700 dark:text-green-400'
                        : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700/60 text-gray-500 dark:text-gray-400'}">
                    <span class="w-1.5 h-1.5 rounded-full ${follow ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}"></span>
                    ${follow ? 'Following' : 'Paused'}
                </button>
            </div>
            <div ref=${bodyRef} onScroll=${onScroll}
                class="flex-1 min-h-0 bg-gray-950 rounded-xl p-4 font-mono text-xs leading-relaxed overflow-y-auto whitespace-pre-wrap break-all">
                ${filtered.length ? filtered.map(line => html`
                    <div class=${lineClass(line)}>${line || '\u00a0'}</div>
                `) : html`<div class="text-gray-500">No log lines match the current filters.</div>`}
            </div>
            <div class="shrink-0 pt-2 text-[11px] text-gray-500 dark:text-gray-400">
                Showing ${filtered.length} of ${data.length} lines ${follow ? '' : '— follow paused'}
            </div>
        </div>
    `;
}
