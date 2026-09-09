import {
    profiles, workflows, schedules, scriptStatusCache,
    profileHistoryPage, workflowHistoryPage,
    profileHistoryData, workflowHistoryData,
    profileHistoryFilters, workflowHistoryFilters,
    auditPage, auditData, auditAction, auditEntity,
    auditName, auditSince, auditUntil,
    logData, logOffset,
    tags, TRASH_GROUP,
} from './state.js';

async function api(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    try {
        return await res.json();
    } catch (err) {
        // Non-JSON bodies (server error pages) or empty responses fail loudly
        // instead of surfacing as undefined data downstream.
        throw new Error(`${method} ${path} failed (${res.status})`);
    }
}

// Older data kept one tag id in `group`; new data keeps a `tags` array.
// On load, fold the legacy value into the array and drop ids whose tag no
// longer exists, so items deleted with old versions don't linger as
// unknown tags. `group` itself now only marks trash ('__trash__').
function normalizeTags(item) {
    const known = new Set(tags.value.map(t => t.id));
    const ids = [];
    for (const id of [...(item.tags || []), item.group || '']) {
        if (id && id !== TRASH_GROUP && known.has(id) && !ids.includes(id)) ids.push(id);
    }
    return { ...item, tags: ids };
}

export async function loadProfiles() {
    profiles.value = (await api('GET', '/api/profiles')).map(normalizeTags);
}

export async function loadWorkflows() {
    workflows.value = (await api('GET', '/api/workflows')).map(normalizeTags);
}

export async function loadSchedules() {
    schedules.value = await api('GET', '/api/schedules');
}

export async function saveSchedule(data) {
    return api('POST', '/api/schedules', data);
}

export async function toggleSchedule(id) {
    return api('POST', `/api/schedules/${id}/toggle`);
}

export async function runScheduleNow(id) {
    return api('POST', `/api/schedules/${id}/run_now`);
}

export async function deleteSchedule(id) {
    return api('DELETE', '/api/schedules/' + id);
}

export async function duplicateSchedule(id) {
    return api('POST', `/api/schedules/${id}/duplicate`);
}

export async function previewCron(cron) {
    return api('GET', '/api/schedules/preview?cron=' + encodeURIComponent(cron));
}

// Both checks always hit the server and refresh the cache: a cached
// "missing" must not pin the badge after the script reappears on disk.
export async function checkScriptExists(path) {
    const res = await api('GET', '/api/script_exists?path=' + encodeURIComponent(path));
    scriptStatusCache.value = { ...scriptStatusCache.value, [path]: res.exists };
    return res.exists;
}

export async function checkAllScripts() {
    const paths = profiles.value.filter(p => p.script_path).map(p => p.script_path);
    const results = await Promise.all(paths.map(async path => {
        const res = await api('GET', '/api/script_exists?path=' + encodeURIComponent(path));
        return [path, res.exists];
    }));
    scriptStatusCache.value = { ...scriptStatusCache.value, ...Object.fromEntries(results) };
}

export async function saveProfile(data) {
    return api('POST', '/api/profiles', data);
}

export async function deleteProfile(id) {
    return api('DELETE', '/api/profiles/' + id);
}

export async function restoreProfile(id) {
    return api('POST', `/api/profiles/${id}/restore`);
}

export async function permanentDeleteProfile(id) {
    return api('DELETE', `/api/profiles/${id}/permanent`);
}

export async function duplicateProfile(id) {
    return api('POST', `/api/profiles/${id}/duplicate`);
}

export async function saveProfileOrder(ids) {
    return api('POST', '/api/profiles/reorder', { order: ids });
}

export async function saveWorkflow(data) {
    return api('POST', '/api/workflows', data);
}

export async function deleteWorkflow(id) {
    return api('DELETE', '/api/workflows/' + id);
}

export async function restoreWorkflow(id) {
    return api('POST', `/api/workflows/${id}/restore`);
}

export async function permanentDeleteWorkflow(id) {
    return api('DELETE', `/api/workflows/${id}/permanent`);
}

export async function duplicateWorkflow(id) {
    return api('POST', `/api/workflows/${id}/duplicate`);
}

export async function saveWorkflowOrder(ids) {
    return api('POST', '/api/workflows/reorder', { order: ids });
}

export async function runProfile(id, argValues) {
    return api('POST', '/api/run/profile', { profile_id: id, arg_values: argValues });
}

export async function runWorkflow(id) {
    return api('POST', '/api/run/workflow', { workflow_id: id });
}

export async function pollRun(runId) {
    return api('GET', '/api/runs/' + runId);
}

export async function cancelRun(runId) {
    return api('POST', '/api/runs/' + runId + '/cancel');
}

export async function fetchHistoryRun(runId, runType) {
    const url = runType ? `/api/history/${runId}?type=${runType}` : `/api/history/${runId}`;
    return api('GET', url);
}

// A picked day ('YYYY-MM-DD') becomes an epoch range covering the whole
// local day. No date picked ('') means no filter.
function dayStartEpoch(day) {
    if (!day) return null;
    const epoch = Date.parse(day + 'T00:00:00') / 1000;
    return Number.isFinite(epoch) ? epoch : null;
}

function dayEndEpoch(day) {
    if (!day) return null;
    const epoch = Date.parse(day + 'T23:59:59') / 1000;
    return Number.isFinite(epoch) ? epoch : null;
}

function addHistoryFilterParams(params, f) {
    if (f.name) params.set('name', f.name);
    if (f.status) params.set('status', f.status);
    const since = dayStartEpoch(f.since);
    const until = dayEndEpoch(f.until);
    if (since !== null) params.set('since', since);
    if (until !== null) params.set('until', until);
}

export async function loadProfileHistory() {
    const params = new URLSearchParams({ page: profileHistoryPage.value, per_page: 15, type: 'profile' });
    addHistoryFilterParams(params, profileHistoryFilters.value);
    const data = await api('GET', '/api/history?' + params.toString());
    profileHistoryData.value = data;
}

export async function loadWorkflowHistory() {
    const params = new URLSearchParams({ page: workflowHistoryPage.value, per_page: 15, type: 'workflow' });
    addHistoryFilterParams(params, workflowHistoryFilters.value);
    const data = await api('GET', '/api/history?' + params.toString());
    workflowHistoryData.value = data;
}

export async function deleteHistoryEntry(runId) {
    await api('DELETE', '/api/history/' + runId);
    await loadProfileHistory();
    await loadWorkflowHistory();
}

export async function deleteHistoryEntries(ids) {
    await api('POST', '/api/history/bulk', { ids });
    await loadProfileHistory();
    await loadWorkflowHistory();
}

export async function openNativeFileDialog() {
    return api('GET', '/api/filedialog');
}

export async function loadAudit() {
    const params = new URLSearchParams({ page: auditPage.value, per_page: 20 });
    if (auditAction.value) params.set('action', auditAction.value);
    if (auditEntity.value) params.set('entity', auditEntity.value);
    if (auditName.value) params.set('name', auditName.value);
    const since = dayStartEpoch(auditSince.value);
    const until = dayEndEpoch(auditUntil.value);
    if (since !== null) params.set('since', since);
    if (until !== null) params.set('until', until);
    auditData.value = await api('GET', '/api/audit?' + params.toString());
}

export async function fetchAuditDetail(entryId) {
    return api('GET', '/api/audit/' + entryId);
}

const LOG_TAIL = 500;
const LOG_BUFFER = 2000;

export async function loadLogs() {
    const data = await api('GET', '/api/logs?lines=' + LOG_TAIL);
    logData.value = data.entries;
    logOffset.value = data.next_offset;
}

export async function pollLogs() {
    const data = await api('GET', '/api/logs?after=' + logOffset.value);
    if (data.reset) {
        logData.value = data.entries;
    } else if (data.entries.length) {
        logData.value = [...logData.value, ...data.entries].slice(-LOG_BUFFER);
    }
    logOffset.value = data.next_offset;
}
