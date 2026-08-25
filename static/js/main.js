/* TechForge 3.0 — small shared helpers (no framework). */

// Modals: elements with class .modal-backdrop; open = flex, closed = hidden.
function openModal(id) { var m = document.getElementById(id); if (!m) return; m.style.display = 'flex'; m.classList.remove('hidden'); document.body.style.overflow = 'hidden'; var f = m.querySelector('input, select, textarea, button'); if (f) f.focus(); }
function closeModal(id) { var m = document.getElementById(id); if (!m) return; m.style.display = 'none'; document.body.style.overflow = ''; }
document.addEventListener('click', function (e) { if (e.target.classList && e.target.classList.contains('modal-backdrop')) closeModal(e.target.id); });
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') document.querySelectorAll('.modal-backdrop').forEach(function (m) { if (m.style.display === 'flex') closeModal(m.id); }); });

// Toast: transient confirmation (success/info). Anything needing action is rendered server-side as a persistent alert.
function showToast(message, type) {
    type = type || 'info';
    var region = document.getElementById('flash-region');
    if (!region) { region = document.createElement('div'); region.id = 'flash-region'; region.className = 'fixed z-50 inset-x-3 top-3 sm:inset-x-auto sm:right-4 sm:top-4 sm:w-[26rem] flex flex-col gap-2'; region.setAttribute('aria-live', 'polite'); document.body.appendChild(region); }
    var el = document.createElement('div'); el.className = 'alert-' + (type === 'danger' ? 'error' : type) + ' shadow-lg'; el.setAttribute('role', 'status'); el.textContent = message; region.appendChild(el);
    setTimeout(function () { el.style.transition = 'opacity .3s'; el.style.opacity = '0'; setTimeout(function () { el.remove(); }, 300); }, type === 'error' ? 8000 : 4000);
}

// Copy text to clipboard with feedback. Works on http://LAN-IP too (no navigator.clipboard there).
function copyText(text, btn) {
    var done = function (ok) {
        if (btn) { var orig = btn.innerHTML; btn.innerHTML = ok ? '✓ Copied' : '✗ Copy failed'; setTimeout(function () { btn.innerHTML = orig; }, 1800); }
        if (!ok) showToast('Could not copy — select the text and press Ctrl+C', 'error');
    };
    var legacy = function () {
        var ta = document.createElement('textarea'); ta.value = text; ta.setAttribute('readonly', '');
        ta.style.position = 'fixed'; ta.style.top = '-1000px'; document.body.appendChild(ta); ta.select();
        var ok = false; try { ok = document.execCommand('copy'); } catch (e) {} document.body.removeChild(ta); done(ok);
    };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(function () { done(true); }, legacy); else legacy();
}
