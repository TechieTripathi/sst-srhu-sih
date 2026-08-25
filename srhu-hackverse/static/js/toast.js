/**
 * One reusable toast component used everywhere in the app.
 * Usage: showToast("Team created successfully", "success")
 */
(function () {
  function ensureContainer() {
    let el = document.querySelector(".toast-container");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast-container";
      document.body.appendChild(el);
    }
    return el;
  }

  window.showToast = function (message, type) {
    type = type || "info";
    const container = ensureContainer();
    const toast = document.createElement("div");
    toast.className = "toast " + type;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 200ms ease";
      setTimeout(() => toast.remove(), 220);
    }, 3800);
  };

  // Render any server-side flash messages (data-flash elements) as toasts.
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-flash]").forEach((node) => {
      window.showToast(node.dataset.flash, node.dataset.flashType || "info");
    });
  });
})();
