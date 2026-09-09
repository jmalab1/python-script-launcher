import { html } from '../../vendor/standalone-preact.esm.js';
import { useState, useEffect, useRef } from '../../vendor/standalone-preact.esm.js';

// Shared filter controls for the History and Audit panels.
// Each control updates a filter value in state.js, resets the panel's page
// to 1, and triggers a reload through the onLoad callback.

const CONTROL_CLASS = 'text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700/60 rounded-lg px-2 py-1.5 text-gray-700 dark:text-gray-300 placeholder-gray-400';

export function hasActiveFilters(...values) {
    return values.some(v => !!v);
}

// Text input that waits for the user to stop typing (300ms) before calling
// onCommit, so we don't fire a server request on every keystroke.
export function SearchInput({ value, onCommit, placeholder }) {
    const [text, setText] = useState(value);
    const committed = useRef(value);
    const timer = useRef(null);

    // If the value changes elsewhere (e.g. the Clear button), follow it.
    // The guard keeps our own commits from clobbering text mid-typing,
    // and drops any pending commit that would override the new value.
    useEffect(() => {
        if (value !== committed.current) {
            committed.current = value;
            setText(value);
            clearTimeout(timer.current);
        }
    }, [value]);

    return html`
        <input type="search" value=${text}
            placeholder=${placeholder || 'Search by name…'}
            onInput=${(ev) => {
                const next = ev.target.value;
                setText(next);
                clearTimeout(timer.current);
                timer.current = setTimeout(() => {
                    committed.current = next;
                    onCommit(next);
                }, 300);
            }}
            class=${CONTROL_CLASS + ' w-44'} />
    `;
}

// From/To date pickers. Both dates are inclusive days; api.js converts
// them to epoch seconds before sending them to the server.
export function DateInputs({ since, until, onSince, onUntil }) {
    return html`
        <div class="flex items-center gap-1.5">
            <input type="date" value=${since} onChange=${(ev) => onSince(ev.target.value)}
                title="From date (inclusive)" class=${CONTROL_CLASS} />
            <span class="text-xs text-gray-400">–</span>
            <input type="date" value=${until} onChange=${(ev) => onUntil(ev.target.value)}
                title="To date (inclusive)" class=${CONTROL_CLASS} />
        </div>
    `;
}

// Filter bar for a run-history table. `filters` is a signal holding
// { name, status, since, until } from state.js.
export function HistoryFilters({ filters, pageSignal, onLoad }) {
    const f = filters.value;

    function update(patch) {
        filters.value = { ...filters.value, ...patch };
        pageSignal.value = 1;
        onLoad();
    }

    const active = hasActiveFilters(f.name, f.status, f.since, f.until);

    return html`
        <div class="flex flex-wrap items-center gap-2">
            <${SearchInput} value=${f.name} onCommit=${(name) => update({ name })} />
            <select value=${f.status} onChange=${(ev) => update({ status: ev.target.value })}
                class=${CONTROL_CLASS}>
                <option value="">All statuses</option>
                <option value="running">Running</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="cancelled">Cancelled</option>
            </select>
            <${DateInputs} since=${f.since} until=${f.until}
                onSince=${(since) => update({ since })}
                onUntil=${(until) => update({ until })} />
            ${active ? html`
                <button onClick=${() => update({ name: '', status: '', since: '', until: '' })}
                    class="text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 px-2 py-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700/50 transition">
                    Clear
                </button>
            ` : ''}
        </div>
    `;
}
