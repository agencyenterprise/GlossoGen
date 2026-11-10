import { expect, it } from "vitest";
import { navigableConsentRedirect } from "./consent-redirect";

it("passes a loopback callback through unchanged", () => {
  const url = "http://127.0.0.1:33418/callback?code=abc&state=xyz";

  expect(navigableConsentRedirect(url)).toBe(url);
});

it("passes a native client's own scheme", () => {
  const url = "cursor://anysphere.cursor-mcp/oauth/callback?code=abc";

  expect(navigableConsentRedirect(url)).toBe(url);
});

it("refuses a javascript: callback, whatever its case or leading whitespace", () => {
  for (const url of [
    "javascript:alert(document.domain)//?code=abc",
    "JavaScript:alert(1)",
    " javascript:alert(1)",
    "java\tscript:alert(1)",
  ]) {
    expect(() => navigableConsentRedirect(url)).toThrow(/Refusing/);
  }
});

it("refuses data: and vbscript: callbacks", () => {
  expect(() => navigableConsentRedirect("data:text/html,<script>1</script>")).toThrow(/Refusing/);
  expect(() => navigableConsentRedirect("vbscript:msgbox(1)")).toThrow(/Refusing/);
});

it("refuses a callback that is not a URL", () => {
  expect(() => navigableConsentRedirect("not a url")).toThrow(/not a valid URL/);
});
