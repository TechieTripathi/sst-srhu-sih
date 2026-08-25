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


// Responsive tables (.table-base.table-cards): copy header text to data-label on each cell and
// wrap the last (actions) column in a <details> so it collapses on phones. CSS does the rest.
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('table.table-cards').forEach(function (t) {
        var heads = Array.prototype.map.call(t.querySelectorAll('thead th'), function (th) { return th.textContent.trim(); });
        if (!heads.length) return;
        var last = heads.length - 1, lastIsActions = heads[last] === '' || /actions|details/i.test(heads[last]);
        t.querySelectorAll('tbody tr').forEach(function (tr) {
            var cells = tr.children, hasPrimary = tr.querySelector('td[data-primary]');
            for (var i = 0; i < cells.length; i++) {
                var td = cells[i];
                if ((!hasPrimary && i === 0) || td.hasAttribute('data-primary')) { td.setAttribute('data-primary', ''); continue; }
                if (i === last && lastIsActions) {
                    td.classList.add('row-more');
                    if (!td.querySelector(':scope > .row-more-panel')) {
                        var btn = document.createElement('button'), box = document.createElement('div');
                        btn.type = 'button'; btn.className = 'row-more-toggle'; btn.textContent = 'More ▾'; btn.setAttribute('aria-expanded', 'false');
                        box.className = 'row-more-panel';
                        // secondary cells (data-more) appear inside the panel on phones, as labelled lines
                        var extra = document.createElement('dl'); extra.className = 'only-cards';
                        Array.prototype.forEach.call(cells, function (c, j) {
                            if (!c.hasAttribute('data-more') || !heads[j]) return;
                            var dt = document.createElement('dt'); dt.className = 'only-cards-dt'; dt.textContent = heads[j];
                            var dd = document.createElement('dd'); dd.className = 'only-cards-dd'; dd.innerHTML = c.innerHTML;
                            extra.appendChild(dt); extra.appendChild(dd);
                        });
                        if (extra.children.length) box.appendChild(extra);
                        while (td.firstChild) box.appendChild(td.firstChild);
                        td.appendChild(btn); td.appendChild(box);
                        btn.addEventListener('click', function () { var open = td.classList.toggle('is-open'); btn.textContent = open ? 'Less ▴' : 'More ▾'; btn.setAttribute('aria-expanded', open ? 'true' : 'false'); });
                    }
                    continue;
                }
                if (heads[i]) td.setAttribute('data-label', heads[i]);
                if (!td.querySelector(':scope > .cell-value')) {           // stack multi-line content on the right of the label
                    var v = document.createElement('div'); v.className = 'cell-value';
                    while (td.firstChild) v.appendChild(td.firstChild); td.appendChild(v);
                }
            }
        });
    });
});
