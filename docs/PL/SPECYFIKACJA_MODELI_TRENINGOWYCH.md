# Specyfikacja modeli przed treningiem

Stan implementacji: **2026-11-14**. W Academy → Trening → Eksperymenty można
rozwinąć karty trzech wariantów. Odczyt pochodzący z kodu jest dostępny przez
`GET /api/v1/academy/experiments/model-specs` na lokalnym backendzie.
Parametry konkretnej próby pochodzą z wybranego profilu i jawnych nadpisań;
porównuj je z kartą przed startem. Karta nie zastępuje wyniku preflightu ani
pomiaru pamięci na wybranej karcie GPU.

| Wariant | Wykonawca i stan | Zakres LoRA | Dane i limit | GPU |
|---|---|---|---|---|
| `LiquidAI/LFM3-Omni-2B` | Lokalny wykonawca Academy | Jawna lista projekcji **tylko** `language_model`: `q_proj`, `k_proj`, `v_proj`, `o_proj`, `in_proj`, `out_proj`, `w1`, `w2`, `w3` | Zatwierdzone polskie dialogi JSONL; maska wybranych tur asystenta; domyślnie `max_tokens=1024`, dopuszczalne 32–4096 | CUDA BF16; dostępna pamięć sprawdzana przed próbą, brak stałej gwarancji VRAM |
| `google/gemma-4-E4B-it` | Oddzielny wykonawca zdalny | Stałe cztery projekcje uwagi tekstowej `q_proj/k_proj/v_proj/o_proj` | Profilowe dane JSONL kodowane natywnie, wybrane tury asystenta; kontekst 4096 | Szacunek 32 GB VRAM dla wspólnej ścieżki LoRA/QLoRA; pomiar i smoke wymagane dla **nowej** konfiguracji |
| `google/gemma-4-12B-it` | Oddzielny wykonawca zdalny | Stałe cztery projekcje uwagi tekstowej `q_proj/k_proj/v_proj/o_proj` | Profilowe dane JSONL kodowane natywnie, wybrane tury asystenta; kontekst 4096 | Szacunek 48 GB VRAM dla wspólnej ścieżki LoRA/QLoRA; smoke na docelowym GPU nadal wymagane |

## Parametry i granice

**Omni:** domyślna receptura ma `rank=4`, `alpha=8`, `dropout=0`,
`learning_rate=0.0002`, `steps=8`, `microbatch=1`, akumulację 1 oraz limit
1024 tokenów. Historyczne domyślne `target_modules=[q_proj,v_proj]` pozostaje
w niskopoziomowym walidatorze dla zgodności pilota, ale nowy profil Academy
bez jawnego zakresu jest odrzucany. Preflight sprawdza faktycznie znalezione
moduły, maski, snapshot i dostępność GPU. Wybór dziewięciu projekcji obejmuje
MLP `w1/w2/w3`; nie wybiera automatycznie wszystkich warstw multimodalnych.

**Gemma 4 E4B i 12B:** każdy wariant ma osobno przypiętą rewizję HF,
loader i hashe metadanych snapshotu. Domyślna receptura to `rank=16`,
`alpha=32`, `dropout=0.05`, `learning_rate=0.00005`, akumulacja 4,
`quantization=nf4`, gradient checkpointing oraz `row_order=family_epoch_v1`.
Wykonawca dopuszcza też BF16 LoRA, ale nie przełącza precyzji samoczynnie.
Natywne kodowanie wyklucza tury kontekstowe ze straty; przekroczenie limitu
rekordu blokuje przygotowanie. Trening wymaga CUDA BF16, pełnego osadzenia
modelu na GPU, zgodnego snapshotu, smoke i wznowienia, potwierdzenia zmiany
adaptera oraz jawnego budżetu aktualizacji. Zależności są przypięte do
Python 3.14.8, Torch 2.15.0, Transformers 5.22.2, PEFT 0.21.2 i
bitsandbytes 0.50.2. Szacunki 32/48 GB **nie** są potwierdzeniem, że model
zmieści się na danym hoście. Każda nowa konfiguracja wymaga świeżej kwalifikacji.

## Decyzja przed uruchomieniem

1. Wybierz **konkretny model, rewizję i profil danych**, nie samą nazwę rodziny.
2. Sprawdź **zakres LoRA**, limit tokenów, maski i rzeczywistą liczbę nadzorowanych
   tokenów. W Omni wąski `q/v` jest świadomym wariantem kontrolnym, nie
   domyślną receptą na poprawę polszczyzny.
3. Sprawdź kwalifikację **tego samego** snapshotu, precyzji, locka i GPU.
   Wynik smoke lub wcześniejszy adapter nie przenosi się między wariantami.
4. Ustal budżet i ocenę względem **własnej bazy** modelu. Sam spadek straty nie
   dowodzi lepszych rozmów; użyj wspólnego dev i niezależnej rezerwy.

Źródła parametrów: [Omni](../../scripts/academy/omni_pl_chat_recipe.py),
[profile Academy](../../venom_core/services/training_experiments/profiles.py),
[Gemma recipe](../../venom_core/services/gemma4_operator/training.py),
[Gemma profile](../../venom_core/services/gemma4_operator/profile.py).
