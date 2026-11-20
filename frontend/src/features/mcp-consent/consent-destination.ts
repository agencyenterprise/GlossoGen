/**
 * How the consent page names the place an approved authorization code is sent.
 *
 * Anyone can register an OAuth client, under any name, with a callback on their own
 * server. The callback is what decides who ends up holding a token for the group, so
 * the page shows it, and says it stays on the visitor's computer only for a loopback
 * HTTP callback. A custom scheme opens whichever app claims it, and some
 * (`intent:`, `microsoft-edge:`) hand the URL on to a web page, so it is never
 * treated as local.
 */

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

/**
 * Where an approved code goes, as the consent page shows it: `loopback` is an
 * application on this computer, `web` is whoever runs `origin`, and `app` is
 * whichever app opens `scheme` links.
 */
export type ConsentDestination =
  | { kind: "loopback"; origin: string }
  | { kind: "web"; origin: string }
  | { kind: "app"; scheme: string };

/** Describes `redirectUri` for the consent page; throws when it is not a URL. */
export function describeConsentDestination(redirectUri: string): ConsentDestination {
  let url: URL;
  try {
    url = new URL(redirectUri);
  } catch {
    throw new Error(`The OAuth client's callback URL is not a valid URL: ${redirectUri}`);
  }
  const protocol = url.protocol.toLowerCase();
  if (protocol === "http:" || protocol === "https:") {
    if (LOOPBACK_HOSTS.has(url.hostname.toLowerCase())) {
      return { kind: "loopback", origin: url.origin };
    }
    return { kind: "web", origin: url.origin };
  }
  return { kind: "app", scheme: protocol };
}
