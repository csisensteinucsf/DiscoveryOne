import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { parse } from "@babel/parser";
import traverseModule from "@babel/traverse";

const traverse = traverseModule.default ?? traverseModule;
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoot = path.join(projectRoot, "src");
const sourceExtensions = new Set([".js", ".jsx", ".mjs"]);

const browserGlobals = new Set([
  "AbortController", "Array", "ArrayBuffer", "BigInt", "Blob", "Boolean",
  "CustomEvent", "Date", "Element", "Error", "Event", "EventSource", "File",
  "FileReader", "FormData", "HTMLInputElement", "Infinity", "Intl", "JSON",
  "Map", "Math", "MutationObserver", "NaN", "Node", "Number", "Object",
  "Promise", "Reflect", "RegExp", "ResizeObserver", "Set", "String", "Symbol",
  "TextDecoder", "TextEncoder", "TypeError", "URL", "URLSearchParams",
  "Uint8Array", "WeakMap", "WeakSet", "WebSocket", "alert", "atob", "btoa",
  "cancelAnimationFrame", "clearInterval", "clearTimeout", "confirm", "console",
  "decodeURIComponent", "encodeURIComponent", "getComputedStyle", "Headers",
  "crypto", "document", "fetch", "globalThis", "history", "isFinite", "isNaN",
  "localStorage", "location", "navigator", "parseFloat", "parseInt", "performance",
  "prompt", "queueMicrotask", "requestAnimationFrame", "sessionStorage",
  "setInterval", "setTimeout", "structuredClone", "undefined", "window",
]);

function sourceFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(entryPath);
    return sourceExtensions.has(path.extname(entry.name)) ? [entryPath] : [];
  });
}

const failures = [];
for (const filename of sourceFiles(sourceRoot)) {
  const source = fs.readFileSync(filename, "utf8");
  const ast = parse(source, {
    sourceType: "module",
    plugins: ["jsx"],
    errorRecovery: false,
  });

  traverse(ast, {
    ReferencedIdentifier(identifierPath) {
      const { name } = identifierPath.node;
      if (browserGlobals.has(name)) return;

      const binding = identifierPath.scope.getBinding(name);
      if (binding) {
        const referenceStart = identifierPath.node.start;
        const declarationStart = binding.path.node.start;
        const referenceFunction = identifierPath.getFunctionParent()?.node ?? null;
        const declarationFunction = binding.path.getFunctionParent()?.node ?? null;
        const isBlockScopedVariable = binding.path.isVariableDeclarator()
          && (binding.kind === "const" || binding.kind === "let");
        if (
          isBlockScopedVariable
          && Number.isInteger(referenceStart)
          && Number.isInteger(declarationStart)
          && referenceStart < declarationStart
          && referenceFunction === declarationFunction
        ) {
          const location = identifierPath.node.loc?.start ?? { line: 1, column: 0 };
          failures.push({
            file: path.relative(projectRoot, filename),
            line: location.line,
            column: location.column + 1,
            name,
            kind: "used before initialization",
          });
        }
        return;
      }

      const location = identifierPath.node.loc?.start ?? { line: 1, column: 0 };
      failures.push({
        file: path.relative(projectRoot, filename),
        line: location.line,
        column: location.column + 1,
        name,
        kind: "not defined",
      });
    },
  });
}

if (failures.length) {
  console.error("Unsafe frontend references detected:");
  for (const failure of failures) {
    console.error(`${failure.file}:${failure.line}:${failure.column} ${failure.name} (${failure.kind})`);
  }
  process.exitCode = 1;
} else {
  console.log("Frontend reference safety check passed.");
}