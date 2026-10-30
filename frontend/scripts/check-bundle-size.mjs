// Bundle budget (HIMS-PLAT-015): fails the build check when any JavaScript file in dist/assets
// is larger than the budget, so the first download stays small. Run after `npm run build`.
// If a new library pushes a file over the budget, load it on demand (route-level lazy loading)
// instead of raising the limit.
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const BUDGET_KB = 500;
const dir = join(import.meta.dirname, "..", "dist", "assets");
const files = readdirSync(dir).filter((name) => name.endsWith(".js"));
const over = files
  .map((name) => ({ name, kb: statSync(join(dir, name)).size / 1024 }))
  .filter((file) => file.kb > BUDGET_KB);

if (files.length === 0) {
  console.error("No JavaScript found in dist/assets. Run `npm run build` first.");
  process.exit(1);
}
if (over.length > 0) {
  for (const file of over) console.error(`Too large: ${file.name} ${file.kb.toFixed(0)} kB (budget ${BUDGET_KB} kB)`);
  process.exit(1);
}
const largest = Math.max(...files.map((name) => statSync(join(dir, name)).size / 1024));
console.log(`Bundle budget OK: ${files.length} files, largest ${largest.toFixed(0)} kB (budget ${BUDGET_KB} kB).`);
