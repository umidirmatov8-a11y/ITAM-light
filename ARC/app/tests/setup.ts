import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => cleanup());

// jsdom has no canvas; the oscilloscope only needs a 2D context stub.
HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement["getContext"];
// jsdom does not implement scrolling.
Element.prototype.scrollTo = (() => undefined) as unknown as Element["scrollTo"];
