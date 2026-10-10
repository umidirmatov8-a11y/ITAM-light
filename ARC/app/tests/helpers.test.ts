import { describe, expect, it } from "vitest";

import { joinArgs, splitArgs } from "../src/screens/Apps";
import { defaultParams, describeStep } from "../src/screens/Scenarios";
import { statusTone } from "../src/components/ui";

describe("argument parsing", () => {
  it("splits like Windows command lines", () => {
    expect(splitArgs('--profile "Work Space" -v')).toEqual(["--profile", "Work Space", "-v"]);
    expect(splitArgs('  ""  x ')).toEqual(["", "x"]);
    expect(splitArgs("")).toEqual([]);
  });
  it("round-trips", () => {
    const args = ["--dir", "C:\\Program Files\\X", ""];
    expect(splitArgs(joinArgs(args))).toEqual(args);
  });
});

describe("scenario steps", () => {
  it("describes steps in Russian", () => {
    expect(describeStep({ action: "volume.set", params: { level: 40 } }, () => "")).toBe("Громкость 40%");
    expect(describeStep({ action: "app.launch", params: { app_id: "x" } }, () => "Steam")).toBe("Запустить приложение: Steam");
    expect(describeStep({ action: "explorer.open", params: { folder: "documents" } }, () => "")).toBe("Открыть папку «Документы»");
  });
  it("has defaults for parameterized steps", () => {
    expect(defaultParams("volume.mute")).toEqual({ muted: true });
    expect(defaultParams("window.minimize_all")).toEqual({});
  });
});

describe("status tones", () => {
  it("maps statuses to colors", () => {
    expect(statusTone("done")).toBe("ok");
    expect(statusTone("denied")).toBe("danger");
    expect(statusTone("dry_run")).toBe("warn");
  });
});
