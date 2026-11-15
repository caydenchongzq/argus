const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
require("./static/formatters.js");

const source = fs.readFileSync(require("node:path").join(__dirname, "static", "app.js"), "utf8");
const moneyDefinition = source.match(/function moneyLevel\(n[^)]*\)\s*\{[\s\S]*?\n\}/);
const quantityDefinition = source.match(/function qty\(n\)\s*\{[\s\S]*?\n\}/);
assert.ok(moneyDefinition, "moneyLevel function should exist");
assert.ok(quantityDefinition, "qty function should exist");

// Execute the app's actual wrappers against the formatter module loaded by the
// page, without booting the browser UI.
const globals = { globalThis: { argusFormatters: globalThis.argusFormatters } };
const moneyLevel = vm.runInNewContext(`(${moneyDefinition[0]})`, globals);
const qty = vm.runInNewContext(`(${quantityDefinition[0]})`, globals);
assert.equal(moneyLevel(null), "—");
assert.equal(moneyLevel(undefined), "—");
assert.equal(moneyLevel(""), "—");
assert.equal(moneyLevel(0), "$0.00");
assert.equal(moneyLevel("1.23"), "$1.23");
assert.equal(moneyLevel(Number.NaN), "—");
assert.equal(qty(0.00001), "0.00001");
assert.equal(qty(0.00005), "0.00005");
assert.equal(qty(null), "—");
assert.equal((source.match(/function moneyLevel\(/g) || []).length, 1, "presentation money formatter is not duplicated");

console.log("check_money_formatter_offline: ok");
