/**
 * Live preview of the evaluation total. This is a UX convenience only —
 * the Flask backend recalculates and validates every score on submit,
 * so nothing here is treated as authoritative.
 */
(function () {
  const sliders = document.querySelectorAll("[data-criterion-score]");
  const totalEl = document.querySelector("[data-preview-total]");
  const pctEl = document.querySelector("[data-preview-percentage]");

  function recalc() {
    let total = 0, max = 0;
    sliders.forEach((s) => {
      total += Number(s.value);
      max += Number(s.dataset.max || 10);
      const valueEl = s.parentElement.querySelector(".criterion-row__score-value");
      if (valueEl) valueEl.textContent = `${s.value} / ${s.dataset.max || 10}`;
    });
    if (totalEl) totalEl.textContent = `${total} / ${max}`;
    if (pctEl) pctEl.textContent = max ? `${((total / max) * 100).toFixed(1)}%` : "0%";
  }

  sliders.forEach((s) => s.addEventListener("input", recalc));
  recalc();

  // Confirm-before-submit modal
  const submitBtn = document.querySelector("[data-submit-evaluation]");
  const confirmModal = document.querySelector("#confirmSubmitModal");
  const form = document.querySelector("#evaluationForm");

  if (submitBtn && confirmModal && form) {
    submitBtn.addEventListener("click", (e) => {
      e.preventDefault();
      confirmModal.classList.add("open");
    });
    const confirmBtn = confirmModal.querySelector("[data-confirm-submit]");
    confirmBtn.addEventListener("click", () => {
      confirmBtn.disabled = true;
      confirmBtn.innerHTML = '<span class="spinner"></span> Submitting...';
      const hiddenAction = document.createElement("input");
      hiddenAction.type = "hidden";
      hiddenAction.name = "action";
      hiddenAction.value = "submit";
      form.appendChild(hiddenAction);
      form.submit();
    });
  }
})();
