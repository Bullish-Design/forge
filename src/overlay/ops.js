(() => {
  // ── State ───────────────────────────────────────────
  let modalOpen = localStorage.getItem("forge-modal-open") === "true";

  // ── Trigger Button ──────────────────────────────────
  const trigger = document.createElement("button");
  trigger.id = "forge-trigger";
  trigger.setAttribute("aria-label", "Open Forge overlay");
  trigger.innerHTML = `<span aria-hidden="true">\u2692</span><span class="forge-badge"></span>`;
  document.body.appendChild(trigger);

  // ── Backdrop + Modal ────────────────────────────────
  const backdrop = document.createElement("div");
  backdrop.id = "forge-backdrop";
  backdrop.innerHTML = `
    <div id="forge-modal" role="dialog" aria-label="Forge overlay">
      <div class="forge-header">
        <span>Forge</span>
        <button id="forge-close" aria-label="Close">\u2715</button>
      </div>
      <div class="forge-body">
        <p style="color:#94a3b8;">Modal body — content coming in next steps.</p>
      </div>
      <div class="forge-footer">
        <span id="forge-sse-status">SSE: connecting...</span>
        <button id="forge-reload">Reload Page</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);

  // Prevent clicks inside the modal from closing via backdrop
  document.getElementById("forge-modal").addEventListener("click", (e) => {
    e.stopPropagation();
  });

  // ── Open / Close ────────────────────────────────────
  function openModal() {
    modalOpen = true;
    localStorage.setItem("forge-modal-open", "true");
    backdrop.classList.add("open");
    trigger.style.display = "none";
  }

  function closeModal() {
    modalOpen = false;
    localStorage.setItem("forge-modal-open", "false");
    backdrop.classList.remove("open");
    trigger.style.display = "flex";
  }

  trigger.addEventListener("click", openModal);
  backdrop.addEventListener("click", closeModal);
  document.getElementById("forge-close").addEventListener("click", closeModal);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modalOpen) closeModal();
  });

  // ── Reload Button ───────────────────────────────────
  document.getElementById("forge-reload").addEventListener("click", () => {
    location.reload();
  });

  // ── Restore state on load ───────────────────────────
  if (modalOpen) {
    openModal();
  }
})();
