/**
 * The check the consent page runs on the OAuth client's callback URL before it
 * navigates there.
 *
 * The page assigns the URL to `window.location.href`, and a `javascript:` URL
 * assigned there runs in this origin, with the visitor signed in. The backend
 * refuses such redirect URIs when a client registers and when consent is approved;
 * this refuses them again at the point of navigation, since the approval endpoint
 * belongs to the identity provider. Native clients' own schemes (`cursor://`,
 * `vscode://`) pass.
 */

const SCRIPT_PROTOCOLS = new Set(["javascript:", "vbscript:", "data:", "blob:"]);

/** Returns `url` when the consent page may navigate to it, and throws otherwise. */
export function navigableConsentRedirect(url: string): string {
  let protocol: string;
  try {
    protocol = new URL(url).protocol;
  } catch {
    throw new Error(`The OAuth client's callback URL is not a valid URL: ${url}`);
  }
  if (SCRIPT_PROTOCOLS.has(protocol.toLowerCase())) {
    throw new Error(`Refusing to open the OAuth client's callback URL (${protocol})`);
  }
  return url;
}
