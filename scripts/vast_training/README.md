# Vast.ai — środowisko treningowe (lokalny zestaw, 2026-11-01)

## Wybrany stos i gotowe szablony

Vast oferuje szablony oparte na obrazach Docker (m.in. PyTorch). Axolotl publikuje
oficjalny obraz cloud dla Vast, RunPod i innych dostawców: obsługuje LoRA, QLoRA
oraz pełny fine-tuning. Wybraliśmy jeden framework dla tych trzech trybów.
Unsloth może być późniejszym wariantem optymalizacji, nie dodatkową obowiązkową warstwą.

Przypięty obraz amd64, digest i źródłowy tag są w stack.json. Publiczny Docker Hub
potwierdził obraz main-20261101-py3.12-cu130-2.13.0: Python 3.12, CUDA 13.0,
PyTorch 2.13. Zależności Transformers/PEFT/TRL/Datasets/Accelerate/bitsandbytes
pochodzą z tego samego obrazu. Nie instalujemy osobno najnowszych pakietów na starcie.
Dokładne wersje na GPU zapisuje doctor.py, a trening zapisuje pip freeze i manifest.
Wymagane NVIDIA, sterownik >=580 oraz BF16/Ampere lub nowsza architektura.
Przy Blackwell/MoE potrzebny jest oddzielny obraz/kwalifikacja kerneli; ten zestaw
nie deklaruje obsługi wszystkich nowych GPU ani wszystkich architektur modeli.

Nie kopiuj requirements-academy.txt do tego obrazu: lokalny Academy ma inny pin
TRL/Torch i nie jest kwalifikacją środowiska chmurowego. Adaptery importuj dopiero
po sprawdzeniu zgodności modelu bazowego, jego SHA, tokenizera i runtime docelowego.

## Profile początkowe (nie gwarancja zmieszczenia konkretnego modelu)

| Profil | GPU VRAM | RAM hosta | Dysk | Zastosowanie początkowe |
|---|---:|---:|---:|---|
| qlora | 24 GB | 64 GB | 100 GB | 0.5–8B, NF4; zależy od kontekstu/modelu |
| lora | 48 GB | 64 GB | 100 GB | BF16 adaptery, mniejsze modele/konteksty |
| full | 80 GB | 128 GB | 100 GB | pełne wagi, zacznij od 0.5–3B |

Wszystkie profile startowe wynajmują jeden GPU. Dla pełnego 8B+ potrzebny jest
osobny dobór liczby GPU i sharding FSDP/DeepSpeed, zależnie od optymalizatora i kontekstu.
Pamięć GPU nie sumuje się automatycznie. Ten zestaw przygotowuje fine-tuning
istniejącego modelu; trening od losowych wag wymaga oddzielnego przepisu pretraining.
Nie nazywaj pełnego fine-tuningu treningiem modelu od zera.

## Operator: wyszukanie i uruchomienie

W Ubuntu-Venom:

```bash
cd scripts/vast_training
# Gdy CLI nie ma: bash install-cli.sh (uv tool, izolacja od Venoma).
# Użyj istniejącego VAST_API_KEY w środowisku lub istniejącego magazynu CLI.
python3 vast_training.py offers --profile qlora --max-hourly 1
python3 vast_training.py offers --profile qlora --max-hourly 1 --execute
python3 vast_training.py template --profile qlora > template-qlora.json
# Po wybraniu i sprawdzeniu aktualnej oferty:
python3 vast_training.py create --profile qlora --offer NUMER_OFERTY
# Dopiero dodanie --execute do poprzedniego polecenia rzeczywiście wynajmuje GPU.
```

Domyślnie oba polecenia drukują komendę i nie komunikują się z API.
Filtr max-hourly dotyczy dph_total przy zadanym dysku (`--storage 100`); osobno sprawdź transfer,
czas kontraktu, przydzielony RAM i architekturę GPU. create nie jest wyceną ani
ponowną walidacją ceny wybranej oferty. Nie uruchamia treningu ani pobierania modelu.
Wyszukiwanie wymaga `direct_port_count>=1` dla bezpośredniego SSH.
Tworzenie używa `--cancel-unavail`: brak możliwości przydziału kończy się błędem
zamiast utworzyć zatrzymaną instancję. Wrapper zwraca błąd, gdy odpowiedź `--raw` odrzuca utworzenie instancji lub nie potwierdza jego wykonania, nawet przy kodzie wyjścia CLI równym `0`. Zarejestruj publiczny klucz SSH na koncie
Vast przed utworzeniem hosta. Wynajem pozostaje płatny, dopóki go nie zakończysz. Stop może zostawić płatny dysk;
przed destroy pobierz checkpointy, adaptery i raporty. Brak automatycznego destroy.

Możesz też użyć obrazu/parametrów z template-qlora.json w kreatorze własnego
szablonu Vast (to opis ustawień, nie JSON do bezpośredniego POST API).
Pola `search_params`, `pricing_storage_gb` i `cancel_unavail` opisują filtr ofert,
wycenę dysku i zachowanie komendy CLI; nie stanowią gotowego payloadu REST.
Dostęp do konta i jego szablonów sprawdź osobno. Nie zapisuj tokenów w profilu.

Vast w trybie SSH zastępuje entrypoint obrazu i sam zapewnia SSH. Nasz on-start
celowo przygotowuje tylko katalogi; nie uruchamia dodatkowego SSH, Jupytera ani
treningu. Nie zakładaj wykonania `/root/cloud-entrypoint.sh` obrazu Axolotl.
Natywny Granite wymaga osobnego `../remote_training_host/prepare.py` zgodnie z
[instrukcją operatora](../../docs/PL/ZDALNY_TRENING.md); ten szablon uruchamia bazę
hosta, a nie zakwalifikowane środowisko Granite.

Zgodność flag sprawdzono z dokumentacją Vast.ai (2026-11-02):
- [Create instance](https://docs.vast.ai/cli/reference/create-instance)
- [Search offers](https://docs.vast.ai/cli/reference/search-offers)
- [SSH i rejestracja klucza](https://docs.vast.ai/cli/hello-world)
- [Tryb SSH i entrypoint](https://docs.vast.ai/guides/templates/template-settings)

## SSH, dane i gotowość

Przygotuj istniejący ~/.ssh/config (alias vast-training, HostName/Port/User,
IdentityFile, UserKnownHostsFile); sprawdź fingerprint hosta w panelu Vast.
upload.sh wymusza StrictHostKeyChecking=yes i nie zmienia znanych hostów.

```bash
bash upload.sh ~/.ssh/config vast-training
ssh -F ~/.ssh/config -o StrictHostKeyChecking=yes vast-training \
  'cd /workspace/data/vast-training/kit && bash bootstrap.sh qlora'
# Umieść własne dane na urządzeniu chmurowym:
scp -F ~/.ssh/config -o StrictHostKeyChecking=yes train.jsonl \
  vast-training:/workspace/data/vast-training/datasets/train.jsonl
```

bootstrap używa venv obrazu /workspace/axolotl-venv, niczego nie instaluje.
doctor sprawdza importy, wersje, sterownik, BF16, wolny dysk/shared memory i mały
CUDA backward; w QLoRA także rzeczywisty backward NF4 bitsandbytes. Brak fallbacku CPU.
Zapewnij shared memory >=1 GiB (dla większych prac zalecane 8 GiB+); szczegóły kontenera
Vast potwierdź w doctorze. Gotowy SSH nie oznacza gotowego treningu.

Dane JSONL: każda linia ma niepuste text. Dla czatu text musi być wcześniej
sformatowany właściwym chat template modelu; completion uczy na całym tekście.
Nie zmieniamy tutaj istniejących eksportów datasets/messages z Academy.

## Trening na wynajętej maszynie

```bash
cd /workspace/data/vast-training/kit
source /workspace/data/vast-training/env.sh
# Wstaw prawdziwy identyfikator modelu i jego 40-znakowy commit SHA z Hugging Face.
python configure.py --mode qlora --model ORGANIZACJA/MODEL --revision COMMIT_SHA \
  --dataset /workspace/data/vast-training/datasets/train.jsonl \
  --output /workspace/data/vast-training/outputs/run01 \
  --config /workspace/data/vast-training/configs/run01/config.yml --max-steps 100
# Przed dłuższą sesją sprawdź model/dane przy preprocess i krótkim treningu.
axolotl preprocess /workspace/data/vast-training/configs/run01/config.yml
bash train.sh /workspace/data/vast-training/configs/run01/config.yml qlora
# Wznowienie: trzeci argument train.sh = istniejący katalog checkpoint.
```

Dla LoRA/full zmień --mode oraz argument train.sh. Każdy nowy run ma osobny config.
train.sh używa pipefail, blokady równoległego uruchomienia, zapisuje wersje i logi;
checkpointy: co 50 kroków (lub mniej), najwyżej dwa ostatnie. Do pracy bez terminala
użyj tmux w obrazie. /workspace/data nie oznacza automatycznej kopii zapasowej:
zawartość lokalnego dysku instancji może zniknąć po destroy. Trwały wolumen/kopię
zorganizuj osobno. Pobranie wyników przed zakończeniem najmu, np.:

```bash
scp -r -F ~/.ssh/config -o StrictHostKeyChecking=yes \
  vast-training:/workspace/data/vast-training/outputs ./artifacts
```

## Co faktycznie sprawdzono

Publiczny manifest Docker Hub (amd64) i digest; generowanie komend/profili;
testy izolacji dry-run oraz walidacji dataset/model SHA; składnia Bash/Python.
Nie wynajęto GPU, nie pobrano wag, nie wykonano treningu ani zdalnego doctora.
Obsługa konkretnego modelu i wydajność pozostają do kwalifikacji na wybranej maszynie.

Źródła:
- https://docs.vast.ai/guides/templates/introduction
- https://docs.vast.ai/guides/templates/template-settings
- https://docs.axolotl.ai/docs/docker.html
- https://docs.axolotl.ai/docs/installation.html
- https://docs.axolotl.ai/docs/getting-started.html
- https://docs.axolotl.ai/docs/config-reference.html
- https://docs.axolotl.ai/docs/cli.html
- https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html

## Integracja z eksperymentem Granite

Ten zestaw generuje ogólny trening completion/text. Nie jest zamiennikiem
loadera tools + messages ani selektywnych masek Granite. Nie spłaszczaj korpusu
Granite do text w celu uruchomienia tego zestawu: wymagana jest osobna integracja
natywnego szablonu, masek, walidacji i kwalifikacji smoke. Włączenie kodu do repo
nie oznacza zgody na wynajem GPU, wysyłkę danych ani uruchomienie treningu.

Dane, konfiguracje konkretnych sesji i wyniki przechowuj pod ignorowanym
data/training/<eksperyment>/, poza katalogiem kodu.


Wrapper rozpoznaje komunikaty o wznowieniu uwierzytelnienia 2FA poprzedzające
JSON w przypiętym CLI 1.10.0. Jeśli wynik `create` pozostaje niejednoznaczny,
wyświetla polecenie `vastai show instances --raw`. Przed ponownym `create`
sprawdź listę instancji, aby uniknąć drugiego wynajmu. Wrapper sam nie ponawia
zlecenia utworzenia hosta.
