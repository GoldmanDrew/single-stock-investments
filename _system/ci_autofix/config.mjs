import { existsSync, readFileSync } from "node:fs";
import YAML from "yaml";

export function loadConfig() {
  const path = ".github/ci-autofix.yml";
  if (!existsSync(path)) return {};
  return YAML.parse(readFileSync(path, "utf8")) || {};
}
