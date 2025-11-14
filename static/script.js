document.addEventListener('DOMContentLoaded', function () {
  const selectAll = document.querySelector('#select-all');
  if (selectAll) {
    selectAll.addEventListener('change', () => {
      document.querySelectorAll('.row-select').forEach(cb => cb.checked = selectAll.checked);
    });
  }

  const btnDeleteSelected = document.querySelector('#btn-delete-selected');
  if (btnDeleteSelected) {
    btnDeleteSelected.addEventListener('click', () => {
      const selected = Array.from(document.querySelectorAll('.row-select:checked')).map(cb => cb.value);
      if (!selected.length) { alert('Nenhum registro selecionado.'); return; }
      if (!confirm('Deseja realmente excluir os registros selecionados?')) return;
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/delete_selected';
      const officeElem = document.querySelector('input[name="office"]');
      const office = officeElem ? officeElem.value : 'Central';
      const officeField = document.createElement('input');
      officeField.type = 'hidden';
      officeField.name = 'office';
      officeField.value = office;
      form.appendChild(officeField);
      selected.forEach(id => {
        const inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'ids';
        inp.value = id;
        form.appendChild(inp);
      });
      document.body.appendChild(form);
      form.submit();
    });
  }

  const btnRestoreSelected = document.querySelector('#btn-restore-selected');
  if (btnRestoreSelected) {
    btnRestoreSelected.addEventListener('click', () => {
      const selected = Array.from(document.querySelectorAll('.row-select:checked')).map(cb => cb.value);
      if (!selected.length) { alert('Nenhum registro selecionado.'); return; }
      if (!confirm('Deseja realmente restaurar os registros selecionados?')) return;
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/restore_selected';
      selected.forEach(id => {
        const inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'ids';
        inp.value = id;
        form.appendChild(inp);
      });
      document.body.appendChild(form);
      form.submit();
    });
  }
});
