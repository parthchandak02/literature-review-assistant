import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach } from "vitest"

// Node 25+ defines globalThis.localStorage as an accessor returning undefined unless
// --localstorage-file is passed, so Vitest's populateGlobal skips copying jsdom's storage.
const jsdomWindow = (globalThis as { jsdom?: { window?: Window } }).jsdom?.window
if (jsdomWindow?.localStorage) {
  Object.defineProperty(globalThis, "localStorage", {
    value: jsdomWindow.localStorage,
    configurable: true,
    writable: true,
    enumerable: true,
  })
}

afterEach(() => {
  cleanup()
  sessionStorage.clear()
  localStorage.clear()
})
