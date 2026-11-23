import { describe, expect, it } from "vitest";
import { cx, fmtNum, fmtTime, kindLabel, pct } from "./format";

describe("format utils", () => {
  it("formats numbers and missing values", () => {
    expect(fmtNum(1234)).toBe("1,234");
    expect(fmtNum(0.123456)).toBe("0.123");
    expect(fmtNum(null)).toBe("—");
    expect(pct(0.256)).toBe("25.6%");
  });
  it("treats backend timestamps as UTC", () => {
    expect(fmtTime("2026-03-14T12:00:00")).toContain("12:00:00");
    expect(fmtTime(null)).toBe("—");
  });
  it("joins class names and labels detector kinds", () => {
    expect(cx("a", false, "b")).toBe("a b");
    expect(kindLabel("new_pattern")).toBe("New error pattern");
    expect(kindLabel("custom_kind")).toBe("custom_kind");
  });
});
