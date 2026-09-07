import { html } from '../../vendor/standalone-preact.esm.js';
import { useState, useEffect, useRef } from '../../vendor/standalone-preact.esm.js';
import { esc, colorizeLine } from '../utils.js';
import { pollRun, fetchHistoryRun } from '../api.js';

export function RunModal({ isOpen, onClose, runId, title, runType }) {
    const [output, setOutput] = useState([]);
    const [status, setStatus] = useState('starting');
    const [tabs, setTabs] = useState([]);
    const [activeTab, setActiveTab] = useState('workflow');
    const [currentStep, setCurrentStep] = useState('');
    const timerRef = useRef(null);
    const outputRef = useRef(null);
    const activeTabRef = useRef('workflow');
    activeTabRef.current = activeTab;

    function linesFor(data) {
        const stepData = data.steps || {};
        const tab = activeTabRef.current;
        let lines;
        if (tab === 'workflow' || !Object.keys(stepData).length) {
            lines = (data.workflow_log?.length ? data.workflow_log : null) || data.output || [];
        } else {
            lines = stepData[tab]?.output || [];
        }
        if (!lines.length && data.output_preview) {
            lines = data.output_preview.split('\n');
        }
        return lines;
    }

    function renderLines(lines) {
        if (!lines || !lines.length) return html`<div class="text-gray-500">No output available for this run.</div>`;
        return lines.map(l => {
            const s = typeof l === 'string' ? l : String(l);
            const cls = colorizeLine(s);
            return cls ? html`<div class=${cls}>${esc(s)}</div>` : esc(s);
        });
    }

    function updateTabs(stepData) {
        const stepNames = Object.keys(stepData);
        if (stepNames.length > 0) {
            setTabs(stepNames.map(name => ({
                name,
                status: stepData[name].status,
            })));
        } else {
            setTabs([]);
        }
    }

    async function loadFromHistory(rid, rType) {
        const hist = await fetchHistoryRun(rid, rType);
        if (hist.error) {
            setOutput(['Run data not found.']);
            return;
        }
        setStatus(hist.status || 'completed');
        updateTabs(hist.steps || {});
        setOutput(linesFor(hist));
    }

    async function pollActiveRun(rid) {
        if (timerRef.current) { clearInterval(timerRef.current); }
        timerRef.current = setInterval(async () => {
            const data = await pollRun(rid);
            if (data.error) {
                clearInterval(timerRef.current);
                timerRef.current = null;
                await loadFromHistory(rid, runType);
                return;
            }
            setStatus(data.status || 'running');
            setCurrentStep(data.current_step || '');
            updateTabs(data.steps || {});
            setOutput(linesFor(data));
            if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;

            if (data.status === 'completed' || data.status === 'failed') {
                clearInterval(timerRef.current);
                timerRef.current = null;
            }
        }, 500);
    }

    useEffect(() => {
        if (!isOpen || !runId) return;
        setOutput([]);
        setStatus('starting');
        setTabs([]);
        setActiveTab('workflow');
        activeTabRef.current = 'workflow';
        setCurrentStep('');

        if (runType) {
            loadFromHistory(runId, runType);
        } else {
            pollActiveRun(runId);
        }

        return () => {
            if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
        };
    }, [isOpen, runId]);

    useEffect(() => {
        if (!isOpen || !runId) return;
        if (runType) {
            loadFromHistory(runId, runType);
        }
    }, [activeTab]);

    if (!isOpen) return null;

    const statusColors = {
        running: 'bg-sky-50 dark:bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-200 dark:border-sky-500/20',
        completed: 'bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/20',
        failed: 'bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20',
        starting: 'bg-purple-50 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-200 dark:border-purple-500/20',
    };
    const dotColors = {
        running: 'bg-sky-400', completed: 'bg-green-400', failed: 'bg-red-400', starting: 'bg-purple-400',
    };
    const statusLabels = { completed: 'Completed', failed: 'Failed', running: 'Running...' };

    return html`
        <div class="fixed inset-0 z-50">
            <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick=${onClose}></div>
            <div class="relative flex items-center justify-center min-h-full p-4">
                <div class="relative bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-5xl max-h-[85vh] flex flex-col border border-gray-200 dark:border-gray-700/60">
                    <div class="shrink-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700/60 px-6 py-4 rounded-t-2xl">
                        <div class="flex items-center justify-between">
                            <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100">${title || 'Run Output'}</h2>
                            <button onClick=${onClose} class="p-1 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/></svg>
                            </button>
                        </div>
                        <div class="mt-3 flex items-center gap-3">
                            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${statusColors[status] || statusColors.starting}">
                                <span class="w-1.5 h-1.5 rounded-full ${dotColors[status] || dotColors.starting} ${status === 'running' ? 'animate-pulse' : ''}"></span>
                                <span>${statusLabels[status] || 'Starting...'}</span>
                            </span>
                            ${currentStep ? html`<span class="text-xs text-gray-500 dark:text-gray-400">Running: ${esc(currentStep)}</span>` : ''}
                        </div>
                    </div>
                    ${tabs.length ? html`
                        <div class="shrink-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700/60 px-6">
                            <div class="flex gap-1 -mb-px overflow-x-auto">
                                <button onClick=${() => setActiveTab('workflow')}
                                    class="px-3 py-2 text-xs font-medium border-b-2 transition ${activeTab === 'workflow' ? 'border-violet-500 text-violet-600 dark:text-violet-400' : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}">Workflow</button>
                                ${tabs.map(t => {
                                    const dot = t.status === 'completed' ? 'bg-green-400' : t.status === 'failed' ? 'bg-red-400' : t.status === 'running' ? 'bg-sky-400 animate-pulse' : 'bg-gray-400';
                                    return html`
                                        <button onClick=${() => setActiveTab(t.name)}
                                            class="px-3 py-2 text-xs font-medium border-b-2 transition flex items-center gap-1.5 ${activeTab === t.name ? 'border-violet-500 text-violet-600 dark:text-violet-400' : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}">
                                            <span class="w-1.5 h-1.5 rounded-full ${dot}"></span>${esc(t.name)}
                                        </button>`;
                                })}
                            </div>
                        </div>
                    ` : ''}
                    <div class="flex-1 overflow-hidden p-4">
                        <div ref=${outputRef} class="h-full bg-gray-950 rounded-xl p-4 font-mono text-xs leading-relaxed overflow-y-auto text-gray-300 whitespace-pre-wrap break-all">
                            ${renderLines(output)}
                        </div>
                    </div>
                    <div class="shrink-0 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700/60 px-6 py-3 rounded-b-2xl flex justify-end">
                        <button onClick=${onClose} class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition">Close</button>
                    </div>
                </div>
            </div>
        </div>
    `;
}
