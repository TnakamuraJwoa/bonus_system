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
    var submitOnSelect = dropdown.dataset.kibetuSubmitOnSelect === "true";

    if (!input) {
      return;
    }

    // 入力して絞り込んでいる最中かどうか。候補を開いた直後は必ず全件表示にして、
    // 既に期別が入っていても他の期別へ切り替えられるようにする。
    var filterByKeyword = false;

    function setOpen(isOpen) {
      dropdown.classList.toggle("is-open", isOpen);
      input.setAttribute("aria-expanded", isOpen ? "true" : "false");
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

    function filterOptions() {
      var keyword = filterByKeyword ? input.value.trim().toLowerCase() : "";
      options.forEach(function(option) {
        var searchText = (option.dataset.kibetuSearch || "").toLowerCase();
        option.hidden = keyword !== "" && searchText.indexOf(keyword) === -1;
      });
    }

    function openDropdown() {
      filterByKeyword = false;
      filterOptions();
      setOpen(true);
    }

    function submitForm() {
      var form = input.form;
      if (!form) {
        return;
      }
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        form.submit();
      }
    }

    input.addEventListener("focus", function() {
      if (!openOnFocus) {
        return;
      }
      openDropdown();
    });

    input.addEventListener("input", function() {
      filterByKeyword = true;
      filterOptions();
      markSelected();
      setOpen(true);
    });

    if (toggle) {
      toggle.addEventListener("click", function() {
        if (dropdown.classList.contains("is-open")) {
          setOpen(false);
          return;
        }
        openDropdown();
        input.focus();
      });
    }

    options.forEach(function(option) {
      option.addEventListener("mousedown", function(event) {
        event.preventDefault();
      });
      option.addEventListener("click", function() {
        input.value = option.dataset.kibetuValue || "";
        filterByKeyword = false;
        markSelected();
        setOpen(false);
        input.blur();

        // 業務検索では選ぶだけで検索まで走らせる（検索ボタンを押さなくてよい）
        if (submitOnSelect) {
          submitForm();
        }
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
