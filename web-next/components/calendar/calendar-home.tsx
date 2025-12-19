"use client";

import { useEffect, useState, useCallback } from "react";
import { CalendarEvent, EventsResponse, CreateEventRequest } from "@/lib/types";
import { CalendarView } from "./calendar-view";
import { EventForm } from "./event-form";

export function CalendarHome() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [timeRangeHours, setTimeRangeHours] = useState(24);

  const fetchEvents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(
        `/api/v1/calendar/events?time_min=now&hours=${timeRangeHours}`
      );

      if (!response.ok) {
        if (response.status === 503) {
          setError("Google Calendar nie jest skonfigurowany. Sprawdź konfigurację ENABLE_GOOGLE_CALENDAR.");
        } else {
          throw new Error(`HTTP ${response.status}`);
        }
        return;
      }

      const data: EventsResponse = await response.json();
      setEvents(data.events);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd podczas pobierania wydarzeń");
    } finally {
      setLoading(false);
    }
  }, [timeRangeHours]);

  const handleCreateEvent = async (eventData: CreateEventRequest) => {
    try {
      const response = await fetch("/api/v1/calendar/event", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(eventData),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || `HTTP ${response.status}`);
      }

      // Refresh events after creating new one
      await fetchEvents();
      setShowForm(false);
    } catch (err) {
      throw err; // Let EventForm handle the error
    }
  };

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white">
            📅 Kalendarz
          </h1>
          <p className="text-sm text-zinc-400 mt-1">
            Synchronizacja z Google Calendar i planowanie zadań
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors"
        >
          {showForm ? "Anuluj" : "+ Nowy termin"}
        </button>
      </div>

      {/* Time Range Filter */}
      <div className="flex gap-2">
        <button
          onClick={() => setTimeRangeHours(8)}
          className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
            timeRangeHours === 8
              ? "bg-emerald-600 text-white"
              : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
          }`}
        >
          8h
        </button>
        <button
          onClick={() => setTimeRangeHours(24)}
          className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
            timeRangeHours === 24
              ? "bg-emerald-600 text-white"
              : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
          }`}
        >
          Dziś
        </button>
        <button
          onClick={() => setTimeRangeHours(168)}
          className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
            timeRangeHours === 168
              ? "bg-emerald-600 text-white"
              : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
          }`}
        >
          Tydzień
        </button>
      </div>

      {/* Event Form */}
      {showForm && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
          <EventForm onSubmit={handleCreateEvent} onCancel={() => setShowForm(false)} />
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="bg-red-950/50 border border-red-900 rounded-lg p-4">
          <p className="text-red-400">❌ {error}</p>
        </div>
      )}

      {/* Loading State */}
      {loading && !error && (
        <div className="flex items-center justify-center py-12">
          <div className="text-zinc-400">Ładowanie wydarzeń...</div>
        </div>
      )}

      {/* Calendar View */}
      {!loading && !error && (
        <CalendarView events={events} onRefresh={fetchEvents} />
      )}
    </div>
  );
}
