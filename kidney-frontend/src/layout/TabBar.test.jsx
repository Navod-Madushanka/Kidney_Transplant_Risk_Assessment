// src/layout/TabBar.test.jsx
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import TabBar from "./TabBar"

describe("TabBar — dead links (review #2 bug 22)", () => {
  it("links only to real routes, not the removed /calculator or /history", () => {
    render(
      <MemoryRouter>
        <TabBar />
      </MemoryRouter>
    )

    expect(screen.getByRole("link", { name: /new check/i })).toHaveAttribute(
      "href",
      "/checks/new"
    )
    expect(screen.getByRole("link", { name: /reports/i })).toHaveAttribute("href", "/reports")
    expect(screen.queryByRole("link", { name: /calculator/i })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /history/i })).not.toBeInTheDocument()
  })

  it("includes a Paired Exchange link, previously missing entirely", () => {
    render(
      <MemoryRouter>
        <TabBar />
      </MemoryRouter>
    )

    expect(screen.getByRole("link", { name: /exchange/i })).toHaveAttribute("href", "/exchange")
  })
})
