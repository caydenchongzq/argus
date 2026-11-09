const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(require("node:path").join(__dirname, "static", "app.js"), "utf8");
const definitions = [...source.matchAll(/function moneyLevel\(n[^)]*\)\s*\{[\s\S]*?\n\}/g)];
assert.ok(definitions.length, "moneyLevel function should exist");

// app.js contains the active helper after its agent-panel declarations. Execute
// that actual function body without booting the browser UI.
const moneyLevel = vm.runInNewContext(`(${definitions.at(-1)[0]})`);
assert.equal(moneyLevel(null), null);
assert.equal(moneyLevel(undefined), null);
assert.equal(moneyLevel(""), null);
assert.equal(moneyLevel(0), "$0.0000");
assert.equal(moneyLevel("1.23"), "$1.23");
assert.equal(moneyLevel(Number.NaN), null);
assert.equal(moneyLevel(null) || "unavailable", "unavailable");

console.log("check_money_formatter_offline: ok");
