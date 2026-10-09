/** Export the decorative empty-state originals without flattening alpha. */
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const { values } = parseArgs({ options: { "sharp-module": { type: "string" } } });
const require = createRequire(import.meta.url);
const sharp = require(values["sharp-module"] || "sharp");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(root, "..");
const publicRoot = path.join(repoRoot, "web/public/brand/illustrations");
const sourceRoot = path.join(root, "illustrations/v2/sources");
const manifestPath = path.join(root, "manifest.json");
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
await mkdir(publicRoot, { recursive: true });

for (const variant of ["workspace", "delivery"]) {
  const source = path.join(sourceRoot, `empty-${variant}.png`);
  const metadata = await sharp(source).metadata();
  const alpha = (await sharp(source).stats()).channels[3];
  if (!metadata.hasAlpha || !alpha || alpha.min !== 0 || alpha.max < 1) {
    throw new Error(`Expected transparent alpha in ${variant} source`);
  }
  const outputs = [];
  for (const width of [480, 960]) {
    for (const format of ["png", "webp"]) {
      const target = path.join(publicRoot, `empty-${variant}-${width}.${format}`);
      let pipeline = sharp(source).resize({ width, withoutEnlargement: true });
      pipeline = format === "webp"
        ? pipeline.webp({ quality: 84, alphaQuality: 100, effort: 6 })
        : pipeline.png({ compressionLevel: 9 });
      await pipeline.toFile(target);
      const final = await sharp(target).metadata();
      const finalAlpha = (await sharp(target).stats()).channels[3];
      if (!final.hasAlpha || !finalAlpha || finalAlpha.min !== 0 || finalAlpha.max < 1) {
        throw new Error(`Export lost transparent alpha: ${path.basename(target)}`);
      }
      outputs.push({
        path: path.relative(repoRoot, target).split(path.sep).join("/"),
        bytes: (await stat(target)).size,
        sha256: createHash("sha256").update(await readFile(target)).digest("hex"),
      });
    }
  }
  const asset = manifest.assets.find((item) => item.id === `empty-${variant}`);
  asset.source_sha256 = createHash("sha256").update(await readFile(source)).digest("hex");
  asset.outputs = outputs.sort((left, right) => left.path.localeCompare(right.path));
}
await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
