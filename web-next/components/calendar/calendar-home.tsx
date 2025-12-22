"use client";

import { useEffect, useState, useCallback } from "react";
import { CalendarEvent, EventsResponse, CreateEventRequest } from "@/lib/types";
import { CalendarView } from "./calendar-view";
import { EventForm } from "./event-form";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { cn } from "@/lib/utils";
import { Calendar } from "lucide-react";

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
      <SectionHeading
        eyebrow="Kalendarz"
        title="📅 Kalendarz"
        description="Synchronizacja z Google Calendar i planowanie zadań"
        as="h1"
        size="lg"
        rightSlot={
          <div className="flex items-center gap-3">
            <Button
              onClick={() => setShowForm(!showForm)}
              variant="secondary"
              size="sm"
              className="bg-emerald-600 text-white hover:bg-emerald-700"
            >
              {showForm ? "Anuluj" : "+ Nowy termin"}
            </Button>
            <Calendar className="page-heading-icon" />
          </div>
        }
      />

      {/* Time Range Filter */}
      <div className="flex gap-2">
        <Button
          onClick={() => setTimeRangeHours(8)}
          size="xs"
          variant="ghost"
          className={cn(
            "rounded-lg px-3 py-1.5 text-sm",
            timeRangeHours === 8
              ? "bg-emerald-600 text-white hover:bg-emerald-600"
              : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
          )}
        >
          8h
        </Button>
        <Button
          onClick={() => setTimeRangeHours(24)}
          size="xs"
          variant="ghost"
          className={cn(
            "rounded-lg px-3 py-1.5 text-sm",
            timeRangeHours === 24
              ? "bg-emerald-600 text-white hover:bg-emerald-600"
              : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
          )}
        >
          Dziś
        </Button>
        <Button
          onClick={() => setTimeRangeHours(168)}
          size="xs"
          variant="ghost"
          className={cn(
            "rounded-lg px-3 py-1.5 text-sm",
            timeRangeHours === 168
              ? "bg-emerald-600 text-white hover:bg-emerald-600"
              : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
          )}
        >
          Tydzień
        </Button>
      </div>

      {/* Event Form */}
      {showForm && (
        <div className="rounded-lg box-muted p-6">
          <EventForm onSubmit={handleCreateEvent} onCancel={() => setShowForm(false)} />
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="rounded-lg border border-red-900 bg-red-950/50 p-4">
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
