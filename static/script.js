// ------------------------------
// Selecionar tudo
// ------------------------------
document.addEventListener("DOMContentLoaded", () => {

    const selectAll = document.getElementById("select-all");
    if (selectAll) {
        selectAll.addEventListener("change", () => {
            document.querySelectorAll(".row-select").forEach(ch => {
                ch.checked = selectAll.checked;
            });
        });
    }

});


// ------------------------------
// Ação: Mover registros
// ------------------------------
function moverPara(escritorio) {
    if (!escritorio || escritorio === "") {
        alert("Selecione um escritório válido.");
        return false;
    }

    return confirm("Deseja realmente mover para " + escritorio + "?");
}


// ------------------------------
// Ação: Excluir registro
// ------------------------------
function confirmarExclusao() {
    return confirm("Tem certeza que deseja excluir este registro?");
}


// ------------------------------
// Ação: Restaurar registro
// ------------------------------
function confirmarRestaurar() {
    return confirm("Deseja restaurar este registro?");
}


// ------------------------------
// Warn about bulk restore/delete without selection
// ------------------------------
function validarSelecao() {
    const marcados = document.querySelectorAll(".row-select:checked");
    if (marcados.length === 0) {
        alert("Nenhum registro selecionado.");
        return false;
    }
    return true;
}
