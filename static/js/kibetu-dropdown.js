document.addEventListener("DOMContentLoaded", function() {
  document.querySelectorAll("[data-kibetu-dropdown]").forEach(function(dropdown) {
    if (dropdown.dataset.kibetuDropdownBound === "1") {
      return;
    }
    dropdown.dataset.kibetuDropdownBound = "1";

    var field = dropdown.closest(".bonus-calc-kibetu-field") || dropdown;
    // 選択中の期別は検索条件の行と別行に置いているので、期別欄の親から探す。
    var selectedScope = field.parentNode || field;
    var input = dropdown.querySelector(".bonus-calc-kibetu-input");
    var toggle = dropdown.querySelector(".bonus-calc-kibetu-toggle");
    var options = Array.from(dropdown.querySelectorAll(".bonus-calc-kibetu-option"));
    var openOnFocus = dropdown.dataset.kibetuOpenOnFocus !== "false";
    var submitOnSelect = dropdown.dataset.kibetuSubmitOnSelect === "true";

    // 複数選択モード。実際の検索条件は hidden にカンマ区切りで持ち、
    // 見えている入力欄は候補の絞り込みだけに使う。
    var multiple = dropdown.dataset.kibetuMultiple === "true";
    var valueField = dropdown.querySelector("[data-kibetu-value-field]");
    var selectedArea = selectedScope.querySelector("[data-kibetu-selected-area]");
    var tagsBox = selectedScope.querySelector("[data-kibetu-tags]");
    var hintCount = selectedScope.querySelector("[data-kibetu-count]");

    if (!input) {
      return;
    }

    if (multiple && !valueField) {
      multiple = false;
    }

    var selectedValues = multiple ? splitValues(valueField.value) : [];

    // 入力して絞り込んでいる最中かどうか。候補を開いた直後は必ず全件表示にして、
    // 既に期別が入っていても他の期別へ切り替えられるようにする。
    var filterByKeyword = false;

    function splitValues(raw) {
      var values = [];
      (raw || "").split(",").forEach(function(value) {
        var kibetu = value.trim();
        if (kibetu !== "" && values.indexOf(kibetu) === -1) {
          values.push(kibetu);
        }
      });
      return values;
    }

    function setOpen(isOpen) {
      dropdown.classList.toggle("is-open", isOpen);
      input.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }

    function isSelected(value) {
      if (multiple) {
        return selectedValues.indexOf(value) !== -1;
      }
      return value !== "" && input.value.trim() === value;
    }

    // 選択中の期別に印を付ける。検索前にクリックしただけの状態でも
    // どれを選んでいるか分かるようにする。
    function markSelected() {
      options.forEach(function(option) {
        var selected = isSelected(option.dataset.kibetuValue || "");
        if (selected) {
          option.setAttribute("data-kibetu-selected", "");
        } else {
          option.removeAttribute("data-kibetu-selected");
        }

        var badge = option.querySelector("[data-kibetu-selected-badge]");
        if (badge) {
          badge.hidden = !selected;
        }
      });
    }

    function renderTags() {
      if (!tagsBox) {
        return;
      }

      tagsBox.textContent = "";
      selectedValues.forEach(function(value) {
        var tag = document.createElement("span");
        tag.className = "bonus-calc-kibetu-tag";
        tag.appendChild(document.createTextNode(value));

        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "bonus-calc-kibetu-tag__remove";
        remove.setAttribute("data-kibetu-tag-remove", value);
        remove.setAttribute("aria-label", value + " を外す");
        remove.textContent = "×";
        tag.appendChild(remove);

        tagsBox.appendChild(tag);
      });

      if (selectedArea) {
        selectedArea.hidden = selectedValues.length === 0;
      }
      if (hintCount) {
        hintCount.textContent = String(selectedValues.length);
      }
    }

    function applySelection() {
      valueField.value = selectedValues.join(",");
      renderTags();
      markSelected();
    }

    function toggleValue(value) {
      if (value === "") {
        return;
      }

      var index = selectedValues.indexOf(value);
      if (index === -1) {
        selectedValues.push(value);
      } else {
        selectedValues.splice(index, 1);
      }
      applySelection();
    }

    function filterOptions() {
      var keyword = filterByKeyword ? input.value.trim().toLowerCase() : "";
      options.forEach(function(option) {
        var searchText = (option.dataset.kibetuSearch || "").toLowerCase();
        option.hidden = keyword !== "" && searchText.indexOf(keyword) === -1;
      });
    }

    function visibleOptions() {
      return options.filter(function(option) {
        return !option.hidden;
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

    if (multiple) {
      // 絞り込み文字を入れた状態の Enter は、候補が1件に絞れていればその期別を選ぶ。
      // 絞り込んでいなければ通常どおり検索を実行する。
      input.addEventListener("keydown", function(event) {
        if (event.key !== "Enter") {
          return;
        }
        if (!filterByKeyword || input.value.trim() === "") {
          return;
        }

        var candidates = visibleOptions();
        if (candidates.length !== 1) {
          return;
        }

        event.preventDefault();
        toggleValue(candidates[0].dataset.kibetuValue || "");
        input.value = "";
        filterByKeyword = false;
        filterOptions();
      });

      if (tagsBox) {
        tagsBox.addEventListener("click", function(event) {
          var remove = event.target.closest("[data-kibetu-tag-remove]");
          if (!remove) {
            return;
          }
          event.preventDefault();
          event.stopPropagation();
          toggleValue(remove.getAttribute("data-kibetu-tag-remove") || "");
        });
      }
    }

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
        if (multiple) {
          // 複数選ぶ間はリストを開いたままにして、検索ボタンで実行させる。
          toggleValue(option.dataset.kibetuValue || "");
          return;
        }

        input.value = option.dataset.kibetuValue || "";
        filterByKeyword = false;
        markSelected();
        setOpen(false);
        input.blur();

        // 業績検索では選ぶだけで検索まで走らせる（検索ボタンを押さなくてよい）
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

    if (multiple) {
      renderTags();
    }
    markSelected();
  });
});
