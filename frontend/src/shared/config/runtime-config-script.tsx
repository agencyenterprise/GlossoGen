import { RUNTIME_CONFIG_GLOBAL, readServerRuntimeConfig } from "./runtime-config";

/**
 * Server Component that publishes the runtime config to the browser.
 *
 * Renders a blocking inline script in `<head>`, so the global is present
 * before any client bundle evaluates. Must be rendered by the root layout
 * ahead of anything that reads runtime config.
 *
 * Only values safe to expose publicly belong here — the backend URL and the
 * Clerk *publishable* key. Secrets must never be added to `RuntimeConfig`;
 * this script's contents are visible in page source.
 */
export function RuntimeConfigScript() {
  const config = readServerRuntimeConfig();
  // JSON.stringify twice: the inner call serializes the config, the outer
  // produces a valid JS string literal with quotes and backslashes escaped.
  // `</script>` inside a value would otherwise close the tag early.
  const serialized = JSON.stringify(JSON.stringify(config)).replace(/</g, "\\u003c");
  return (
    <script
      dangerouslySetInnerHTML={{
        __html: `window.${RUNTIME_CONFIG_GLOBAL}=JSON.parse(${serialized});`,
      }}
    />
  );
}
