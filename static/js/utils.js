export function esc(s) {
    return s ? String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') : '';
}

export function formatTime(ts) {
    return ts ? new Date(ts * 1000).toLocaleTimeString() : '-';
}

export function formatDuration(seconds) {
    if (seconds == null || seconds < 0) return '-';
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m ${String(s).padStart(2, '0')}s`;
}

export function colorizeStatus(status) {
    return status === 'completed' ? 'text-green-600 dark:text-green-400'
        : status === 'failed' ? 'text-red-600 dark:text-red-400'
        : 'text-sky-600 dark:text-sky-400';
}

export function colorizeLine(line) {
    if (line.startsWith('[FAIL') || line.startsWith('[ABORT') || line.startsWith('ERROR'))
        return 'text-red-400';
    if (line.startsWith('[DONE') || line.startsWith('[SKIP'))
        return 'text-green-400';
    if (line.startsWith('[RUN') || line.startsWith('='))
        return 'text-sky-400';
    return '';
}
