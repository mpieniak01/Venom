"use client";

import { useState, FormEvent, useEffect } from "react";
import { CreateEventRequest } from "@/lib/types";
import { Button } from "@/components/ui/button";

interface EventFormProps {
  readonly onSubmit: (data: CreateEventRequest) => Promise<void>;
  readonly onCancel: () => void;
}

export function EventForm({ onSubmit, onCancel }: EventFormProps) {
  const [formData, setFormData] = useState<CreateEventRequest>({
    title: "",
    start_time: "",
    duration_minutes: 60,
    description: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Set default start time to next hour
  useEffect(() => {
    const now = new Date();
    now.setHours(now.getHours() + 1);
    now.setMinutes(0);
    now.setSeconds(0);
    now.setMilliseconds(0);

    // Format to datetime-local input format (YYYY-MM-DDTHH:mm)
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');

    const defaultTime = `${year}-${month}-${day}T${hours}:${minutes}`;
    setFormData(prev => ({ ...prev, start_time: defaultTime }));
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!formData.title.trim()) {
      setError("Tytuł jest wymagany");
      return;
    }

    if (!formData.start_time) {
      setError("Data i czas rozpoczęcia są wymagane");
      return;
    }

    try {
      setLoading(true);
      setError(null);

      // Konwersja lokalnego czasu z <input type="datetime-local"> na format bez strefy czasowej
      // Backend oczekuje 'YYYY-MM-DDTHH:mm:ss' traktowanego jako czas lokalny, więc nie używamy toISOString() (UTC)
      const isoStartTime =
        formData.start_time.length === 16
          ? `${formData.start_time}:00`
          : formData.start_time.slice(0, 19);

      await onSubmit({
        ...formData,
        start_time: isoStartTime,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd podczas tworzenia wydarzenia");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <h3 className="heading-h3 mb-4">Nowe wydarzenie</h3>

      {/* Title */}
      <div>
        <label htmlFor="title" className="block text-sm font-medium text-zinc-300 mb-2">
          Tytuł *
        </label>
        <input
          type="text"
          id="title"
          value={formData.title}
          onChange={(e) => setFormData({ ...formData, title: e.target.value })}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
          placeholder="Np. Spotkanie z klientem"
          disabled={loading}
        />
      </div>

      {/* Start Time */}
      <div>
        <label htmlFor="start_time" className="block text-sm font-medium text-zinc-300 mb-2">
          Data i czas rozpoczęcia *
        </label>
        <input
          type="datetime-local"
          id="start_time"
          value={formData.start_time}
          onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
          disabled={loading}
        />
      </div>

      {/* Duration */}
      <div>
        <label htmlFor="duration" className="block text-sm font-medium text-zinc-300 mb-2">
          Czas trwania (minuty)
        </label>
        <select
          id="duration"
          value={formData.duration_minutes}
          onChange={(e) => setFormData({ ...formData, duration_minutes: Number.parseInt(e.target.value, 10) })}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
          disabled={loading}
        >
          <option value={15}>15 minut</option>
          <option value={30}>30 minut</option>
          <option value={45}>45 minut</option>
          <option value={60}>1 godzina</option>
          <option value={90}>1.5 godziny</option>
          <option value={120}>2 godziny</option>
          <option value={180}>3 godziny</option>
        </select>
      </div>

      {/* Description */}
      <div>
        <label htmlFor="description" className="block text-sm font-medium text-zinc-300 mb-2">
          Opis (opcjonalnie)
        </label>
        <textarea
          id="description"
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 min-h-[100px]"
          placeholder="Dodatkowe informacje o wydarzeniu..."
          disabled={loading}
        />
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-950/50 border border-red-900 rounded-lg p-3">
          <p className="text-red-400 text-sm">❌ {error}</p>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-3 pt-2">
        <Button
          type="submit"
          disabled={loading}
          variant="secondary"
          className="flex-1 bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-emerald-800"
        >
          {loading ? "Tworzenie..." : "Utwórz wydarzenie"}
        </Button>
        <Button
          type="button"
          onClick={onCancel}
          disabled={loading}
          variant="outline"
          className="bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:bg-zinc-900"
        >
          Anuluj
        </Button>
      </div>
    </form>
  );
}
