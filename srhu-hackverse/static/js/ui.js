(function () {
  // Mobile sidebar toggle
  const hamburger = document.querySelector(".topbar__hamburger");
  const sidebar = document.querySelector(".sidebar");
  const backdrop = document.querySelector(".sidebar-backdrop");

  function closeSidebar() {
    sidebar && sidebar.classList.remove("open");
    backdrop && backdrop.classList.remove("open");
  }

  if (hamburger && sidebar) {
    hamburger.addEventListener("click", () => {
      sidebar.classList.toggle("open");
      backdrop && backdrop.classList.toggle("open");
    });
  }
  backdrop && backdrop.addEventListener("click", closeSidebar);

  // Generic modal open/close via data attributes:
  // data-modal-target="#id" opens, data-modal-close closes
  document.querySelectorAll("[data-modal-target]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = document.querySelector(btn.dataset.modalTarget);
      target && target.classList.add("open");
    });
  });
  document.querySelectorAll("[data-modal-close]").forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.closest(".modal-backdrop").classList.remove("open");
    });
  });

  // Prevent double-submit on any form marked data-guard-submit
  document.querySelectorAll("form[data-guard-submit]").forEach((form) => {
    form.addEventListener("submit", () => {
      const btn = form.querySelector("[type=submit]");
      if (btn) {
        btn.disabled = true;
        btn.dataset.originalText = btn.innerHTML;
        btn.innerHTML = '<span class="spinner"></span> Please wait...';
      }
    });
  });
})();
