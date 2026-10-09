import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const sourceFile = path.resolve("src/lib/utils.ts");
const compiledSource = ts.transpileModule(readFileSync(sourceFile, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

// Separate processes give Date/Intl a real timezone from startup, including on
// Windows. No fake Date parser or global timezone mutation can hide the bug.
const probe = `
const { readFileSync } = require("node:fs");
const Module = require("node:module");
const path = require("node:path");
const input = JSON.parse(readFileSync(0, "utf8"));
const moduleUnderTest = new Module(input.sourceFile);
moduleUnderTest.filename = input.sourceFile;
moduleUnderTest.paths = Module._nodeModulePaths(path.dirname(input.sourceFile));
moduleUnderTest._compile(input.compiledSource, input.sourceFile);
const utils = moduleUnderTest.exports;
global.document = { documentElement: { lang: "pl" } };
const now = new Date("2026-10-09T12:00:20Z").getTime();
Date.now = () => now;
const naive = "2026-10-09T12:00:00.123456";
const explicit = "2026-10-09T12:00:00.123456Z";
const parsed = utils.parseApiTimestamp(naive);
const localCalendar = new Date(2026, 9, 9);
const lateEvent = utils.parseApiTimestamp("2026-10-09T23:30:00");
const result = {
  zone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  naive: parsed.toISOString(), explicit: utils.parseApiTimestamp(explicit).toISOString(),
  positiveOffset: utils.parseApiTimestamp("2026-10-09T14:00:00.123+02:00").toISOString(),
  negativeOffset: utils.parseApiTimestamp("2026-10-09T08:00:00.123-04:00").toISOString(),
  relativeNaive: utils.relativeTime(naive), relativeExplicit: utils.relativeTime(explicit),
  displayNaive: utils.formatDateTime(naive), displayExplicit: utils.formatDateTime(explicit),
  dateOnlyPreserved: utils.parseApiTimestamp("2026-10-09").getTime() === new Date("2026-10-09").getTime(),
  timeOnlyPreserved: Number.isNaN(utils.parseApiTimestamp("12:30").getTime()) === Number.isNaN(new Date("12:30").getTime()),
  localCalendarHour: localCalendar.getHours(),
  lateLocalDay: lateEvent.getDate(),
  daylightOverlapDifference: utils.parseApiTimestamp("2026-10-25T01:30:00").getTime() - utils.parseApiTimestamp("2026-10-25T00:30:00").getTime(),
  winterNaive: utils.parseApiTimestamp("2026-01-09T12:00:00").toISOString(),
  explicitOffsetPreserved: utils.parseApiTimestamp("2026-10-25T02:30:00+01:00").toISOString(),
};
process.stdout.write(JSON.stringify(result));
`;

describe("UTC API timestamps in actual local timezones", () => {
  it.each([
    ["UTC", 9],
    ["Europe/Warsaw", 10],
    ["America/New_York", 9],
  ])("keeps event instants and local calendar days correct in %s", (zone, lateLocalDay) => {
    const child = spawnSync(process.execPath, ["-e", probe], {
      cwd: process.cwd(), env: { ...process.env, TZ: zone },
      input: JSON.stringify({ sourceFile, compiledSource }), encoding: "utf8", timeout: 20_000,
    });
    expect(child.status, child.stderr).toBe(0);
    const result = JSON.parse(child.stdout);
    expect(result.zone).toBe(zone);
    expect(result.naive).toBe("2026-10-09T12:00:00.123Z");
    expect(result.explicit).toBe(result.naive);
    expect(result.positiveOffset).toBe(result.naive);
    expect(result.negativeOffset).toBe(result.naive);
    expect(result.relativeNaive).toBe("przed chwilą");
    expect(result.relativeNaive).toBe(result.relativeExplicit);
    expect(result.displayNaive).toBe(result.displayExplicit);
    expect(result.dateOnlyPreserved).toBe(true);
    expect(result.timeOnlyPreserved).toBe(true);
    expect(result.localCalendarHour).toBe(0);
    expect(result.lateLocalDay).toBe(lateLocalDay);
    expect(result.daylightOverlapDifference).toBe(60 * 60 * 1000);
    expect(result.winterNaive).toBe("2026-01-09T12:00:00.000Z");
    expect(result.explicitOffsetPreserved).toBe("2026-10-25T01:30:00.000Z");
  });
});
