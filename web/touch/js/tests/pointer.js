function marker(stage, pointer) {
  let element = stage.querySelector(`[data-pointer-id="${pointer.pointerId}"]`);
  if (!element) {
    element = document.createElement("span");
    element.className = "contact";
    element.dataset.pointerId = pointer.pointerId;
    stage.append(element);
  }
  const bounds = stage.getBoundingClientRect();
  element.style.left = `${pointer.clientX - bounds.left}px`;
  element.style.top = `${pointer.clientY - bounds.top}px`;
  element.textContent = `${pointer.pointerType || "pointer"} ${pointer.pointerId}`;
  return element;
}

export function setupPointerTest(stage, onEvidence) {
  const active = new Map();
  const events = [];
  let highWater = 0;
  let sawDown = false;

  const record = (event) => {
    const evidence = {
      type: event.type,
      pointerId: event.pointerId,
      pointerType: event.pointerType,
      isPrimary: event.isPrimary,
      pressure: event.pressure,
      width: event.width,
      height: event.height,
      buttons: event.buttons,
      x: Math.round(event.clientX),
      y: Math.round(event.clientY),
      at: new Date().toISOString()
    };
    events.push(evidence);
    if (events.length > 80) events.shift();
    onEvidence({ active: active.size, highWater, events: [...events], complete: false, latest: evidence });
  };

  const down = (event) => {
    sawDown = true;
    active.set(event.pointerId, marker(stage, event));
    highWater = Math.max(highWater, active.size);
    withCapture(stage, event.pointerId);
    record(event);
  };
  const move = (event) => {
    if (!active.has(event.pointerId)) return;
    active.set(event.pointerId, marker(stage, event));
    record(event);
  };
  const finish = (event) => {
    const contact = active.get(event.pointerId);
    if (contact) contact.remove();
    active.delete(event.pointerId);
    record(event);
    onEvidence({
      active: active.size,
      highWater,
      events: [...events],
      complete: sawDown,
      latest: events[events.length - 1]
    });
  };
  stage.addEventListener("pointerdown", down);
  stage.addEventListener("pointermove", move);
  stage.addEventListener("pointerup", finish);
  stage.addEventListener("pointercancel", finish);

  return () => {
    stage.removeEventListener("pointerdown", down);
    stage.removeEventListener("pointermove", move);
    stage.removeEventListener("pointerup", finish);
    stage.removeEventListener("pointercancel", finish);
  };
}

function withCapture(stage, pointerId) {
  try {
    stage.setPointerCapture(pointerId);
  } catch {
    // Some synthesized or legacy pointers cannot be captured; the event remains valid evidence.
  }
}
