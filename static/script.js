// /static/script.js
document.addEventListener('DOMContentLoaded', function () {
  function showToast(msg, timeout=2200) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.innerText = msg;
    t.style.display = 'block';
    setTimeout(()=> t.style.display = 'none', timeout);
  }

  const selectAll = document.getElementById('select-all');
  if (selectAll) {
    selectAll.addEventListener('change', () => {
      document.querySelectorAll('.row-select').forEach(cb => cb.checked = selectAll.checked);
    });
  }

  // delete selected
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

  // top move selected
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
      ids.forEach(id=>{
        const inp = document.createElement('input');
        inp.type='hidden'; inp.name='ids'; inp.value=id;
        topActionsForm.appendChild(inp);
      });
      const src = document.createElement('input');
      src.type='hidden'; src.name='office_current'; src.value = (document.querySelector('select[name="office"]')||{value:'CENTRAL'}).value;
      topActionsForm.appendChild(src);
      topActionsForm.submit();
    });
  }

  // inline select change -> confirmation -> POST to /migrate
  document.querySelectorAll('.inline-migrate-select').forEach(sel=>{
    sel.addEventListener('change', (ev)=>{
      const toKey = sel.value;
      if (!toKey) return;
      const tr = sel.closest('tr');
      const idInput = tr.querySelector('.row-select');
      if (!idInput) { sel.value = ""; return; }
      const id = idInput.value;
      const office_current = (document.querySelector('select[name="office"]')||{value:'CENTRAL'}).value;
      // confirmation (option C)
      const display = sel.options[sel.selectedIndex].text;
      if (!confirm(`Confirmar mover o registro ID ${id} para ${display}?`)) {
        sel.value = "";
        return;
      }
      // post via form
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/migrate';
      const inpId = document.createElement('input'); inpId.type='hidden'; inpId.name='id'; inpId.value = id; form.appendChild(inpId);
      const inpFrom = document.createElement('input'); inpFrom.type='hidden'; inpFrom.name='office_current'; inpFrom.value = office_current; form.appendChild(inpFrom);
      const inpTo = document.createElement('input'); inpTo.type='hidden'; inpTo.name='office_target'; inpTo.value = toKey; form.appendChild(inpTo);
      document.body.appendChild(form);
      form.submit();
    });
  });

  // show server flash messages as toast
  const flashEls = document.querySelectorAll('.flash');
  if (flashEls && flashEls.length>0) {
    flashEls.forEach(fe => {
      showToast(fe.textContent, 2200);
    });
  }
});
