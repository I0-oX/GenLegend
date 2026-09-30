/* The slab Character Generator face (app/slab/forge.slab) talks Shiny here.
 *
 * slab owns presentation only: it solves layout and paints frames from data
 * it is given, and emits signals when the player picks, filters, or forges.
 * This file is the whole seam — choices go in as list params, picks come out
 * as the Shiny inputs the server already reads (char_species, char_class,
 * char_background, btn_gen_char). Nothing on the server knows slab exists.
 */
(() => {
    'use strict';

    const FONTS = [
        ['Cinzel', '/static/fonts/slab-cinzel-700.ttf'],
        ['Eagle Lake', '/static/fonts/slab-eagle-lake-400.ttf'],
    ];
    const CATEGORY_INPUT = {
        species: 'char_species',
        classes: 'char_class',
        backgrounds: 'char_background',
    };
    const HINT = 'type to narrow every option';

    const state = {
        choices: null,   // {species: [{key,name,picked}], …} once parsed
        query: '',
        host: null,
        element: null,
        mounting: false,
        fontBytes: null,
        pendingSync: null,
        seq: 0,
        handlerRegistered: false,
        queued: [],
    };

    /* ---- Shiny input bridge ---------------------------------------- */

    function setInput(name, value, isEvent) {
        const send = () => {
            if (typeof window.Shiny === 'undefined'
                    || typeof Shiny.setInputValue !== 'function') return;
            Shiny.setInputValue(
                name,
                value,
                isEvent ? {priority: 'event'} : undefined
            );
        };
        if (typeof window.Shiny !== 'undefined' && Shiny.shinyapp) {
            send();
        } else {
            state.queued.push(send);
        }
    }

    function flushQueued() {
        if (typeof window.Shiny === 'undefined' || !Shiny.shinyapp) return;
        state.queued.splice(0).forEach((send) => send());
    }

    document.addEventListener('shiny:connected', flushQueued);

    /* ---- choices payload ------------------------------------------- */

    function readChoices() {
        const node = document.getElementById('forge-choices');
        if (!node) return null;
        let payload;
        try {
            payload = JSON.parse(node.textContent || '');
        } catch (error) {
            console.warn('forge: choices payload is not JSON', error);
            return null;
        }
        const choices = {};
        for (const cat of Object.keys(CATEGORY_INPUT)) {
            const names = Array.isArray(payload[cat]) ? payload[cat] : [];
            choices[cat] = names.map((name) => ({
                key: cat + '|' + name,
                name: name,
                picked: name === 'Random',
            }));
        }
        return choices;
    }

    function pickedName(cat) {
        const hit = (state.choices[cat] || []).find((row) => row.picked);
        return hit ? hit.name : 'Random';
    }

    /* ---- painting data back into slab ------------------------------ */

    function paint() {
        const el = state.element;
        if (!el || !state.choices) return;
        const query = state.query.toLowerCase();
        for (const cat of Object.keys(CATEGORY_INPUT)) {
            const all = state.choices[cat];
            const shown = query
                ? all.filter((row) => row.picked
                    || row.name.toLowerCase().includes(query))
                : all;
            el[cat] = shown.map((row) => ({
                key: row.key,
                name: row.name,
                picked: row.picked,
            }));
            el[cat + '_count'] = query
                ? shown.length + '/' + all.length
                : String(all.length);
        }
        el.match_hint = query
            ? 'filter: ' + (state.query.length > 22
                ? state.query.slice(0, 22) + '…'
                : state.query)
            : HINT;
    }

    /* ---- slab signals ---------------------------------------------- */

    function onPick(ev) {
        const item = (ev.detail && ev.detail.item) || '';
        const cut = item.indexOf('|');
        if (cut < 0) return;
        const cat = item.slice(0, cut);
        const name = item.slice(cut + 1);
        if (!state.choices[cat]) return;
        state.choices[cat].forEach((row) => {
            row.picked = row.name === name;
        });
        paint();
        setInput(CATEGORY_INPUT[cat], name, true);
    }

    function onFilter(ev) {
        state.query = ((ev.detail && ev.detail.text) || '').trim();
        paint();
    }

    function onGenerate() {
        // The pick inputs already carry the current choices; sending them
        // again keeps one flush in front of the button event.
        for (const cat of Object.keys(CATEGORY_INPUT)) {
            setInput(CATEGORY_INPUT[cat], pickedName(cat), false);
        }
        state.seq += 1;
        setInput('btn_gen_char', state.seq, true);
    }

    /* ---- server → face (resolved choices come back as "Random") ----- */

    function applySync(msg) {
        for (const cat of Object.keys(CATEGORY_INPUT)) {
            const want = msg[cat];
            if (typeof want !== 'string') continue;
            state.choices[cat].forEach((row) => {
                row.picked = row.name === want;
            });
            setInput(CATEGORY_INPUT[cat], want, true);
        }
        paint();
    }

    function registerHandler() {
        if (state.handlerRegistered) return;
        if (typeof window.Shiny === 'undefined'
                || typeof Shiny.addCustomMessageHandler !== 'function') return;
        Shiny.addCustomMessageHandler('forge_home_selections', (msg) => {
            if (!msg) return;
            if (!state.choices) {
                // Home not mounted (yet): hold it until choices arrive.
                state.pendingSync = msg;
                return;
            }
            applySync(msg);
        });
        state.handlerRegistered = true;
    }

    registerHandler();
    document.addEventListener('shiny:connected', registerHandler);

    /* ---- mounting --------------------------------------------------- */

    async function loadFonts(mod) {
        if (state.fontBytes) return state.fontBytes;
        const register = mod.SlabForgeElement
            || mod.SlabPickElement
            || Object.values(mod).find(
                (value) => value
                    && typeof value === 'function'
                    && typeof value.registerFont === 'function'
                );
        if (!register) return null;
        const loaded = [];
        for (const [name, url] of FONTS) {
            try {
                const response = await fetch(url);
                if (!response.ok) throw new Error('HTTP ' + response.status);
                const bytes = new Uint8Array(await response.arrayBuffer());
                if (!register.registerFont(name, bytes)) {
                    console.warn('forge: font rejected by slab', name);
                }
                loaded.push([name, bytes]);
            } catch (error) {
                console.warn('forge: font load failed', name, error);
            }
        }
        state.fontBytes = loaded;
        return loaded;
    }

    async function mount(host) {
        if (state.mounting) return;
        state.mounting = true;
        try {
            if (!state.choices) {
                state.choices = readChoices();
            }
            if (!state.choices) return;

            const mod = await import(
                '/static/slab/forge.js?v=' + (host.dataset.slabVersion || '0')
                );
            await loadFonts(mod);

            const el = document.createElement('gl-forge');
            el.className = 'forge-element';
            el.addEventListener('pick', onPick);
            el.addEventListener('filter', onFilter);
            el.addEventListener('generate', onGenerate);
            host.appendChild(el);

            state.host = host;
            state.element = el;
            paint();

            // Push the initial selections so the server never sees a null
            // char_species/char_class/char_background before a generate.
            for (const cat of Object.keys(CATEGORY_INPUT)) {
                setInput(CATEGORY_INPUT[cat], pickedName(cat), false);
            }
            if (state.pendingSync) {
                applySync(state.pendingSync);
                state.pendingSync = null;
            }
        } catch (error) {
            console.error('forge: the slab face failed to mount', error);
        } finally {
            state.mounting = false;
        }
    }

    function ensureHost() {
        const host = document.getElementById('forge-host');
        if (!host) {
            state.host = null;
            state.element = null;
            return;
        }
        if (host === state.host && state.element && state.element.isConnected) {
            return;
        }
        if (state.element && state.element.isConnected
                && state.element.parentElement === host) {
            return;
        }
        mount(host);
    }

    let scheduled = false;
    function schedule() {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(() => {
            scheduled = false;
            ensureHost();
        });
    }

    new MutationObserver(schedule).observe(document.documentElement, {
        childList: true,
        subtree: true,
    });
    ensureHost();
})();
