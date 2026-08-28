export function parseRoute(hash = location.hash) {
  const value = hash.replace(/^#\/?/, "");
  const parts = value.split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "test" && parts[1]) return { name: "test", id: parts[1] };
  if (["run", "tests", "report"].includes(parts[0])) return { name: parts[0] };
  return { name: "run" };
}

export function startRouter(onRoute) {
  const dispatch = () => onRoute(parseRoute());
  window.addEventListener("hashchange", dispatch);
  if (!location.hash) history.replaceState(null, "", "#/run");
  dispatch();
  return () => window.removeEventListener("hashchange", dispatch);
}

export function testHref(id) {
  return `#/test/${encodeURIComponent(id)}`;
}
