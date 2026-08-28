function updateMarkers(stage, touches) {
  const live = new Set();
  const bounds = stage.getBoundingClientRect();
  for (const touch of touches) {
    const id = String(touch.identifier);
    live.add(id);
    let element = stage.querySelector(`[data-touch-id="${id}"]`);
    if (!element) {
      element = document.createElement("span");
      element.className = "contact touch";
      element.dataset.touchId = id;
      stage.append(element);
    }
    element.style.left = `${touch.clientX - bounds.left}px`;
    element.style.top = `${touch.clientY - bounds.top}px`;
    element.textContent = `touch ${id}`;
  }
  stage.querySelectorAll("[data-touch-id]").forEach((element) => {
    if (!live.has(element.dataset.touchId)) element.remove();
  });
}

export function setupTouchTest(stage, onEvidence) {
  const events = [];
  let highWater = 0;
  let sawStart = false;

  const record = (event) => {
    event.preventDefault();
    if (event.type === "touchstart") sawStart = true;
    highWater = Math.max(highWater, event.touches.length);
    updateMarkers(stage, event.touches);
    const evidence = {
      type: event.type,
      touches: event.touches.length,
      targetTouches: event.targetTouches.length,
      changedTouches: event.changedTouches.length,
      identifiers: Array.from(event.touches, (touch) => touch.identifier),
      highWater,
      at: new Date().toISOString()
    };
    events.push(evidence);
    if (events.length > 80) events.shift();
    const complete = sawStart && ["touchend", "touchcancel"].includes(event.type);
    onEvidence({ active: event.touches.length, highWater, events: [...events], complete, latest: evidence });
  };

  const options = { passive: false };
  for (const type of ["touchstart", "touchmove", "touchend", "touchcancel"]) {
    stage.addEventListener(type, record, options);
  }
  return () => {
    for (const type of ["touchstart", "touchmove", "touchend", "touchcancel"]) {
      stage.removeEventListener(type, record, options);
    }
  };
}
