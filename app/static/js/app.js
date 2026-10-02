/* The static Gen Legend frontend: slab mounts, the hash router, and the
 * JSON API (app/api.py). slab owns presentation — the shell, footer, forge,
 * and sheet web components solve layout and paint frames from data they are
 * given — and this file is the whole seam: choices go in as params, signals
 * come out as API calls. Nothing here knows about Shiny; the legacy app is
 * only still reachable for parked surfaces and /character/ link redirects.
 *
 * Signal map (the compiled elements list them in their `signals` export):
 *   gl-shell:  nav_home nav_character nav_npc nav_npclist nav_dm
 *   gl-footer: open_about open_wiki open_julio
 *   gl-forge:  pick filter generate
 *   gl-sheet:  open_species open_background open_class open_specialization
 *              pick level_down level_up generate share
 *
 * Rebuild the components with `make slab`; bump SLAB_VERSION then so
 * browsers re-import the modules.
 */
(() => {
    'use strict';

    const SLAB_VERSION = '8';
    const FONTS = [
        ['Cinzel', '/static/fonts/slab-cinzel-700.ttf'],
        ['Eagle Lake', '/static/fonts/slab-eagle-lake-400.ttf'],
    ];
    /* Forge column param ← /api/choices list key. */
    const FORGE_LISTS = {
        species: 'species',
        classes: 'guilds',
        backgrounds: 'backgrounds',
    };
    /* Forge column param ← the generate body field it feeds. */
    const FORGE_BODY = {
        species: 'species',
        classes: 'char_class',
        backgrounds: 'background',
    };
    const HINT = 'type to narrow every option';
    const SHEET_FIELDS = {
        open_species: 'species',
        open_background: 'background',
        open_class: 'char_class',
        open_specialization: 'specialization',
    };
    const LINKS = {
        open_about: 'https://github.com/JulTob/DnD#readme',
        open_wiki: 'https://github.com/JulTob/DnD/wiki',
        open_julio: 'https://github.com/JulTob',
    };
    /* Parked first-publish chrome: these still answer the legacy Shiny
     * fallthrough routes; nothing publishes them while data-player-only. */
    const PARKED_ROUTES = {
        nav_npc: '/npc',
        nav_npclist: '/npclist',
        nav_dm: '/dm',
    };
    const PATH_NULL_MARKERS = ['', '_', 'random', 'none', 'null'];

    const state = {
        lists: null,        // /api/choices: {species, guilds, backgrounds, specializations}
        specCache: {},      // guild → choices from /api/specializations
        forgeRows: null,    // forge param → [{key, name, picked}]
        query: '',
        shell: null,
        forge: null,
        sheet: null,
        parameters: null,   // last generated canonical parameters
        hash: '',           // that character's canonical hash ('' = none)
        pending: null,      // sheet selectors before the next generate
        level: 1,
        busy: false,
        openField: null,    // 'species' | 'background' | 'char_class' | 'specialization'
        shareTimer: null,
    };

    /* ---- small helpers ---------------------------------------------- */

    function loader(show) {
        const summon = window.summonLoader;
        if (!summon) return;
        if (show) summon.show();
        else summon.hide();
    }

    function showView(name) {
        document.getElementById('view-home').hidden = name !== 'home';
        document.getElementById('view-sheet').hidden = name !== 'sheet';
    }

    function showHome() {
        showView('home');
    }

    function showSheet() {
        showView('sheet');
    }

    function sheetError(message) {
        state.sheet.error = message;
        state.sheet.error_shown = true;
    }

    /* ---- /api/choices ------------------------------------------------ */

    async function loadChoices() {
        const response = await fetch('/api/choices');
        if (!response.ok) throw new Error('HTTP ' + response.status);
        state.lists = await response.json();
    }

    function forgeRowsInit() {
        state.forgeRows = {};
        for (const param of Object.keys(FORGE_LISTS)) {
            const names = state.lists[FORGE_LISTS[param]] || [];
            state.forgeRows[param] = names.map((name) => ({
                key: param + '|' + name,
                name: name,
                picked: name === 'Random',
            }));
        }
    }

    async function specializationsFor(guild) {
        const key = guild || 'Random';
        if (!state.specCache[key]) {
            const response = await fetch(
                '/api/specializations?guild=' + encodeURIComponent(key)
            );
            const data = await response.json();
            if (!response.ok || data.ok === false) {
                throw new Error(data.error || 'HTTP ' + response.status);
            }
            state.specCache[key] = data.choices;
        }
        return state.specCache[key];
    }

    /* ---- the forge face (app/slab/forge.slab) ------------------------ */

    function forgePicked(param) {
        const hit = (state.forgeRows[param] || []).find((row) => row.picked);
        return hit ? hit.name : 'Random';
    }

    function paintForge() {
        const el = state.forge;
        if (!el || !state.forgeRows) return;
        const query = state.query.toLowerCase();
        for (const param of Object.keys(FORGE_LISTS)) {
            const all = state.forgeRows[param];
            const shown = query
                ? all.filter((row) => row.picked
                    || row.name.toLowerCase().includes(query))
                : all;
            el[param] = shown.map((row) => ({
                key: row.key,
                name: row.name,
                picked: row.picked,
            }));
            el[param + '_count'] = query
                ? shown.length + '/' + all.length
                : String(all.length);
        }
        el.match_hint = query
            ? 'filter: ' + (state.query.length > 22
                ? state.query.slice(0, 22) + '…'
                : state.query)
            : HINT;
    }

    function onForgePick(event) {
        const item = (event.detail && event.detail.item) || '';
        const cut = item.indexOf('|');
        if (cut < 0) return;
        const param = item.slice(0, cut);
        const name = item.slice(cut + 1);
        if (!state.forgeRows[param]) return;
        state.forgeRows[param].forEach((row) => {
            row.picked = row.name === name;
        });
        paintForge();
    }

    function onForgeFilter(event) {
        state.query = ((event.detail && event.detail.text) || '').trim();
        paintForge();
    }

    function onForgeGenerate() {
        const body = { level: state.level };
        for (const param of Object.keys(FORGE_BODY)) {
            body[FORGE_BODY[param]] = forgePicked(param);
        }
        void generate(body);
    }

    /* ---- the sheet bar (app/slab/sheet.slab) ------------------------- */

    function paintSheetFrom(parameters) {
        const sheet = state.sheet;
        state.pending = {
            species: parameters.species || 'Random',
            background: parameters.background || 'Random',
            char_class: parameters.char_class || 'Random',
            specialization: parameters.specialization || 'Random',
        };
        if (parameters.level) state.level = parameters.level;
        sheet.species = state.pending.species;
        sheet.background = state.pending.background;
        sheet.char_class = state.pending.char_class;
        sheet.specialization = state.pending.specialization;
        sheet.level = String(state.level);
    }

    function closeFields() {
        state.openField = null;
        for (const param of Object.keys(SHEET_FIELDS)) {
            state.sheet['open_' + SHEET_FIELDS[param]] = false;
        }
    }

    async function onOpenField(action) {
        const field = SHEET_FIELDS[action];
        if (!field) return;
        if (state.openField === field) {
            closeFields();
            return;
        }
        let names;
        try {
            if (field === 'specialization') {
                const guild = state.pending ? state.pending.char_class : 'Random';
                names = await specializationsFor(guild);
            } else if (field === 'species') {
                names = state.lists.species;
            } else if (field === 'background') {
                names = state.lists.backgrounds;
            } else {
                names = state.lists.guilds;
            }
        } catch (error) {
            console.error('sheet: option list failed', error);
            sheetError(String(error.message || error));
            return;
        }
        closeFields();
        state.openField = field;
        const current = state.pending ? state.pending[field] : 'Random';
        state.sheet['open_' + field] = true;
        state.sheet.field_options = names.map((name) => ({
            key: field + '|' + name,
            name: name,
            picked: name === current,
        }));
        // The overlay list mounts on the next paint frames — re-mark
        // scrollables once it exists.
        requestAnimationFrame(() => requestAnimationFrame(() => {
            containOverscroll(state.sheet.shadowRoot);
        }));
    }

    /* Mirrors app/parameters.py specialization_selection(). */
    function specializationSelection(selectedGuild, available) {
        const current = state.parameters || {};
        if ((current.char_class || null) !== selectedGuild) return 'Random';
        const spec = current.specialization;
        return available.indexOf(spec) >= 0 ? spec : 'Random';
    }

    function onSheetPick(event) {
        const item = (event.detail && event.detail.item) || '';
        const cut = item.indexOf('|');
        if (cut < 0) return;
        const field = item.slice(0, cut);
        const name = item.slice(cut + 1);
        if (!state.pending || !(field in state.pending)) return;
        state.pending[field] = name;
        state.sheet[field] = name;
        closeFields();
        if (field !== 'char_class') return;
        void (async () => {
            let available;
            try {
                available = await specializationsFor(name);
            } catch (error) {
                console.error('sheet: specialization list failed', error);
                return;
            }
            state.pending.specialization = specializationSelection(name, available);
            state.sheet.specialization = state.pending.specialization;
        })();
    }

    function onLevelStep(direction) {
        const next = Math.max(1, Math.min(20, state.level + direction));
        if (next === state.level) return;
        state.level = next;
        void generate(sheetBody());
    }

    function sheetBody() {
        return {
            species: state.pending.species,
            background: state.pending.background,
            char_class: state.pending.char_class,
            specialization: state.pending.specialization,
            level: state.level,
        };
    }

    function onSheetGenerate() {
        void generate(sheetBody());
    }

    /* ---- POST /api/character/generate -------------------------------- */

    async function generate(body, options) {
        if (state.busy) return null;
        const silent = options && options.silent;
        state.busy = true;
        state.sheet.busy = true;
        loader(true);
        try {
            const response = await fetch('/api/character/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            let data = null;
            try {
                data = await response.json();
            } catch (error) {
                data = null;
            }
            if (!response.ok || !data || data.ok !== true) {
                if (!silent) {
                    sheetError((data && data.error) || ('HTTP ' + response.status));
                }
                return null;
            }
            applyGenerated(data);
            return data;
        } catch (error) {
            console.error('generate failed', error);
            if (!silent) sheetError(String(error.message || error));
            return null;
        } finally {
            state.busy = false;
            state.sheet.busy = false;
            loader(false);
        }
    }

    function applyGenerated(data) {
        state.parameters = data.parameters;
        state.hash = data.hash || '';
        paintSheetFrom(data.parameters);
        state.sheet.error_shown = false;
        state.sheet.error = '';
        closeFields();
        document.getElementById('character_result').innerHTML = data.sheet_html;
        if (state.hash && location.hash !== state.hash) {
            location.hash = state.hash;
        }
        showSheet();
    }

    /* ---- share ------------------------------------------------------- */

    /* Mirrors app/character_url.py character_params_to_compact(). */
    function pathSegment(value) {
        const text = value === undefined || value === null
            ? ''
            : String(value).trim();
        if (!text || text === 'Random') return 'random';
        return encodeURIComponent(text);
    }

    function compactHash(data) {
        const seed = data.seed === undefined || data.seed === null
            ? null
            : Number(data.seed);
        if (!Number.isFinite(seed)) return '';
        const level = Math.max(1, Math.min(20, Number(data.level) || 1));
        return [
            level,
            pathSegment(data.species),
            pathSegment(data.background),
            pathSegment(data.char_class),
            pathSegment(data.specialization),
            pathSegment(data.gender),
            seed,
        ].join('/');
    }

    function buildShareUrl() {
        const compact = compactHash(state.parameters || {});
        return compact
            ? location.origin + location.pathname + '#/' + compact
            : '';
    }

    function setShareStatus(text, isError) {
        const sheet = state.sheet;
        sheet.share_status = text || '';
        sheet.share_error = !!isError;
        clearTimeout(state.shareTimer);
        if (text) {
            state.shareTimer = setTimeout(() => {
                sheet.share_status = '';
                sheet.share_error = false;
                state.shareTimer = null;
            }, 2600);
        }
    }

    async function onShare() {
        const url = buildShareUrl();
        if (!url) {
            setShareStatus('no character to share yet', true);
            return;
        }
        let copied = false;
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(url);
                copied = true;
            }
        } catch (error) {
            copied = false;
        }
        if (!copied) {
            copied = window.prompt('Copy your character link:', url) !== null;
        }
        setShareStatus(copied ? 'link copied' : 'copy cancelled', !copied);
    }

    /* ---- the hash router --------------------------------------------- */

    function intOrNull(value) {
        const number = Number(value);
        return Number.isFinite(number) ? Math.trunc(number) : null;
    }

    function decode(part) {
        try {
            return decodeURIComponent(part);
        } catch (error) {
            return part;
        }
    }

    function pathDimension(part) {
        const text = decode(String(part)).trim();
        if (PATH_NULL_MARKERS.indexOf(text.toLowerCase()) >= 0) return null;
        return text;
    }

    /* Mirrors app/character_url.py parse_character_params_from_hash(). */
    function parseHash(hash) {
        if (!hash) return null;
        let raw = String(hash).trim();
        if (raw.startsWith('#')) raw = raw.slice(1);
        raw = raw.replace(/^\/+|\/+$/g, '');
        if (!raw) return null;
        const parts = raw.split('/').filter(Boolean);
        if (parts.length && parts[0].toLowerCase() === 'character') {
            parts.shift();
        }
        if (parts.length < 6) return null;
        const level = intOrNull(decode(parts[0]));
        const seed = intOrNull(decode(parts[parts.length - 1]));
        if (seed === null) return null;
        const params = {
            level: Math.max(1, Math.min(20, level === null ? 1 : level)),
            species: pathDimension(parts[1]),
            background: pathDimension(parts[2]),
            char_class: pathDimension(parts[3]),
            seed: seed,
        };
        if (parts.length >= 7) {
            params.specialization = pathDimension(parts[4]);
            params.gender = pathDimension(parts[5]);
        } else {
            params.gender = pathDimension(parts[4]);
        }
        return params;
    }

    async function loadHash(raw) {
        const previous = {
            hash: state.hash,
            parameters: state.parameters,
            pending: state.pending,
        };
        state.hash = raw;
        const data = await generate({ hash: raw }, { silent: true });
        if (!data) {
            state.hash = previous.hash;
            state.parameters = previous.parameters;
            state.pending = previous.pending;
            showHome();
        }
    }

    function route() {
        const raw = location.hash || '';
        if (raw && raw === state.hash) {
            showSheet();
            return;
        }
        if (raw) {
            const params = parseHash(raw);
            if (params) {
                void loadHash(raw);
                return;
            }
        }
        showHome();
    }

    /* ---- shell / footer signals -------------------------------------- */

    function onShellSignal(action) {
        if (action === 'nav_home') {
            if (location.hash) location.hash = '';
            else showHome();
            return;
        }
        if (action === 'nav_character') {
            if (state.hash) {
                if (location.hash === state.hash) showSheet();
                else location.hash = state.hash;
            } else {
                void generate({ level: state.level });
            }
            return;
        }
        const route = PARKED_ROUTES[action];
        if (route) location.href = route;
    }

    function onLinkSignal(action) {
        const url = LINKS[action];
        if (url) window.open(url, '_blank', 'noopener');
    }

    /* ---- mounting ----------------------------------------------------- */

    async function registerFonts(mod) {
        const register = mod.SlabForgeElement
            || mod.SlabPickElement
            || Object.values(mod).find(
                (value) => value
                    && typeof value === 'function'
                    && typeof value.registerFont === 'function'
            );
        if (!register) {
            console.warn('slab: no registerFont export; text falls back');
            return;
        }
        for (const [name, url] of FONTS) {
            try {
                const response = await fetch(url);
                if (!response.ok) throw new Error('HTTP ' + response.status);
                const bytes = new Uint8Array(await response.arrayBuffer());
                if (!register.registerFont(name, bytes)) {
                    console.warn('slab: font rejected', name);
                }
            } catch (error) {
                console.warn('slab: font load failed', name, error);
            }
        }
    }

    function wire(element, handlers) {
        for (const [signal, handler] of Object.entries(handlers)) {
            element.addEventListener(signal, handler);
        }
    }

    /* Slab scroll containers live inside the shadow layers; a wheel that
     * reaches their edge chains to the document ("the whole page scrolls").
     * Shadow DOM can't be styled from the page, so mark every scrollable
     * node with overscroll-behavior: contain from JS. */
    function containOverscroll(scope) {
        if (!scope || !scope.querySelectorAll) return;
        for (const el of scope.querySelectorAll('*')) {
            if (el.scrollHeight > el.clientHeight + 4
                || el.scrollWidth > el.clientWidth + 4) {
                el.style.overscrollBehavior = 'contain';
            }
        }
    }

    async function boot() {
        try {
            await loadChoices();
        } catch (error) {
            console.error('choices failed', error);
            return;
        }
        try {
            await Promise.all([
                import('/static/slab/shell.js?v=' + SLAB_VERSION),
                import('/static/slab/footer.js?v=' + SLAB_VERSION),
                import('/static/slab/forge.js?v=' + SLAB_VERSION),
                import('/static/slab/sheet.js?v=' + SLAB_VERSION),
            ]).then((modules) => registerFonts(modules[2]));
        } catch (error) {
            console.error('slab: the components failed to load', error);
            return;
        }

        state.shell = document.querySelector('gl-shell');
        state.forge = document.querySelector('gl-forge');
        state.sheet = document.querySelector('gl-sheet');

        const host = state.shell;
        host.parked = host.dataset.playerOnly !== 'false';
        wire(host, {
            nav_home: () => onShellSignal('nav_home'),
            nav_character: () => onShellSignal('nav_character'),
            nav_npc: () => onShellSignal('nav_npc'),
            nav_npclist: () => onShellSignal('nav_npclist'),
            nav_dm: () => onShellSignal('nav_dm'),
        });
        wire(document.querySelector('gl-footer'), {
            open_about: () => onLinkSignal('open_about'),
            open_wiki: () => onLinkSignal('open_wiki'),
            open_julio: () => onLinkSignal('open_julio'),
        });
        wire(state.forge, {
            pick: onForgePick,
            filter: onForgeFilter,
            generate: onForgeGenerate,
        });
        wire(state.sheet, {
            open_species: () => void onOpenField('open_species'),
            open_background: () => void onOpenField('open_background'),
            open_class: () => void onOpenField('open_class'),
            open_specialization: () => void onOpenField('open_specialization'),
            pick: onSheetPick,
            level_down: () => onLevelStep(-1),
            level_up: () => onLevelStep(1),
            generate: onSheetGenerate,
            share: () => void onShare(),
        });

        containOverscroll(state.sheet.shadowRoot);
        /* Slab ignores wheel events that land on a .slab-hole row (its own
         * handler returns without preventDefault), so the native default
         * chains to the document — "the whole page scrolls". The kernel
         * DOES preventDefault the wheels it consumes; block only the rest,
         * and only while a selector list is open. Registered after slab's
         * own listener, so defaultPrevented already reflects the kernel. */
        state.sheet.addEventListener('wheel', (event) => {
            if (event.defaultPrevented) return;
            const open = Object.values(SHEET_FIELDS).some(
                (field) => state.sheet['open_' + field]
            );
            if (open) event.preventDefault();
        }, { passive: false });

        forgeRowsInit();
        paintForge();

        window.addEventListener('hashchange', route);
        route();
    }

    void boot();
})();
