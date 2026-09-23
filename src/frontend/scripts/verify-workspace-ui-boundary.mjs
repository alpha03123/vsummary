import { readdir, readFile } from "node:fs/promises";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "@babel/parser";

const root = fileURLToPath(new URL("../packages/workspace-ui/src/", import.meta.url));
const packageRoot = resolve(root, "..");
const packageManifest = JSON.parse(await readFile(join(packageRoot, "package.json"), "utf8"));
const allowedPackages = new Set([
  ...Object.keys(packageManifest.dependencies ?? {}),
  ...Object.keys(packageManifest.peerDependencies ?? {}),
  ...Object.keys(packageManifest.devDependencies ?? {}),
]);

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
  const imports = [];
  collectImports(parse(source, { sourceType: "module", plugins: ["jsx"] }).program, imports);
  for (const imported of imports) {
    if (imported === null) {
      violations.push(`${file}: dynamic import specifier must be a literal`);
      continue;
    }
    if (imported.startsWith(".")) {
      const importedPath = resolve(file, "..", imported);
      if (relative(root, importedPath).startsWith("..")) {
        violations.push(`${file}: relative import escapes workspace-ui source: ${imported}`);
      }
      continue;
    }
    const dependency = imported.startsWith("@") ? imported.split("/").slice(0, 2).join("/") : imported.split("/")[0];
    if (!allowedPackages.has(dependency)) {
      violations.push(`${file}: undeclared external dependency: ${imported}`);
    }
  }
}

if (violations.length) {
  throw new Error(`workspace-ui imports must remain package-local or declared package dependencies:\n${violations.join("\n")}`);
}

function collectImports(node, imports) {
  if (node === null || typeof node !== "object") return;
  if (node.type === "ImportDeclaration" || node.type === "ExportAllDeclaration" || node.type === "ExportNamedDeclaration") {
    if (node.source) imports.push(node.source.value);
  } else if (node.type === "ImportExpression") {
    imports.push(node.source.type === "StringLiteral" ? node.source.value : null);
  } else if (node.type === "CallExpression" && node.callee.type === "Import") {
    const [source] = node.arguments;
    imports.push(source?.type === "StringLiteral" ? source.value : null);
  }
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) {
      for (const item of value) collectImports(item, imports);
    } else if (value !== null && typeof value === "object" && value.type) {
      collectImports(value, imports);
    }
  }
}
