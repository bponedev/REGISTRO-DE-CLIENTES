// static/script.js
document.addEventListener('DOMContentLoaded', function () {

  // 1. Lógica para Selecionar Todos (.row-select)
  const selectAll = document.querySelector('#select-all, #select-all-ex');
  if (selectAll) {
    selectAll.addEventListener('change', () => {
      document.querySelectorAll('.row-select').forEach(cb => cb.checked = selectAll.checked);
    });
  }

  // 2. Lógica para Excluir Selecionados
  const btnDeleteSelected = document.querySelector('#btn-delete-selected');
  if (btnDeleteSelected) {
    btnDeleteSelected.addEventListener('click', () => {
      const selected = Array.from(document.querySelectorAll('.row-select:checked')).map(cb => cb.value);
      if (!selected.length) { alert('Nenhum registro selecionado.'); return; }
      if (!confirm('Deseja realmente excluir os registros selecionados?')) return;

      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/delete_selected';
      
      // Adiciona IDs selecionados
      selected.forEach(id => {
        const inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'ids';
        inp.value = id;
        form.appendChild(inp);
      });

      // Captura o 'office' da URL ou de algum campo escondido se existir
      const officeParam = new URLSearchParams(window.location.search).get('office');
      if (officeParam) {
          const officeInput = document.createElement('input');
          officeInput.type = 'hidden';
          officeInput.name = 'table';
          officeInput.value = officeParam;
          form.appendChild(officeInput);
      }
      
      document.body.appendChild(form);
      form.submit();
    });
  }

  // 3. Lógica para Restaurar Selecionados (na página de excluídos)
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
  
  // 4. Lógica de confirmação para formulários individuais (Excluir/Restaurar)
  document.querySelectorAll('form[data-confirm="true"]').forEach(form => {
    form.addEventListener('submit', (e) => {
      const msg = form.getAttribute('data-confirm-message') || 'Deseja prosseguir?';
      if (!confirm(msg)) {
        e.preventDefault();
      }
    });
  });

});
