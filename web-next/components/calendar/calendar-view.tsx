"use client";

import { CalendarEvent } from "@/lib/types";
import { Button } from "@/components/ui/button";

interface CalendarViewProps {
  events: CalendarEvent[];
  onRefresh: () => void;
}

export function CalendarView({ events, onRefresh }: CalendarViewProps) {
  const formatTime = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString("pl-PL", {
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return isoString;
    }
  };

  const formatDate = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString("pl-PL", {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
      });
    } catch {
      return isoString;
    }
  };

  if (events.length === 0) {
    return (
      <div className="rounded-lg box-muted p-12 text-center">
        <div className="text-6xl mb-4">📭</div>
        <p className="text-muted text-lg mb-4">Brak wydarzeń w wybranym zakresie</p>
        <Button
          onClick={onRefresh}
          variant="outline"
          size="sm"
          className="bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
        >
          Odśwież
        </Button>
      </div>
    );
  }

  // Group events by date
  const eventsByDate = events.reduce((acc, event) => {
    const date = formatDate(event.start);
    if (!acc[date]) {
      acc[date] = [];
    }
    acc[date].push(event);
    return acc;
  }, {} as Record<string, CalendarEvent[]>);

  return (
    <div className="space-y-6">
      {/* Refresh Button */}
      <div className="flex justify-between items-center">
        <p className="text-sm text-muted">
          Znaleziono {events.length} {events.length === 1 ? "wydarzenie" : "wydarzeń"}
        </p>
        <Button
          onClick={onRefresh}
          variant="outline"
          size="xs"
          className="bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
        >
          🔄 Odśwież
        </Button>
      </div>

      {/* Events List */}
      <div className="space-y-6">
        {Object.entries(eventsByDate).map(([date, dateEvents]) => (
          <div key={date} className="space-y-3">
            {/* Date Header */}
            <h2 className="heading-h2 border-b border-zinc-800 pb-2">
              {date}
            </h2>

            {/* Events for this date */}
            <div className="space-y-2">
              {dateEvents.map((event, idx) => (
                <div
                  key={event.id || idx}
                  className="rounded-lg box-muted p-4 transition-colors hover:border-zinc-700"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-emerald-400 font-medium">
                          🕒 {formatTime(event.start)} - {formatTime(event.end)}
                        </span>
                      </div>
                      <h3 className="heading-h3 mt-1">
                        {event.summary}
                      </h3>
                      {event.description && (
                        <p className="text-sm text-muted mt-2 whitespace-pre-wrap">
                          {event.description}
                        </p>
                      )}
                      {event.location && (
                        <p className="text-hint mt-2">
                          📍 {event.location}
                        </p>
                      )}
                    </div>
                    {event.status && (
                      <span className="pill-badge text-zinc-400">{event.status}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
