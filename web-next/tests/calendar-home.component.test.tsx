import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CalendarHome } from "../components/calendar/calendar-home";

afterEach(() => {
  cleanup();
  mock.restoreAll();
});

async function arrange(response: { status: string; message: string; event_id?: string }) {
  let refreshes = 0;
  mock.method(console, "error", () => {});
  mock.method(globalThis, "fetch", async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      return Response.json(response, { status: 201 });
    }
    refreshes++;
    return Response.json({ events: [], total: 0, time_min: "", time_max: "" });
  });
  render(<CalendarHome />);
  await screen.findByText(/brak wydarzeń w wybranym zakresie/i);
  fireEvent.click(screen.getByRole("button", { name: /nowy termin/i }));
  fireEvent.change(screen.getByLabelText(/tytuł/i), { target: { value: "Fikcyjna próba" } });
  fireEvent.submit(screen.getByLabelText(/tytuł/i).closest("form")!);
  return () => refreshes;
}

test("keeps the calendar form open when HTTP 201 contains an executor error", async () => {
  const refreshes = await arrange({ status: "error", message: "Wpis nie został potwierdzony." });
  assert.ok(await screen.findByText(/wpis nie został potwierdzony/i));
  assert.equal((screen.getByLabelText(/tytuł/i) as HTMLInputElement).value, "Fikcyjna próba");
  assert.equal(refreshes(), 1);
});

test("refreshes the calendar and closes the form after a confirmed creation", async () => {
  const refreshes = await arrange({ status: "success", message: "Utworzono wpis.", event_id: "test-event" });
  await waitFor(() => assert.ok(!screen.queryByLabelText(/tytuł/i)));
  assert.equal(refreshes(), 2);
});
