(function () {
    function normalize(value) {
        return (value || "").trim();
    }

    function syncBulkToolbar() {
        var changedCells = document.querySelectorAll("td.field-changed");
        var summary = document.querySelector(".js-bulk-changed-summary");
        var saveBtn = document.querySelector(".js-bulk-save-btn");

        if (summary) {
            summary.textContent =
                changedCells.length > 0
                    ? changedCells.length + " 箇所"
                    : "変更なし";
        }
        if (saveBtn) {
            saveBtn.disabled = changedCells.length === 0;
        }
    }

    function syncRowState(row) {
        if (!row) {
            return;
        }
        var hasChanged = row.querySelector("td.field-changed") !== null;
        row.classList.toggle("field-changed-row", hasChanged);
        syncBulkToolbar();
    }

    function initField(input) {
        if (input.dataset.trackChangeInit === "1") {
            return;
        }
        input.dataset.trackChangeInit = "1";

        var original = normalize(input.value);
        input.dataset.originalValue = original;
        var row = input.closest("tr");
        var cell = input.closest("td");

        function sync() {
            var changed = normalize(input.value) !== original;
            if (cell) {
                cell.classList.toggle("field-changed", changed);
            }
            syncRowState(row);
        }

        input.addEventListener("input", sync);
        input.addEventListener("change", sync);
    }

    function initAll() {
        document.querySelectorAll(".js-track-change").forEach(initField);
        syncBulkToolbar();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }
})();
