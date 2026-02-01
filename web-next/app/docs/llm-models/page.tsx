import { Panel } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";

export const metadata = {
  title: "LLM Models - Venom Cockpit",
  description: "Guide for adding models to Ollama and vLLM",
};

export default function LlmModelsDocsPage() {
  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Dokumentacja"
        title="Modele LLM"
        description="Krótka instrukcja dodawania modeli do Ollama i vLLM."
        as="h1"
        size="lg"
      />
      <Panel
        title="Ollama"
        description="Modele pobierane przez klienta Ollama i widoczne w Cockpit."
      >
        <ol className="list-decimal space-y-2 pl-4 text-sm text-zinc-300">
          <li>Upewnij się, że serwer Ollama jest uruchomiony lokalnie.</li>
          <li>
            Pobierz model poleceniem: <code>ollama pull gemma:2b</code>.
          </li>
          <li>Wróć do Cockpit i wybierz serwer Ollama oraz model.</li>
        </ol>
      </Panel>
      <Panel
        title="vLLM"
        description="Modele w katalogu ./models lub /data/models widoczne dla vLLM."
      >
        <ol className="list-decimal space-y-2 pl-4 text-sm text-zinc-300">
          <li>Skopiuj model do katalogu <code>./models</code> lub <code>/data/models</code>.</li>
          <li>Uruchom serwer vLLM z odpowiednim modelem lub konfiguracja auto-load.</li>
          <li>W Cockpit wybierz serwer vLLM i aktywuj wybrany model.</li>
        </ol>
      </Panel>
      <Panel title="Diagnostyka" description="Gdy model nie pojawia się na liście.">
        <ul className="list-disc space-y-2 pl-4 text-sm text-zinc-300">
          <li>Sprawdź, czy endpoint serwera odpowiada (np. vLLM na 8001).</li>
          <li>Zweryfikuj nazwę modelu w katalogu i zgodność z serwerem.</li>
          <li>Odśwież panel serwerów LLM w Cockpit po zmianach.</li>
        </ul>
      </Panel>
    </div>
  );
}
