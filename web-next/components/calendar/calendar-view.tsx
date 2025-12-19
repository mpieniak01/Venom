"use client";

import { CalendarEvent } from "@/lib/types";

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
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-12 text-center">
        <div className="text-6xl mb-4">📭</div>
        <p className="text-zinc-400 text-lg mb-4">Brak wydarzeń w wybranym zakresie</p>
        <button
          onClick={onRefresh}
          className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg transition-colors"
        >
          Odśwież
        </button>
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
        <p className="text-sm text-zinc-400">
          Znaleziono {events.length} {events.length === 1 ? "wydarzenie" : "wydarzeń"}
        </p>
        <button
          onClick={onRefresh}
          className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-sm transition-colors"
        >
          🔄 Odśwież
        </button>
      </div>

      {/* Events List */}
      <div className="space-y-6">
        {Object.entries(eventsByDate).map(([date, dateEvents]) => (
          <div key={date} className="space-y-3">
            {/* Date Header */}
            <h2 className="text-xl font-semibold text-white border-b border-zinc-800 pb-2">
              {date}
            </h2>

            {/* Events for this date */}
            <div className="space-y-2">
              {dateEvents.map((event, idx) => (
                <div
                  key={event.id || idx}
                  className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 hover:border-zinc-700 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-emerald-400 font-medium">
                          🕒 {formatTime(event.start)} - {formatTime(event.end)}
                        </span>
                      </div>
                      <h3 className="text-white font-semibold mt-1">
                        {event.summary}
                      </h3>
                      {event.description && (
                        <p className="text-zinc-400 text-sm mt-2 whitespace-pre-wrap">
                          {event.description}
                        </p>
                      )}
                      {event.location && (
                        <p className="text-zinc-500 text-sm mt-2">
                          📍 {event.location}
                        </p>
                      )}
                    </div>
                    {event.status && (
                      <span className="px-2 py-1 bg-zinc-800 text-zinc-400 text-xs rounded">
                        {event.status}
                      </span>
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
