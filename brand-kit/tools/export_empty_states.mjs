/** Export committed imagegen originals without redrawing or flattening alpha. */
import { createRequire } from "node:module";
import { mkdir, copyFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const { values } = parseArgs({ options: { "sharp-module": { type: "string" } } });
const require = createRequire(import.meta.url);
const sharp = require(values["sharp-module"] || "sharp");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicRoot = path.resolve(root, "../web/public/brand/illustrations");
const sourceRoot = path.join(root, "illustrations/v2/sources");
const exportRoot = path.join(root, "illustrations/v2/web");
await mkdir(exportRoot, { recursive: true });
await mkdir(publicRoot, { recursive: true });

const exports = [];
for (const variant of ["workspace", "delivery"]) {
  const source = path.join(sourceRoot, `empty-${variant}.png`);
  const metadata = await sharp(source).metadata();
  const statistics = await sharp(source).stats();
  const alpha = statistics.channels[3];
  if (!metadata.hasAlpha || !alpha || alpha.min !== 0 || alpha.max < 1) {
    throw new Error(`Expected genuine transparent alpha in ${variant} source`);
  }
  for (const width of [480, 960]) {
    for (const format of ["png", "webp"]) {
      const name = `empty-${variant}-${width}.${format}`;
      const target = path.join(exportRoot, name);
      let pipeline = sharp(source).resize({ width, withoutEnlargement: true });
      pipeline = format === "webp"
        ? pipeline.webp({ quality: 84, alphaQuality: 100, effort: 6 })
        : pipeline.png({ compressionLevel: 9 });
      await pipeline.toFile(target);
      await copyFile(target, path.join(publicRoot, name));
      const final = await sharp(target).metadata();
      const finalAlpha = (await sharp(target).stats()).channels[3];
      if (!final.hasAlpha || !finalAlpha || finalAlpha.min !== 0 || finalAlpha.max < 1) {
        throw new Error(`Export lost transparent alpha: ${name}`);
      }
      exports.push({ name, width: final.width, height: final.height, bytes: (await stat(target)).size });
    }
  }
}
await writeFile(path.join(exportRoot, "exports.json"), JSON.stringify(exports, null, 2) + "\n");
process.stdout.write(JSON.stringify(exports, null, 2) + "\n");
