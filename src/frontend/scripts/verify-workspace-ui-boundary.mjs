import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../packages/workspace-ui/src/", import.meta.url));
const forbidden = ["local-features", "localWorkspaceApi", "/api/"];

async function listFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const descendants = await Promise.all(entries.map(async (entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? listFiles(path) : [path];
  }));
  return descendants.flat();
}

const violations = [];
for (const file of await listFiles(root)) {
  const source = await readFile(file, "utf8");
  for (const value of forbidden) {
    if (source.includes(value)) violations.push(`${file}: ${value}`);
  }
}

if (violations.length) {
  throw new Error(`workspace-ui must not reference Local APIs:\n${violations.join("\n")}`);
}
