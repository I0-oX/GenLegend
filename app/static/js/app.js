/* The static Gen Legend frontend: slab mounts, the hash router, and the
 * JSON API (app/main.py). slab owns presentation — the shell, footer, forge,
 * and sheet web components solve layout and paint frames from data they are
 * given — and this file is the whole seam: choices go in as params, signals
 * come out as API calls. Nothing here knows about a UI server: the FastAPI
 * app serves the API, the site shell and the /character/ link redirects.
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

    const SLAB_VERSION = '38';
    // Detail marks (clouds/splotches/fibers/flecks) scattered on
    // <gl-parchment> each load — must match DETAIL in parchment.slab.
    const PARCHMENT_MARKS = 244;

    /* The ground is created together with the sheet: a character's hash
       scatters its own parchment (same hash → same ground), Home takes
       a fresh lottery per visit. FNV-1a into mulberry32 — slab owns the
       paint; this only aims the anchors. */
    function parchmentRandom(seed) {
        let h = 2166136261 >>> 0;
        const text = String(seed === undefined || seed === null ? '' : seed);
        for (let i = 0; i < text.length; i += 1) {
            h ^= text.charCodeAt(i);
            h = Math.imul(h, 16777619) >>> 0;
        }
        return function rand(min, max) {
            h = (h + 0x6D2B79F5) >>> 0;
            let t = h;
            t = Math.imul(t ^ (t >>> 15), t | 1);
            t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
            return Math.round(min + (((t ^ (t >>> 14)) >>> 0) / 4294967296) * (max - min));
        };
    }

    function scatterParchment(seed) {
        const host = document.querySelector('gl-parchment');
        if (!host) return;
        // Remount per creation: a fresh element rebuilds the slab ground
        // and replays the settle animation, so the parchment is visibly
        // drawn anew together with the sheet — never a stale backdrop.
        // Params land on the DETACHED clone before it mounts, so the
        // build bakes the seed rather than catching up later.
        const parchment = host.cloneNode(false);
        const rand = parchmentRandom(seed);
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        // Mottle patches drift inside the viewport but may hang off
        // an edge, like real stains that started beyond the sheet.
        parchment.m1x = rand(-160, Math.max(-40, vw - 640));
        parchment.m1y = rand(-120, Math.max(-40, vh - 420));
        parchment.m2x = rand(-120, Math.max(-40, vw - 560));
        parchment.m2y = rand(-80, Math.max(-40, vh - 520));
        parchment.m3x = rand(-180, Math.max(-40, vw - 560));
        parchment.m3y = rand(-60, Math.max(-40, vh - 460));
        parchment.m4x = rand(-140, Math.max(-40, vw - 460));
        parchment.m4y = rand(-140, Math.max(-40, vh - 400));
        parchment.m5x = rand(-180, Math.max(-40, vw - 560));
        parchment.m5y = rand(-140, Math.max(-40, vh - 380));
        parchment.m6x = rand(-80, Math.max(-40, vw - 480));
        parchment.m6y = rand(-60, Math.max(-40, vh - 420));
        parchment.m7x = rand(-160, Math.max(-40, vw - 420));
        parchment.m7y = rand(-120, Math.max(-40, vh - 300));
        parchment.m8x = rand(-200, Math.max(-40, vw - 620));
        parchment.m8y = rand(-180, Math.max(-40, vh - 460));
        parchment.m9x = rand(-60, Math.max(-40, vw - 700));
        parchment.m9y = rand(-120, Math.max(-40, vh - 420));
        // The cup ring and the three tonal masses travel with the seed —
        // position comes from the hash, so consecutive sheets read as
        // genuinely different parchment: dark-blotched, bleached, warm.
        parchment.ringx = rand(80, Math.max(140, vw - 560));
        parchment.ringy = rand(40, Math.max(120, vh - 420));
        parchment.t1x = rand(-300, vw - 460);
        parchment.t1y = rand(-240, vh - 400);
        parchment.t2x = rand(-260, vw - 420);
        parchment.t2y = rand(-200, vh - 380);
        parchment.t3x = rand(-240, vw - 380);
        parchment.t3y = rand(-180, vh - 340);
        // The detail tangle: every fiber, fleck and foxing bloom is
        // re-aimed, so the scatter never repeats between characters.
        for (let i = 0; i < PARCHMENT_MARKS; i += 1) {
            parchment['d' + i + 'x'] = rand(-240, vw - 40);
            parchment['d' + i + 'y'] = rand(-160, vh - 40);
        }
        // Mount only now, fully seeded: build bakes the `when` lottery.
        host.replaceWith(parchment);
    }
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
        pendingGenerate: null, // coalesced request waiting for the current flight
        openField: null,    // 'species' | 'background' | 'char_class' | 'specialization'
        openEpoch: 0,       // closeFields() counter — invalidates pending opens
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
        // Invariant: a view switch never carries an open selector — a
        // stuck selector-open class leaves gl-sheet's padded hit box
        // swallowing clicks on whatever sits under it.
        closeFields();
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

    async function loadChoicesOnce(url) {
        // A hung request here would leave the app half-wired with no
        // retry: every control looks dead until a reload. Bound it.
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 15000);
        try {
            const response = await fetch(url, { signal: controller.signal });
            if (!response.ok) throw new Error('HTTP ' + response.status);
            return await response.json();
        } finally {
            clearTimeout(timer);
        }
    }

    async function loadChoices() {
        let lastError = null;
        for (let attempt = 0; attempt < 2; attempt += 1) {
            try {
                state.lists = await loadChoicesOnce('/api/choices');
                return;
            } catch (error) {
                lastError = error;
            }
        }
        throw lastError;
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
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 10000);
            let response;
            try {
                response = await fetch(
                    '/api/specializations?guild=' + encodeURIComponent(key),
                    { signal: controller.signal }
                );
            } finally {
                clearTimeout(timer);
            }
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
        // Any close invalidates a pending async open: options for
        // specialization arrive from the network, and a click outside /
        // navigation / pick while they load must not resurrect the
        // selector (and its selector-open hit box) afterwards.
        state.openEpoch += 1;
        state.openField = null;
        for (const param of Object.keys(SHEET_FIELDS)) {
            state.sheet['open_' + SHEET_FIELDS[param]] = false;
        }
        state.sheet.classList.remove('selector-open');
    }

    async function onOpenField(action) {
        const field = SHEET_FIELDS[action];
        if (!field) return;
        if (state.openField === field) {
            closeFields();
            return;
        }
        const epoch = state.openEpoch;
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
        if (epoch !== state.openEpoch) return;
        closeFields();
        state.openField = field;
        const current = state.pending ? state.pending[field] : 'Random';
        state.sheet['open_' + field] = true;
        // Grow the host box so overlay clicks/wheels land on gl-sheet.
        state.sheet.classList.add('selector-open');
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

    /* A click anywhere outside the open selector retracts it — not just a
     * click back on the field. Slab hit-tests internally (native target is
     * always gl-sheet), so geometry decides "inside": the overlay box or a
     * 44px field row under the cursor. Capture phase, so it runs before
     * slab's own click handling re-opens whatever field was hit. */
    document.addEventListener('click', (event) => {
        if (!state.openField) return;
        const x = event.clientX;
        const y = event.clientY;
        const nodes = [];
        const walk = (root) => {
            for (const el of root.querySelectorAll('*')) {
                if (el.shadowRoot) walk(el.shadowRoot);
                nodes.push(el);
            }
        };
        walk(state.sheet.shadowRoot);
        const inside = nodes.some((el) => {
            const b = el.getBoundingClientRect();
            if (x < b.left || x > b.right || y < b.top || y > b.bottom) return false;
            const h = b.height;
            const w = b.width;
            // the open overlay list
            if (h > 150 && h < 200 && w > 150 && w < 500 && el.scrollHeight > el.clientHeight + 20) return true;
            // any selector field row
            if (Math.abs(h - 44) < 4 && w > 150 && w < 600) return true;
            return false;
        });
        if (!inside) closeFields();
    }, true);

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
        if (state.busy) {
            // Buttons clicked mid-flight used to be dropped silently —
            // on a slow server that reads as "the button is dead".
            // Coalesce instead: the newest request wins and runs when the
            // current flight settles; its caller still gets a promise.
            return new Promise((resolve) => {
                if (state.pendingGenerate) state.pendingGenerate.resolve(null);
                state.pendingGenerate = { body: body, options: options, resolve: resolve };
            });
        }
        const silent = options && options.silent;
        state.busy = true;
        state.sheet.busy = true;
        state.skipRestore = false;
        try {
            // Inside the try: if the loader overlay throws, the catch +
            // finally must still run, or state.busy stays true forever
            // and every later Generate silently no-ops until a reload.
            loader(true);
            // The loader covers the page while this runs; a request that
            // never settles would leave it up forever and every button
            // under it dead until a reload. Abort so finally always runs.
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 30000);
            let response;
            try {
                response = await fetch('/api/character/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                    signal: controller.signal,
                });
            } finally {
                clearTimeout(timer);
            }
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
            if (!silent) {
                sheetError(error && error.name === 'AbortError'
                    ? 'the forge took too long — try again'
                    : String(error.message || error));
            }
            return null;
        } finally {
            state.busy = false;
            state.sheet.busy = false;
            try {
                loader(false);
            } catch (error) {
                console.error('loader hide failed', error);
            }
            const queued = state.pendingGenerate;
            state.pendingGenerate = null;
            if (queued) {
                generate(queued.body, queued.options).then(
                    queued.resolve,
                    () => queued.resolve(null)
                );
            }
        }
    }

    /* The sheet body is <gl-sheetbody> (app/slab/sheetbody.slab): params
       in, never HTML in. Assignment goes through the compiled element's
       accessors, which is how every other slab host on this page paints. */
    function paintSheetBody(sheet) {
        const body = document.querySelector('gl-sheetbody');
        if (!body || !sheet) return;
        Object.assign(body, sheet);
    }

    function applyGenerated(data) {
        state.parameters = data.parameters;
        state.hash = data.hash || '';
        paintSheetFrom(data.parameters);
        state.sheet.error_shown = false;
        state.sheet.error = '';
        closeFields();
        paintSheetBody(data.sheet_data);
        // The parchment is created together with the sheet: the
        // character's hash aims every stain and fiber of its own ground.
        scatterParchment(data.hash || location.hash);
        // The user may have hit Home while this ran — never yank them back
        // to the sheet, neither via the hash nor via the view itself.
        if (!state.skipRestore) {
            if (state.hash && location.hash !== state.hash) {
                location.hash = state.hash;
            }
            showSheet();
        }
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
            // A generate still in flight re-writes the view/hash when it
            // lands; remember the user already left so it can't yank them
            // back to the sheet — even when Home was pressed from the
            // clean home URL (hash already empty). A request still queued
            // behind the flight dies with the same intent.
            state.skipRestore = true;
            if (state.pendingGenerate) {
                state.pendingGenerate.resolve(null);
                state.pendingGenerate = null;
            }
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
                import('/static/slab/sheetbody.js?v=' + SLAB_VERSION),
                import('/static/slab/parchment.js?v=' + SLAB_VERSION),
            ]).then((modules) => registerFonts(modules[2]));
        } catch (error) {
            console.error('slab: the components failed to load', error);
            return;
        }

        /* Home's own imperfection: a fresh ground for the visit; a
           sheet redraws it from its hash when it paints (see
           applyGenerated). Slab owns the paint — this only aims
           anchors; no SVG, no CSS lines. */
        scatterParchment(location.hash || 'home:' + Date.now());

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
