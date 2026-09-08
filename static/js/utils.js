export function esc(s) {
    return s ? String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : '';
}

export function formatTime(ts) {
    return ts ? new Date(ts * 1000).toLocaleTimeString() : '-';
}

export function formatDateTime(ts) {
    return ts ? new Date(ts * 1000).toLocaleString() : '-';
}

export function formatRelative(ts) {
    if (!ts) return '';
    const diff = ts - Date.now() / 1000;
    if (diff <= 0) return 'now';
    const totalMinutes = Math.round(diff / 60);
    if (totalMinutes < 1) return 'in <1m';
    if (totalMinutes < 60) return `in ${totalMinutes}m`;
    const h = Math.floor(totalMinutes / 60);
    if (h < 24) return `in ${h}h ${totalMinutes % 60}m`;
    const d = Math.floor(h / 24);
    return `in ${d}d ${h % 24}h`;
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
        : status === 'cancelled' ? 'text-amber-600 dark:text-amber-400'
        : 'text-sky-600 dark:text-sky-400';
}

export function colorizeLine(line) {
    if (line.startsWith('[FAIL') || line.startsWith('[ABORT') || line.startsWith('ERROR'))
        return 'text-red-400';
    if (line.startsWith('[DONE') || line.startsWith('[SKIP'))
        return 'text-green-400';
    if (line.startsWith('[CANCEL'))
        return 'text-amber-400';
    if (line.startsWith('[RUN') || line.startsWith('='))
        return 'text-sky-400';
    return '';
}
