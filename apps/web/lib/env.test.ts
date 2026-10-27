import { describe, expect, it } from "vitest";

import { apiBaseUrl } from "./env";

describe("apiBaseUrl", () => {
  it("falls back to the local API when unset or blank", () => {
    expect(apiBaseUrl(undefined)).toBe("http://localhost:8000");
    expect(apiBaseUrl("  ")).toBe("http://localhost:8000");
  });

  it("strips trailing slashes", () => {
    expect(apiBaseUrl("https://api.example.test//")).toBe("https://api.example.test");
  });
});
