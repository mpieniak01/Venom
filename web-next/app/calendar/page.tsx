import { Suspense } from "react";
import { CalendarHome } from "@/components/calendar/calendar-home";

export const metadata = {
  title: "Kalendarz - Venom Cockpit",
  description: "Kalendarz i synchronizacja z Google Calendar",
};

export default function CalendarPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[400px] items-center justify-center">
          <div className="text-hint">Ładowanie kalendarza...</div>
        </div>
      }
    >
      <CalendarHome />
    </Suspense>
  );
}
