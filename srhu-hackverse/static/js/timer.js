/**
 * Simple client-side presentation countdown.
 * Markup: <span data-timer data-seconds="360"></span>
 */
(function () {
  document.querySelectorAll("[data-timer]").forEach((el) => {
    let remaining = parseInt(el.dataset.seconds || "0", 10);
    function render() {
      const m = String(Math.floor(remaining / 60)).padStart(2, "0");
      const s = String(remaining % 60).padStart(2, "0");
      el.textContent = `${m}:${s}`;
    }
    render();
    const interval = setInterval(() => {
      remaining = Math.max(0, remaining - 1);
      render();
      if (remaining === 0) clearInterval(interval);
    }, 1000);
  });
})();
