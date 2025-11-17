document.addEventListener('DOMContentLoaded', function () {
  // select-all on table page
  const selectAll = document.querySelector('#select-all');
  if (selectAll) {
    selectAll.addEventListener('change', () => {
      document.querySelectorAll('.row-select').forEach(cb => cb.checked = selectAll.checked);
    });
  }

  const selectAllExcl = document.querySelector('#select-all-excl');
  if (selectAllExcl) {
    selectAllExcl.addEventListener('change', () => {
      document.querySelectorAll('.row-select').forEach(cb => cb.checked = selectAllExcl.checked);
    });
  }

  // Delete selected
  const btnDeleteSelected = document.querySelector('#btn-delete-selected');
  if (btnDeleteSelected) {
    btnDeleteSelected.addEventListener('click', () => {
      const selected = Array.from(document.querySelectorAll('.row-select:checked')).map(cb => cb.value);
      if (!selected.length) { alert('Nenhum registro selecionado.'); return; }
      if (!confirm('Deseja realmente excluir os registros selecionados?')) return;

      const office = document.querySelector('#office-select') ? document.querySelector('#office-select').value : document.querySelector('input[name="office"]') ? document.querySelector('input[name="office"]').value : 'central';
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/delete_selected';
      selected.forEach(id => {
        const inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'ids';
        inp.value = id;
        form.appendChild(inp);
      });
      const officeField = document.createElement('input');
      officeField.type = 'hidden';
      officeField.name = 'office';
      officeField.value = office;
      form.appendChild(officeField);
      document.body.appendChild(form);
      form.submit();
    });
  }

  // Restore selected (on excluidos page)
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

  // Migrate selected
  const btnMigrateSelected = document.querySelector('#btn-migrate-selected');
  if (btnMigrateSelected) {
    btnMigrateSelected.addEventListener('click', () => {
      const selected = Array.from(document.querySelectorAll('.row-select:checked')).map(cb => cb.value);
      const target = document.querySelector('#migrate-target-select') ? document.querySelector('#migrate-target-select').value : null;
      const officeCurrent = document.querySelector('#office-select') ? document.querySelector('#office-select').value : null;
      if (!selected.length) { alert('Nenhum registro selecionado.'); return; }
      if (!target) { alert('Selecione o escritório destino.'); return; }
      if (!confirm(`Deseja mover ${selected.length} registro(s) para ${target.replace('_',' ')}?`)) return;

      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/migrate_selected';
      selected.forEach(id => {
        const inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'ids';
        inp.value = id;
        form.appendChild(inp);
      });
      const src = document.createElement('input');
      src.type = 'hidden';
      src.name = 'office_current';
      src.value = officeCurrent;
      form.appendChild(src);
      const tgt = document.createElement('input');
      tgt.type = 'hidden';
      tgt.name = 'office_target';
      tgt.value = target;
      form.appendChild(tgt);
      document.body.appendChild(form);
      form.submit();
    });
  }

  // office select change -> go to /table with params preserved
  const officeSelect = document.querySelector('#office-select');
  if (officeSelect) {
    officeSelect.addEventListener('change', () => {
      const office = officeSelect.value;
      // preserve per_page and filters if present
      const per_page = document.querySelector('#per-page-select') ? document.querySelector('#per-page-select').value : '';
      const filtro = document.querySelector('#filtro-select') ? document.querySelector('#filtro-select').value : '';
      const valor = document.querySelector('#valor-search') ? document.querySelector('#valor-search').value : '';
      const data_tipo = document.querySelector('#data-tipo-select') ? document.querySelector('#data-tipo-select').value : '';
      const data_de = document.querySelector('#data-de') ? document.querySelector('#data-de').value : '';
      const data_ate = document.querySelector('#data-ate') ? document.querySelector('#data-ate').value : '';

      let qs = `?office=${encodeURIComponent(office)}`;
      if (per_page) qs += `&per_page=${encodeURIComponent(per_page)}`;
      if (filtro && valor) qs += `&filtro=${encodeURIComponent(filtro)}&valor=${encodeURIComponent(valor)}`;
      if (data_tipo) {
        qs += `&data_tipo=${encodeURIComponent(data_tipo)}`;
        if (data_de) qs += `&data_de=${encodeURIComponent(data_de)}`;
        if (data_ate) qs += `&data_ate=${encodeURIComponent(data_ate)}`;
      }
      window.location.href = '/table' + qs;
    });
  }

  // per-page change
  const perPageSelect = document.querySelector('#per-page-select');
  if (perPageSelect) {
    perPageSelect.addEventListener('change', () => {
      const per = perPageSelect.value;
      const office = document.querySelector('#office-select') ? document.querySelector('#office-select').value : 'central';
      const filtro = document.querySelector('#filtro-select') ? document.querySelector('#filtro-select').value : '';
      const valor = document.querySelector('#valor-search') ? document.querySelector('#valor-search').value : '';
      let qs = `?office=${encodeURIComponent(office)}&per_page=${encodeURIComponent(per)}`;
      if (filtro && valor) qs += `&filtro=${encodeURIComponent(filtro)}&valor=${encodeURIComponent(valor)}`;
      window.location.href = '/table' + qs;
    });
  }

  // search form submit (keep per_page)
  const searchForm = document.querySelector('#search-form');
  if (searchForm) {
    searchForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const filtro = document.querySelector('#filtro-select').value;
      const valor = document.querySelector('#valor-search').value;
      const office = document.querySelector('#office-select') ? document.querySelector('#office-select').value : 'central';
      const per = document.querySelector('#per-page-select') ? document.querySelector('#per-page-select').value : 10;
      let qs = `?office=${encodeURIComponent(office)}&per_page=${encodeURIComponent(per)}&filtro=${encodeURIComponent(filtro)}&valor=${encodeURIComponent(valor)}`;
      window.location.href = '/table' + qs;
    });
  }

  // apply date filter
  const applyDateBtn = document.querySelector('#apply-date-filter');
  if (applyDateBtn) {
    applyDateBtn.addEventListener('click', () => {
      const dataTipo = document.querySelector('#data-tipo-select').value;
      const dataDe = document.querySelector('#data-de').value;
      const dataAte = document.querySelector('#data-ate').value;
      const office = document.querySelector('#office-select') ? document.querySelector('#office-select').value : 'central';
      const per = document.querySelector('#per-page-select') ? document.querySelector('#per-page-select').value : 10;
      let qs = `?office=${encodeURIComponent(office)}&per_page=${encodeURIComponent(per)}`;
      if (dataTipo) {
        qs += `&data_tipo=${encodeURIComponent(dataTipo)}`;
        if (dataDe) qs += `&data_de=${encodeURIComponent(dataDe)}`;
        if (dataAte) qs += `&data_ate=${encodeURIComponent(dataAte)}`;
      }
      window.location.href = '/table' + qs;
    });
  }

  // inline migrate forms: attach confirmation to each (progressive enhancement)
  document.querySelectorAll('.migrate-form').forEach(form => {
    form.addEventListener('submit', (e) => {
      if (!confirm('Mover este registro?')) e.preventDefault();
    });
  });
});
