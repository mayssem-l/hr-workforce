(() => {
  "use strict";

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("form[data-loading-form]");
    if (!form || event.defaultPrevented) {
      return;
    }

    form.setAttribute("aria-busy", "true");
    form.querySelectorAll('button[type="submit"]').forEach((button) => {
      button.setAttribute("aria-disabled", "true");
      window.requestAnimationFrame(() => {
        button.disabled = true;
      });
    });
  });
})();
