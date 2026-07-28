// src/test/setup.js
// Loaded once before every test file (see the `test.setupFiles` entry in
// vite.config.js). Registers jest-dom's extra matchers (toBeInTheDocument,
// toHaveTextContent, etc.) globally so individual test files don't each
// need to import it.
//
// Uses the "/vitest" subpath rather than the bare package: jest-dom's
// default entry point calls `expect.extend(...)` against a *global*
// `expect`, which only exists if vitest's `test.globals` config is turned
// on. This project doesn't set that (test files import `expect` from
// "vitest" explicitly instead), so the plain import blew up with
// "ReferenceError: expect is not defined". The /vitest subpath is jest-dom's
// own Vitest integration — it imports `expect` from "vitest" itself and
// extends that, so it works regardless of the `globals` setting.
import "@testing-library/jest-dom/vitest"

import { afterEach } from "vitest"
import { cleanup } from "@testing-library/react"

// @testing-library/react normally unmounts the previous test's render
// automatically, but only if it finds a *global* `afterEach` at import time
// — which, again, only exists when `test.globals` is on. Without this,
// every test's render stays in the DOM for the next test to trip over: the
// first test in a file passes, then subsequent tests start throwing
// "Found multiple elements..." once two renders' worth of matching markup
// (this test's + a prior test's leftover) coexist in document.body.
// Registering cleanup explicitly here keeps that guarantee without having
// to turn on globals project-wide.
afterEach(() => {
  cleanup()
})
