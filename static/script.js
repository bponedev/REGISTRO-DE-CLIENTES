// ===============================================
// Selecionar / desselecionar todos os checkboxes
// ===============================================
document.addEventListener("DOMContentLoaded", () => {
    const selectAll = document.getElementById("select-all");
    const rowSelects = document.querySelectorAll(".row-select");

    if (selectAll) {
        selectAll.addEventListener("change", () => {
            rowSelects.forEach(chk => chk.checked = selectAll.checked);
        });
    }

    // ===============================================
    // Enviar IDs selecionados para exclusão em massa
    // ===============================================
    const deleteForm = document.getElementById("deleteSelectedForm");
    if (deleteForm) {
        deleteForm.addEventListener("submit", (e) => {
            const ids = [...document.querySelectorAll(".row-select:checked")].map(c => c.value);
            if (ids.length === 0) {
                alert("Nenhum item selecionado.");
                e.preventDefault();
                return;
            }

            ids.forEach(id => {
                const input = document.createElement("input");
                input.type = "hidden";
                input.name = "ids";
                input.value = id;
                deleteForm.appendChild(input);
            });

            if (!confirm("Tem certeza que deseja excluir os itens selecionados?")) {
                e.preventDefault();
            }
        });
    }

    // ===============================================
    // Migração em massa
    // ===============================================
    const migrateForm = document.getElementById("migrateForm");
    if (migrateForm) {
        migrateForm.addEventListener("submit", (e) => {
            const ids = [...document.querySelectorAll(".row-select:checked")].map(c => c.value);
            if (ids.length === 0) {
                alert("Nenhum item selecionado para mover.");
                e.preventDefault();
                return;
            }

            ids.forEach(id => {
                const input = document.createElement("input");
                input.type = "hidden";
                input.name = "ids";
                input.value = id;
                migrateForm.appendChild(input);
            });

            if (!confirm("Confirmar migração dos clientes selecionados?")) {
                e.preventDefault();
            }
        });
    }
});
