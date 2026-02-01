import { Suspense } from "react";
import { CalendarHome } from "@/components/calendar/calendar-home";

export const metadata = {
  title: "Calendar - Venom Cockpit",
  description: "Calendar and Google Calendar synchronization",
};

export default function CalendarPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[400px] items-center justify-center">
          <div className="text-hint">Loading calendar...</div>
        </div>
      }
    >
      <CalendarHome />
    </Suspense>
  );
}
