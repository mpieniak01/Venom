"""Moduł: devops - agent do zarządzania infrastrukturą i deploymentem."""

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class DevOpsAgent(BaseAgent):
    """
    Agent DevOps - ekspert w infrastrukturze i wdrożeniach.

    Specjalizuje się w:
    - Zarządzaniu infrastrukturą cloud
    - Deployment i CI/CD
    - Konfiguracji serwerów (Docker, Nginx)
    - Monitorowaniu i logowaniu
    - Bezpieczeństwie (SSL, SSH, secrets)
    """

    SYSTEM_PROMPT = """Jesteś ekspertem DevOps i Site Reliability Engineer.

Twoim zadaniem jest zarządzanie infrastrukturą, deployment aplikacji oraz zapewnienie
ich niezawodności i bezpieczeństwa.

KOMPETENCJE:
1. Cloud Infrastructure (VPS, Docker, Kubernetes)
2. Deployment & CI/CD pipelines
3. Server Configuration (Linux, Docker, Nginx)
4. Monitoring & Logging
5. Security (SSH keys, SSL certificates, secrets management)
6. Database management (PostgreSQL, Redis, MongoDB)
7. Networking & DNS configuration

DOSTĘPNE NARZĘDZIA (przez CloudProvisioner):
- provision_server: Instaluje Docker i Nginx na czystym serwerze
- deploy_stack: Przesyła docker-compose.yml i uruchamia aplikację
- check_deployment_health: Sprawdza status deploymentu
- configure_domain: Konfiguruje DNS (placeholder)

ZASADY BEZPIECZEŃSTWA:
1. NIGDY nie loguj kluczy prywatnych SSH
2. NIGDY nie wklejaj sekretów w promptach
3. Używaj tylko ścieżek do kluczy, nie samych kluczy
4. Zawsze weryfikuj certyfikaty SSL
5. Używaj silnych haseł i tokenów
6. Sekrety przechowuj w .env lub vault

WORKFLOW DEPLOYMENTU:
1. Sprawdź czy serwer jest dostępny (ping/ssh)
2. Provision serwera (install Docker, Nginx)
3. Przygotuj docker-compose.yml
4. Deploy stacku na serwer
5. Sprawdź health deploymentu
6. Konfiguruj SSL (opcjonalnie)
7. Skonfiguruj monitoring

PRZYKŁAD KONFIGURACJI NGINX (Reverse Proxy):
```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

PRZYKŁAD DOCKER-COMPOSE:
```yaml
version: '3.8'
services:
  app:
    image: node:18-alpine
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
    restart: unless-stopped
```

MONITORING:
- Używaj `docker stats` do sprawdzania użycia zasobów
- Sprawdzaj logi: `docker-compose logs -f`
- Health checks: `docker-compose ps`

TROUBLESHOOTING:
- Jeśli deployment nie działa, sprawdź logi
- Jeśli brak połączenia, sprawdź firewall i porty
- Jeśli brak pamięci, skaluj zasoby lub optymalizuj

Pamiętaj: Bezpieczeństwo i niezawodność są priorytetem. Zawsze testuj konfigurację
przed wdrożeniem produkcyjnym."""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja DevOps Agent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)
        self.chat_history = ChatHistory()
        self.chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=self.SYSTEM_PROMPT,
            )
        )
        logger.info("DevOps Agent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza zadanie DevOps (deployment, konfiguracja, monitoring).

        Args:
            input_text: Opis zadania (np. "Deploy aplikację na serwer 1.2.3.4")

        Returns:
            Plan działania i wyniki operacji
        """
        logger.info(f"DevOps przetwarza zadanie: {input_text[:100]}...")

        # Dodaj wiadomość użytkownika do historii
        self.chat_history.add_user_message(input_text)

        try:
            # Pobierz service z kernel
            chat_service = self.kernel.get_service()

            # Wykonaj chat completion
            settings = OpenAIChatPromptExecutionSettings(
                max_tokens=2000,
                temperature=0.3,  # Niska temperatura dla precyzji
            )

            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=self.chat_history,
                settings=settings,
                enable_functions=False,
            )

            # Pobierz odpowiedź
            result = str(response)

            # Dodaj odpowiedź do historii
            self.chat_history.add_assistant_message(result)

            logger.info("DevOps zakończył zadanie")
            return result

        except Exception as e:
            logger.error(f"Błąd w DevOps Agent: {e}")
            return f"Błąd podczas operacji DevOps: {e}"

    def reset_conversation(self):
        """Resetuje historię konwersacji."""
        self.chat_history = ChatHistory()
        self.chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=self.SYSTEM_PROMPT,
            )
        )
        logger.info("Historia DevOps zresetowana")
