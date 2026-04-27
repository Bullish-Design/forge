(() => {
  // ── Trigger Button ──────────────────────────────────
  const trigger = document.createElement("button");
  trigger.id = "forge-trigger";
  trigger.setAttribute("aria-label", "Open Forge overlay");
  trigger.innerHTML = `<span aria-hidden="true">\u2692</span><span class="forge-badge"></span>`;
  document.body.appendChild(trigger);

  trigger.addEventListener("click", () => {
    console.log("[forge-overlay] trigger clicked");
  });
})();
