import assert from "node:assert/strict";
import { it, type TestContext } from "node:test";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { VoiceCameraButton } from "../components/voice/voice-camera-button";

function replace(test: TestContext, target: object, name: string, value: unknown) {
  const original = Object.getOwnPropertyDescriptor(target, name);
  Object.defineProperty(target, name, { configurable: true, value });
  test.after(() => {
    if (original) Object.defineProperty(target, name, original);
    else Reflect.deleteProperty(target, name);
  });
}

function mockCamera(test: TestContext) {
  let stopCount = 0;
  const requests: MediaStreamConstraints[] = [];
  const draws: Array<[number, number]> = [];
  const stream = { getTracks: () => [{ stop: () => { stopCount++; } }] };
  replace(test, navigator, "mediaDevices", {
    getUserMedia: async (request: MediaStreamConstraints) => {
      requests.push(request);
      return stream;
    },
  });
  replace(test, window.HTMLMediaElement.prototype, "play", async () => {});
  replace(test, window.HTMLVideoElement.prototype, "videoWidth", 1920);
  replace(test, window.HTMLVideoElement.prototype, "videoHeight", 1080);
  replace(test, window.HTMLCanvasElement.prototype, "getContext", () => ({
    drawImage: (_image: unknown, _x: number, _y: number, w: number, h: number) => draws.push([w, h]),
  }));
  replace(test, window.HTMLCanvasElement.prototype, "toBlob", (callback: BlobCallback) =>
    callback(new Blob(["frame"], { type: "image/jpeg" })));
  test.after(cleanup);
  return { requests, draws, stops: () => stopCount };
}

it("captures one bounded JPEG on demand and stops all tracks before attaching it", async (test) => {
  const camera = mockCamera(test);
  const received: File[] = [];
  const busy: boolean[] = [];
  render(<VoiceCameraButton disabled={false} onBusy={(value) => busy.push(value)} onCapture={(file) => {
    assert.equal(camera.stops(), 1);
    received.push(file);
  }} />);
  assert.equal(camera.requests.length, 0);
  fireEvent.click(screen.getByRole("button", { name: "Zrób zdjęcie kamerą" }));
  await waitFor(() => assert.equal(received.length, 1));
  assert.deepEqual(camera.requests, [{ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false }]);
  assert.deepEqual(camera.draws, [[1280, 720]]);
  assert.deepEqual(busy, [true, false]);
  assert.equal(received[0].type, "image/jpeg");
  assert.equal(received[0].name, "camera-frame.jpg");
});

it("releases a camera granted after the voice controls were closed", async (test) => {
  let grant: (media: object) => void = () => {};
  const request = new Promise<object>((resolve) => { grant = resolve; });
  replace(test, navigator, "mediaDevices", { getUserMedia: () => request });
  const busy: boolean[] = [];
  let stopped = 0;
  let attached = false;
  const view = render(<VoiceCameraButton disabled={false} onBusy={(value) => busy.push(value)}
    onCapture={() => { attached = true; }} />);
  fireEvent.click(screen.getByRole("button", { name: "Zrób zdjęcie kamerą" }));
  await act(async () => view.unmount());
  grant({ getTracks: () => [{ stop: () => { stopped++; } }] });
  await waitFor(() => assert.equal(stopped, 1));
  assert.equal(attached, false);
  assert.deepEqual(busy, [true, false]);
});

it("reports permission denial and allows a subsequent attempt", async (test) => {
  replace(test, navigator, "mediaDevices", {
    getUserMedia: async () => { throw new DOMException("denied", "NotAllowedError"); },
  });
  test.after(cleanup);
  let attached = false;
  render(<VoiceCameraButton disabled={false} onBusy={() => {}} onCapture={() => { attached = true; }} />);
  fireEvent.click(screen.getByRole("button", { name: "Zrób zdjęcie kamerą" }));
  const error = await screen.findByRole("alert");
  assert.match(error.textContent ?? "", /Nie udało się pobrać klatki/);
  assert.equal(attached, false);
  assert.equal(screen.getByRole<HTMLButtonElement>("button", { name: "Zrób zdjęcie kamerą" }).disabled, false);
});
