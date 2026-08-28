function media(query) {
  try {
    return window.matchMedia(query).matches;
  } catch {
    return null;
  }
}

export function detectEnvironment() {
  const userAgentData = navigator.userAgentData;
  const visualViewport = window.visualViewport;
  const orientation = screen.orientation;
  return {
    browser: {
      userAgent: navigator.userAgent,
      brands: userAgentData && userAgentData.brands ? userAgentData.brands : [],
      mobile: userAgentData && typeof userAgentData.mobile === "boolean" ? userAgentData.mobile : null,
      language: navigator.language
    },
    platform: {
      reportedPlatform: (userAgentData && userAgentData.platform) || navigator.platform || "unknown",
      maxTouchPoints: navigator.maxTouchPoints === undefined ? 0 : navigator.maxTouchPoints,
      hardwareConcurrency: navigator.hardwareConcurrency === undefined ? null : navigator.hardwareConcurrency,
      deviceMemory: navigator.deviceMemory === undefined ? null : navigator.deviceMemory
    },
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio,
      visualViewport: Boolean(visualViewport),
      visualWidth: visualViewport ? visualViewport.width : null,
      visualHeight: visualViewport ? visualViewport.height : null,
      orientation: orientation ? orientation.type : null
    },
    input: {
      pointerEvents: "PointerEvent" in window,
      touchEvents: "TouchEvent" in window || "ontouchstart" in window,
      coarsePointer: media("(pointer: coarse)"),
      finePointer: media("(pointer: fine)"),
      hover: media("(hover: hover)"),
      anyCoarsePointer: media("(any-pointer: coarse)")
    },
    origin: {
      href: location.href,
      origin: location.origin,
      secureContext: window.isSecureContext,
      online: navigator.onLine,
      serviceWorker: "serviceWorker" in navigator,
      standalone: media("(display-mode: standalone)")
    }
  };
}
