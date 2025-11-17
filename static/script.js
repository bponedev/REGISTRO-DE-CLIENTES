// /static/script.js
document.addEventListener('DOMContentLoaded', function () {
  // toast helper
  function showToast(msg, timeout=2500) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.innerText = msg;
    t.style.display = 'block';
    setTimeout(()=> t.style.display = 'none', timeout);
  }

  // select all
  const selectAll = document.getElementById('select-all');
  if (selectAll) {
    selectAll.addEventListener('change', () => {
      document.querySelectorAll('.row-select').forEach(cb => cb.checked = selectAll.checked);
    });
  }
  const selectAllExcl = document.getElementById('select-all-excl');
  if (selectAllExcl) {
    selectAllExcl.addEventListener('change', () => {
      document.querySelectorAll('.row-select').forEach(cb => cb.checked = selectAllExcl.checked);
    });
  }

  // delete selected form
  const deleteForm = document.getElementById('deleteSelectedForm');
  if (deleteForm) {
    deleteForm.addEventListener('submit', (e) => {
      const ids = [...document.querySelectorAll('.row-select:checked')].map(x=>x.value);
      if (!ids.length) {
        alert('Nenhum registro selecionado.');
        e.preventDefault();
        return;
      }
      if (!confirm('Deseja realmente excluir os registros selecionados?')) {
        e.preventDefault();
        return;
      }
      ids.forEach(id=>{
        const inp = document.createElement('input');
        inp.type='hidden'; inp.name='ids'; inp.value=id;
        deleteForm.appendChild(inp);
      });
    });
  }

  // migrate selected (top)
  const topMoveSelect = document.getElementById('top-move-select');
  const topActionsForm = document.getElementById('top-actions');
  if (topActionsForm) {
    topActionsForm.addEventListener('submit', (e)=>{
      e.preventDefault();
      const target = topMoveSelect.value;
      if (!target) { alert('Selecione o escritório destino.'); return; }
      const ids = [...document.querySelectorAll('.row-select:checked')].map(x=>x.value);
      if (!ids.length) { alert('Nenhum registro selecionado.'); return; }
      if (!confirm(`Deseja mover ${ids.length} registro(s) para ${target.replace(/_/g,' ')}?`)) return;
      // append inputs and submit
      ids.forEach(id=>{
        const inp = document.createElement('input');
        inp.type='hidden'; inp.name='ids'; inp.value=id;
        topActionsForm.appendChild(inp);
      });
      const src = document.createElement('input');
      src.type='hidden'; src.name='office_current'; src.value = document.querySelector('select[name="office"]').value || 'CENTRAL';
      topActionsForm.appendChild(src);
      topActionsForm.submit();
    });
  }

  // top single migrate via inline selects (confirmation + post)
  document.querySelectorAll('select[name="office_target"]').forEach(sel=>{
    sel.addEventListener('change', (ev)=>{
      const newVal = sel.value;
      if (!newVal) return;
      const tr = sel.closest('tr');
      const id = tr.querySelector('.row-select').value;
      const office_current = document.querySelector('select[name="office"]').value || 'CENTRAL';
      if (!confirm(`Mover este registro (ID ${id}) para ${newVal.replace(/_/g,' ')} ?`)) {
        // reset select
        sel.value = "";
        return;
      }
      // create form and submit
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/migrate';
      const inpId = document.createElement('input'); inpId.type='hidden'; inpId.name='id'; inpId.value = id; form.appendChild(inpId);
      const inpFrom = document.createElement('input'); inpFrom.type='hidden'; inpFrom.name='office_current'; inpFrom.value = office_current; form.appendChild(inpFrom);
      const inpTo = document.createElement('input'); inpTo.type='hidden'; inpTo.name='office_target'; inpTo.value = newVal; form.appendChild(inpTo);
      document.body.appendChild(form);
      form.submit();
    });
  });

  // apply small toast on page load if there are flash messages (the server renders flash messages)
  const flashEls = document.querySelectorAll('.flash');
  if (flashEls && flashEls.length>0) {
    flashEls.forEach(fe => {
      showToast(fe.textContent, 2200);
    });
  }
});
