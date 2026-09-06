/* Cell references ($<row>:<Column>) — shared by the Data Table editor and
 * the Program editor.
 *
 * The input/textarea ALWAYS holds the raw value (saves post the reference,
 * not its resolution). When a reference cell is not being edited, the field
 * is hidden and its sibling .dt-cell-display shows the resolved text.
 *
 * Usage:
 *   var refs = initCellRefs({
 *       containerId: 'rows-container',
 *       columns: ['Time', 'Speaker'],
 *       getField: function (tr, columnName) { return <input|textarea>; }
 *   });
 *   refs.renumber(); refs.refreshAll();   // exposed for Sortable hooks
 */
function initCellRefs(opts) {
    var container = document.getElementById(opts.containerId);
    if (!container) return null;

    var columns = opts.columns;
    var REF_PREFIX_RE = /^\$\d+:/;
    var REF_FULL_RE = /^\$(\d+):(.+)$/;

    function rows() {
        return Array.from(container.children).filter(function (el) {
            return el.tagName === 'TR';
        });
    }

    function renumber() {
        rows().forEach(function (tr, i) {
            var td = tr.querySelector('.dt-row-num');
            if (td) td.textContent = i + 1;
        });
    }

    function resolveRef(raw, seen) {
        var m = REF_FULL_RE.exec((raw || '').trim());
        if (!m) return { ok: true, text: raw };
        var rowIdx = parseInt(m[1], 10) - 1;
        var col = m[2].trim();
        var trs = rows();
        if (rowIdx < 0 || rowIdx >= trs.length) {
            return { ok: false, error: 'Row ' + m[1] + ' does not exist' };
        }
        var actualCol = columns.find(function (c) {
            return c.toLowerCase() === col.toLowerCase();
        });
        if (!actualCol) {
            return { ok: false, error: 'Column "' + col + '" does not exist' };
        }
        var key = rowIdx + '::' + actualCol;
        seen = seen || {};
        if (seen[key]) return { ok: false, error: 'Circular reference' };
        seen[key] = true;
        var target = opts.getField(trs[rowIdx], actualCol);
        if (!target) return { ok: false, error: 'Column "' + col + '" does not exist' };
        return resolveRef(target.value, seen);
    }

    function refreshCell(el) {
        var wrap = el.closest('.dt-cell');
        if (!wrap || document.activeElement === el) return;
        var disp = wrap.querySelector('.dt-cell-display');
        if (!disp) return;
        el.classList.remove('dt-ref-mode', 'dt-ref-error');
        el.removeAttribute('title');
        if (!REF_PREFIX_RE.test((el.value || '').trim())) {
            disp.classList.add('d-none');
            el.classList.remove('dt-hidden');
            return;
        }
        var res = resolveRef(el.value);
        if (res.ok) {
            var empty = !(res.text || '').trim();
            disp.textContent = empty ? '(empty — ' + el.value.trim() + ')' : res.text;
            disp.classList.toggle('dt-empty', empty);
            disp.title = el.value.trim() + ' — click to edit the reference';
            disp.classList.remove('d-none');
            el.classList.add('dt-hidden');
        } else {
            disp.classList.add('d-none');
            el.classList.remove('dt-hidden');
            el.classList.add('dt-ref-error');
            el.title = res.error;
        }
    }

    function refreshAll(except) {
        container.querySelectorAll('.dt-cell-input').forEach(function (el) {
            if (el !== except) refreshCell(el);
        });
    }

    /* Column-name autocomplete */
    var acBox = null;
    function hideAc() { if (acBox) acBox.style.display = 'none'; }

    function showAc(el) {
        var m = /^\$(\d+):(.*)$/.exec((el.value || '').trim());
        if (!m) { hideAc(); return; }
        var typed = m[2].toLowerCase();
        var matches = columns.filter(function (c) {
            return c.toLowerCase().indexOf(typed) === 0 && c !== m[2];
        });
        if (!matches.length) { hideAc(); return; }
        if (!acBox) {
            acBox = document.createElement('div');
            acBox.className = 'dt-ac';
            document.body.appendChild(acBox);
        }
        acBox.innerHTML = '';
        matches.forEach(function (c) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'dt-ac-item';
            b.textContent = c;
            b.addEventListener('mousedown', function (e) {
                e.preventDefault(); // keep focus in the field
                el.value = '$' + m[1] + ':' + c;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                hideAc();
            });
            acBox.appendChild(b);
        });
        var r = el.getBoundingClientRect();
        acBox.style.left = (window.scrollX + r.left) + 'px';
        acBox.style.top = (window.scrollY + r.bottom + 2) + 'px';
        acBox.style.minWidth = r.width + 'px';
        acBox.style.display = 'block';
    }

    container.addEventListener('focusin', function (e) {
        var el = e.target.closest('.dt-cell-input');
        if (!el) return;
        el.classList.remove('dt-ref-error');
        el.removeAttribute('title');
        if (REF_PREFIX_RE.test((el.value || '').trim())) {
            el.classList.add('dt-ref-mode');
            showAc(el);
        }
    });

    container.addEventListener('input', function (e) {
        var el = e.target.closest('.dt-cell-input');
        if (!el) return;
        var isRef = REF_PREFIX_RE.test((el.value || '').trim());
        el.classList.toggle('dt-ref-mode', isRef);
        if (isRef) showAc(el); else hideAc();
        refreshAll(el); // live propagation to referencing cells
    });

    container.addEventListener('focusout', function (e) {
        var el = e.target.closest('.dt-cell-input');
        if (!el) return;
        hideAc();
        el.classList.remove('dt-ref-mode');
        setTimeout(function () {
            refreshCell(el);
            refreshAll(el);
            if (el.classList.contains('dt-ref-error') && typeof cmToast === 'function') {
                cmToast(el.title + ': ' + el.value.trim(), 'error');
            }
        }, 0);
    });

    /* Click a resolved display -> edit the raw reference */
    container.addEventListener('click', function (e) {
        var disp = e.target.closest('.dt-cell-display');
        if (!disp) return;
        var el = disp.closest('.dt-cell').querySelector('.dt-cell-input');
        disp.classList.add('d-none');
        el.classList.remove('dt-hidden');
        el.focus();
    });

    function refreshPage() { renumber(); refreshAll(); }
    document.addEventListener('DOMContentLoaded', refreshPage);
    document.body.addEventListener('htmx:afterSwap', refreshPage);
    refreshPage();

    return { renumber: renumber, refreshAll: refreshAll };
}
