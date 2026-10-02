/* Summon loader for the static slab site.
 * Generated from AtlasVenustas/Tools_of_Loader.py loader_script() -
 * regenerate with make loader-script after editing the source.
 */
(() => {
  const AUTO_HIDE_MS = 12000;
  const ACTION_IDS = new Set(["btn_gen_char", "btn_char_apply_selectors", "btn_char_level_down", "btn_char_level_up", "btn_gen_npc", "btn_gen_npc_again", "btn_gen_list", "btn_gen_list_again"]);
  const STATUS_LINES = ["Summoning your legend...", "Inscribing dice runes...", "Binding fate...", "Consulting the oracle...", "Polishing weapons...", "Crafting armor...", "Infusing potions...", "Awakening powers... ", "Joining guild...", "Writting tragic past...", "Finding tavern...", "Setting the stars to guide party...", "Assembling party...", "Enfuriating goblins...", "Wake up, traveler...", "The journey begins..."];
  const SOL_SYMBOLS = ["☉", "☼", "✶", "✦", "✧", "✪", "✫", "✬", "✭", "✮", "✯", "⚛", "⚜", "⚝", "⚚", "☤", "☥", "☯", "☮", "☸", "⛤", "⛥", "⛦", "⛧", "⍟", "⌘", "※", "◈", "◉", "◎", "♆", "♃", "♄", "♅", "☿", "♁", "⚳", "⚷", "⚵"];
  const PLANET_SYMBOLS = ["ᚠ", "ᚢ", "ᚦ", "ᚨ", "ᚱ", "ᚲ", "ᚷ", "ᚹ", "ᚺ", "ᚾ", "ᛁ", "ᛃ", "ᛇ", "ᛈ", "ᛉ", "ᛊ", "ᛋ", "ᛏ", "ᛒ", "ᛖ", "ᛗ", "ᛚ", "ᛜ", "ᛞ", "ᛟ", "ᛡ", "ᛢ", "ᛣ", "ᛤ", "ᛥ", "⚝", "⚚", "✦", "✶", "✧", "⛥", "☿", "♆", "◈", "◇", "α", "β", "γ", "δ", "ε", "ζ", "η", "θ", "λ", "π", "σ", "φ", "ψ", "ω", "∑", "∫", "∂", "∇", "∞", "√", "≈"];

  let statusTicker = null;
  let typingTicker = null;
  let autoHideTimer = null;
  let flipTicker = null;
  let statusIndex = 0;

  function randomFrom(list) {
    return list[Math.floor(Math.random() * list.length)];
  }

  function getLoader() {
    return document.getElementById('loader');
  }

  function getMessageNode() {
    return document.getElementById('loader-message');
  }

  function populatePlanets() {
    const loader = getLoader();
    if (!loader) return;

    const sun = loader.querySelector('.sol-layer');
    if (sun) sun.textContent = randomFrom(SOL_SYMBOLS);

    loader.querySelectorAll('.orbit-layer').forEach((orbit, orbitIndex) => {
      orbit.innerHTML = '';
      orbit.classList.remove('flip-x', 'flip-y');
      // The 2D spin lives on this inner ring; the outer shell only coin-flips.
      const ring = document.createElement('div');
      ring.className = 'orbit-ring';
      const count = orbitIndex + 3;
      const radius = Math.max(20, orbit.offsetWidth / 2);
      for (let i = 0; i < count; i += 1) {
        const angle = (360 * i) / count;
        const planet = document.createElement('div');
        planet.className = 'planet';
        planet.textContent = randomFrom(PLANET_SYMBOLS);
        planet.style.transform = `rotate(${angle}deg) translate(${radius}px)`;
        ring.appendChild(planet);
      }
      orbit.appendChild(ring);
    });
  }

  function startFlips() {
    if (flipTicker) clearInterval(flipTicker);
    // Every discrete second one random orbit coin-flips 180 degrees on a
    // random axis (X or Y); the mirrored shell reverses its ring's apparent
    // spin direction until a later flip turns it back.
    flipTicker = setInterval(() => {
      const loader = getLoader();
      if (!loader) return;
      const orbits = loader.querySelectorAll('.orbit-layer');
      if (!orbits.length) return;
      const orbit = orbits[Math.floor(Math.random() * orbits.length)];
      orbit.classList.toggle(Math.random() < 0.5 ? 'flip-x' : 'flip-y');
    }, 1000);
  }

  function stopFlips() {
    if (flipTicker) {
      clearInterval(flipTicker);
      flipTicker = null;
    }
  }

  function typeLine(text) {
    const node = getMessageNode();
    if (!node) return;
    if (typingTicker) clearInterval(typingTicker);
    let i = 0;
    node.textContent = '';
    typingTicker = setInterval(() => {
      i += 1;
      node.textContent = text.slice(0, i);
      if (i >= text.length) {
        clearInterval(typingTicker);
        typingTicker = null;
      }
    }, 30);
  }

  function startStatus() {
    if (statusTicker) clearInterval(statusTicker);
    typeLine(STATUS_LINES[statusIndex % STATUS_LINES.length]);
    statusTicker = setInterval(() => {
      statusIndex += 1;
      typeLine(STATUS_LINES[statusIndex % STATUS_LINES.length]);
    }, 2200);
  }

  function stopStatus() {
    if (statusTicker) {
      clearInterval(statusTicker);
      statusTicker = null;
    }
    if (typingTicker) {
      clearInterval(typingTicker);
      typingTicker = null;
    }
  }

  function showLoader() {
    const loader = getLoader();
    if (!loader) return;
    loader.classList.add('show');
    loader.style.pointerEvents = 'none';
    populatePlanets();
    startStatus();
    startFlips();
    if (autoHideTimer) clearTimeout(autoHideTimer);
    autoHideTimer = setTimeout(() => {
      hideLoader();
    }, AUTO_HIDE_MS);
  }

  function hideLoader() {
    const loader = getLoader();
    if (!loader) return;
    loader.classList.remove('show');
    stopStatus();
    stopFlips();
    if (autoHideTimer) {
      clearTimeout(autoHideTimer);
      autoHideTimer = null;
    }
  }

  window.summonLoader = { show: showLoader, hide: hideLoader };

  document.addEventListener('click', (event) => {
    const target = event.target.closest('button, input[type="submit"], [data-show-loader]');
    if (!target) return;
    if (target.hasAttribute('data-show-loader') || ACTION_IDS.has(target.id || '')) {
      showLoader();
    }
  }, true);

  function installShinyLoaderHandler() {
    if (typeof Shiny === 'undefined' || !Shiny.addCustomMessageHandler) return false;
    if (window.__summonLoaderHandlerInstalled) return true;
    window.__summonLoaderHandlerInstalled = true;
    Shiny.addCustomMessageHandler('set_loader', function(msg) {
      if (msg && msg.action === 'show') {
        showLoader();
      } else {
        hideLoader();
      }
    });
    return true;
  }

  function installOutputObservers() {
    const outputIds = ['character_result', 'npc_result', 'npc_list_result'];
    outputIds.forEach((id) => {
      const root = document.getElementById(id);
      if (!root || root.__loaderObserverInstalled) return;
      root.__loaderObserverInstalled = true;
      const observer = new MutationObserver(() => {
        hideLoader();
      });
      observer.observe(root, { childList: true, subtree: true });
    });
  }

  if (!installShinyLoaderHandler()) {
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      if (installShinyLoaderHandler() || tries >= 80) {
        clearInterval(timer);
      }
    }, 100);
    window.addEventListener('shiny:connected', installShinyLoaderHandler, { once: true });
  }

  installOutputObservers();
  document.addEventListener('shiny:idle', () => {
    hideLoader();
    installOutputObservers();
  });
  document.addEventListener('shiny:disconnected', hideLoader);
  window.addEventListener('hashchange', hideLoader);

  window.addEventListener('load', hideLoader);
})();

