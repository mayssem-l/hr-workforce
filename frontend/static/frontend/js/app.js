(() => {
  "use strict";

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("form[data-loading-form]");
    if (!form || event.defaultPrevented) {
      return;
    }

    if (form.getAttribute("aria-busy") === "true") {
      event.preventDefault();
      return;
    }

    form.setAttribute("aria-busy", "true");
    const loadingStatus = form.querySelector("[data-loading-status]");
    if (loadingStatus) {
      loadingStatus.hidden = false;
    }
    form.querySelectorAll('button[type="submit"]').forEach((button) => {
      button.setAttribute("aria-disabled", "true");
      const loadingLabel = button.getAttribute("data-loading-label");
      if (loadingLabel) {
        button.textContent = loadingLabel;
      }
      window.requestAnimationFrame(() => {
        button.disabled = true;
      });
    });
  });
})();
