document.addEventListener("DOMContentLoaded", function() {
  document.querySelectorAll("[data-kibetu-dropdown]").forEach(function(dropdown) {
    if (dropdown.dataset.kibetuDropdownBound === "1") {
      return;
    }
    dropdown.dataset.kibetuDropdownBound = "1";

    var input = dropdown.querySelector(".bonus-calc-kibetu-input");
    var toggle = dropdown.querySelector(".bonus-calc-kibetu-toggle");
    var options = Array.from(dropdown.querySelectorAll(".bonus-calc-kibetu-option"));

    if (!input) {
      return;
    }

    function setOpen(isOpen) {
      dropdown.classList.toggle("is-open", isOpen);
      input.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }

    function filterOptions() {
      var keyword = input.value.trim().toLowerCase();
      options.forEach(function(option) {
        var searchText = (option.dataset.kibetuSearch || "").toLowerCase();
        option.hidden = keyword && searchText.indexOf(keyword) === -1;
      });
    }

    input.addEventListener("focus", function() {
      filterOptions();
      setOpen(true);
    });

    input.addEventListener("input", function() {
      filterOptions();
      setOpen(true);
    });

    if (toggle) {
      toggle.addEventListener("click", function() {
        filterOptions();
        setOpen(!dropdown.classList.contains("is-open"));
        input.focus();
      });
    }

    options.forEach(function(option) {
      option.addEventListener("mousedown", function(event) {
        event.preventDefault();
      });
      option.addEventListener("click", function() {
        input.value = option.dataset.kibetuValue || "";
        setOpen(false);
        input.blur();
      });
    });

    document.addEventListener("click", function(event) {
      if (!dropdown.contains(event.target)) {
        setOpen(false);
      }
    });
  });
});
