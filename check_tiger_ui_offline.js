// Credential-free check for stale and out-of-order Tiger preview responses.
const assert = require("node:assert/strict");
require("./static/tiger-preview-guard.js");

const current = globalThis.argusTigerPreviewIsCurrent;
assert.equal(typeof current, "function");

// Request 2 belongs to account B and resolves first. A later response from the
// older request for account A must not replace it after the selection changed.
assert.equal(current(2, 2, "account-B", "account-B", "account-B", true), true);
assert.equal(current(1, 2, "account-A", "account-B", "account-A", true), false);
assert.equal(current(2, 2, "account-B", "account-B", "account-A", true), false);
assert.equal(current(2, 2, "account-B", "account-B", "account-B", false), false);

console.log("argus Tiger UI offline check: ok (out-of-order, account binding, closed dialog)");
