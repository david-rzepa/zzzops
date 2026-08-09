import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const schema = JSON.parse(await readFile(path.join(root, ".github/schemas/agent-plugins-1.0.0-plugin.schema.json")));
const manifest = JSON.parse(await readFile(path.join(root, "plugins/zzzops/plugin.json")));
const validate = new Ajv2020({ allErrors: true, strict: true }).compile(schema);

assert.equal(validate(manifest), true, JSON.stringify(validate.errors));
assert.equal(manifest.$schema, schema.$id);
console.log(`Validated ${manifest.name} against Agent Plugins ${manifest.$schema}`);
