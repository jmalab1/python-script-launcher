// The fixed palette users can pick tag colors from. Tailwind's play CDN
// scans the DOM for class names at runtime, so building the class strings
// from the color name here works — any palette class only reaches the DOM
// when a tag actually uses that color.
const HEXES = {
    amber: '#f59e0b',
    orange: '#f97316',
    rose: '#f43f5e',
    fuchsia: '#d946ef',
    violet: '#8b5cf6',
    blue: '#3b82f6',
    sky: '#0ea5e9',
    teal: '#14b8a6',
    emerald: '#10b981',
    lime: '#84cc16',
};

export const TAG_COLORS = Object.entries(HEXES).map(([id, hex]) => ({
    id,
    hex,
    // Chip/pill styling: soft background, readable text, subtle border.
    chip: `bg-${id}-50 dark:bg-${id}-500/10 text-${id}-700 dark:text-${id}-400 border-${id}-200 dark:border-${id}-500/20`,
    // Extra emphasis for a selected chip/pill.
    ring: `ring-${id}-400/60 dark:ring-${id}-400/40`,
}));

// Tags created before colors existed (or with an unknown color) fall back
// to this entry, so they always render with the amber look they had before.
export const DEFAULT_TAG_COLOR = 'amber';

export function tagColor(tag) {
    return TAG_COLORS.find(c => c.id === (tag && tag.color)) || TAG_COLORS[0];
}
