// src/constants/donorStatus.test.js
import { describe, expect, it } from "vitest"
import { donorStatusBadgeProps } from "./donorStatus"

describe("donorStatusBadgeProps", () => {
  it.each([
    ["available", "clear", "Available"],
    ["reserved", "pending", "Reserved"],
    ["under_workup", "pending", "Under workup"],
    ["transplanted", "neutral", "Transplanted"],
    ["medically_unfit", "fail", "Medically unfit"],
    ["withdrawn", "neutral", "Withdrawn"],
    ["deceased", "neutral", "Deceased"],
  ])("maps donor status %s to badge status %s", (donorStatus, expectedStatus, expectedLabel) => {
    expect(donorStatusBadgeProps(donorStatus)).toEqual({
      status: expectedStatus,
      label: expectedLabel,
    })
  })

  it("falls back to a neutral badge with the raw value for an unrecognized status", () => {
    expect(donorStatusBadgeProps("something_new")).toEqual({
      status: "neutral",
      label: "something_new",
    })
  })
})
