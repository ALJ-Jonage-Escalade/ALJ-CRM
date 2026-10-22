import { describe, expect, it } from "vitest";
import { looksLikeEmail } from "./email";

describe("looksLikeEmail", () => {
  it.each([["a@b.fr", true], ["a@b", false], ["pas-une-adresse", false], ["a b@c.fr", false], ["", false]])("%s: %s", (value, ok) => {
    expect(looksLikeEmail(value)).toBe(ok);
  });
});
