import { describe, expect, it } from "vitest";
import { describeConsentDestination } from "./consent-destination";

describe("describeConsentDestination", () => {
  it("names a remote callback by its origin", () => {
    expect(describeConsentDestination("https://collector.example/cb?x=1")).toEqual({
      kind: "web",
      origin: "https://collector.example",
    });
  });

  it("treats a loopback callback as this computer", () => {
    expect(describeConsentDestination("http://localhost:33418/callback")).toEqual({
      kind: "loopback",
      origin: "http://localhost:33418",
    });
    expect(describeConsentDestination("HTTP://LOCALHOST/callback").kind).toBe("loopback");
    expect(describeConsentDestination("http://127.0.0.1/callback").kind).toBe("loopback");
    expect(describeConsentDestination("http://[::1]:9000/callback").kind).toBe("loopback");
    expect(describeConsentDestination("http://user@localhost/callback").kind).toBe("loopback");
  });

  it("does not treat a host that only starts with localhost as this computer", () => {
    expect(describeConsentDestination("https://localhost.collector.example/cb")).toEqual({
      kind: "web",
      origin: "https://localhost.collector.example",
    });
  });

  it("names a custom scheme without calling it local", () => {
    expect(describeConsentDestination("cursor://anysphere.cursor-mcp/oauth/callback")).toEqual({
      kind: "app",
      scheme: "cursor:",
    });
  });

  it("does not treat schemes that hand the URL to a browser as local", () => {
    expect(
      describeConsentDestination(
        "intent://collector.example/cb#Intent;scheme=https;package=com.android.chrome;end"
      )
    ).toEqual({ kind: "app", scheme: "intent:" });
    expect(describeConsentDestination("microsoft-edge:https://collector.example/cb")).toEqual({
      kind: "app",
      scheme: "microsoft-edge:",
    });
  });

  it("refuses a value that is not a URL", () => {
    expect(() => describeConsentDestination("not a url")).toThrow(/not a valid URL/);
  });
});
