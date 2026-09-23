/* Mermaid is pinned in mkdocs.yml; this only initializes rendered diagrams. */
if (window.mermaid) {
  window.mermaid.initialize({ startOnLoad: false, theme: "neutral" });
  const renderMermaid = () => window.mermaid.run({ querySelector: ".mermaid" });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderMermaid, { once: true });
  } else {
    renderMermaid();
  }
}
