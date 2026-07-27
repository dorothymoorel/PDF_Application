import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(packageRoot, "..", "..");
const outputPath = resolve(packageRoot, "src", "generated", "schema.ts");
const outputLabel = "packages/api-client/src/generated/schema.ts";
const checkOnly = process.argv.slice(2).includes("--check");

const python = [
  "import json",
  "from transloka_api.main import app",
  "print(json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True, separators=(',', ':')))",
].join("; ");

const exported = spawnSync("uv", ["run", "python", "-c", python], {
  cwd: repositoryRoot,
  encoding: "utf8",
  shell: false,
});

if (exported.error) {
  throw exported.error;
}
if (exported.status !== 0) {
  process.stderr.write(exported.stderr || "OpenAPI export failed.\n");
  process.exit(exported.status ?? 1);
}

const schema = JSON.parse(exported.stdout);
const operationIds = [];
for (const pathItem of Object.values(schema.paths ?? {})) {
  for (const operation of Object.values(pathItem)) {
    if (operation && typeof operation === "object" && "operationId" in operation) {
      operationIds.push(operation.operationId);
    }
  }
}

if (operationIds.some((value) => typeof value !== "string" || value.length === 0)) {
  throw new Error("Every OpenAPI operation must have a stable operation ID.");
}
if (new Set(operationIds).size !== operationIds.length) {
  throw new Error("OpenAPI operation IDs must be unique.");
}

const schemaNames = Object.keys(schema.components?.schemas ?? {});
if (new Set(schemaNames).size !== schemaNames.length) {
  throw new Error("OpenAPI schema names must be unique.");
}

const ast = await openapiTS(schema);
const generated = [
  "// This file is generated. Do not edit manually.",
  "",
  astToString(ast).trimEnd(),
  "",
].join("\n");

if (checkOnly) {
  let current;
  try {
    current = readFileSync(outputPath, "utf8").replaceAll("\r\n", "\n");
  } catch {
    process.stderr.write(`Generated API schema is missing: ${outputLabel}\n`);
    process.exit(1);
  }

  if (current !== generated) {
    process.stderr.write(
      `Generated API schema is out of date: ${outputLabel}. Run the generate script.\n`,
    );
    process.exit(1);
  }
  process.stdout.write("Generated API schema is current.\n");
} else {
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, generated, "utf8");
  process.stdout.write(`Generated ${outputLabel}.\n`);
}
