document.addEventListener("DOMContentLoaded", function() {
  document.querySelectorAll("[data-kibetu-dropdown]").forEach(function(dropdown) {
    if (dropdown.dataset.kibetuDropdownBound === "1") {
      return;
    }
    dropdown.dataset.kibetuDropdownBound = "1";

    var input = dropdown.querySelector(".bonus-calc-kibetu-input");
    var toggle = dropdown.querySelector(".bonus-calc-kibetu-toggle");
    var options = Array.from(dropdown.querySelectorAll(".bonus-calc-kibetu-option"));
    var openOnFocus = dropdown.dataset.kibetuOpenOnFocus !== "false";
    var suppressWhenSelected = dropdown.dataset.kibetuSuppressWhenSelected === "true";

    if (!input) {
      return;
    }

    function setOpen(isOpen) {
      dropdown.classList.toggle("is-open", isOpen);
      input.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }

    function isSelectedKibetu() {
      var value = input.value.trim();
      if (!value) {
        return false;
      }
      return options.some(function(option) {
        return (option.dataset.kibetuValue || "") === value;
      });
    }

    function canOpenDropdown() {
      if (suppressWhenSelected && isSelectedKibetu()) {
        return false;
      }
      return true;
    }

    // 選択中の期別に印を付ける。検索前にクリックしただけの状態でも
    // どれを選んでいるか分かるようにする。
    function markSelected() {
      var value = input.value.trim();
      options.forEach(function(option) {
        var isSelected = value !== "" && (option.dataset.kibetuValue || "") === value;
        if (isSelected) {
          option.setAttribute("data-kibetu-selected", "");
        } else {
          option.removeAttribute("data-kibetu-selected");
        }

        var badge = option.querySelector("[data-kibetu-selected-badge]");
        if (badge) {
          badge.hidden = !isSelected;
        }
      });
    }

    function showAllOptions() {
      options.forEach(function(option) {
        option.hidden = false;
      });
    }

    function filterOptions() {
      var keyword = input.value.trim().toLowerCase();

      // 入力値が候補そのものと一致している場合は「選択済みの値」であって
      // 絞り込みキーワードではない。ここで絞り込むと、▾ で開き直したときに
      // 選択中の1件しか出てこなくなるため全件表示に戻す。
      if (!keyword || isSelectedKibetu()) {
        showAllOptions();
        return;
      }

      options.forEach(function(option) {
        var searchText = (option.dataset.kibetuSearch || "").toLowerCase();
        option.hidden = searchText.indexOf(keyword) === -1;
      });
    }

    input.addEventListener("focus", function() {
      if (!openOnFocus || !canOpenDropdown()) {
        return;
      }
      filterOptions();
      setOpen(true);
    });

    input.addEventListener("input", function() {
      filterOptions();
      markSelected();
      if (canOpenDropdown()) {
        setOpen(true);
      } else {
        setOpen(false);
      }
    });

    if (toggle) {
      toggle.addEventListener("click", function() {
        if (dropdown.classList.contains("is-open")) {
          setOpen(false);
          return;
        }
        filterOptions();
        setOpen(true);
        input.focus();
      });
    }

    options.forEach(function(option) {
      option.addEventListener("mousedown", function(event) {
        event.preventDefault();
      });
      option.addEventListener("click", function() {
        input.value = option.dataset.kibetuValue || "";
        markSelected();
        setOpen(false);
        input.blur();
      });
    });

    document.addEventListener("click", function(event) {
      if (!dropdown.contains(event.target)) {
        setOpen(false);
      }
    });

    markSelected();
  });
});
