# THE CHAT - Conversational Assistant

## Role

Chat Agent is a friendly conversational assistant in the Venom system, specializing in natural conversations with users, answering general questions, and managing simple tasks without the need for complex planning.

## Responsibilities

- **Natural conversation** - Answering questions in a friendly, helpful manner
- **Memory integration** - Using and saving information to long-term memory
- **Calendar management** - Integration with Google Calendar (reading, task scheduling)
- **General knowledge** - Answering factual questions
- **Personal assistant** - Help with daily tasks

## Key Components

### 1. Available Tools

**MemorySkill** (`venom_core/memory/memory_skill.py`):
- `recall(query)` - Retrieve information from long-term memory
- `memorize(content, tags)` - Save important information

**GoogleCalendarSkill** (`venom_core/execution/skills/google_calendar_skill.py`):
- `read_agenda(days_ahead)` - Read calendar for upcoming days
- `schedule_task(summary, start_time, duration_minutes, description)` - Add event

### 2. Operating Principles

**Operation sequence:**
1. **Memory first** - Always check `recall()` for stored information
2. **Use knowledge** - If found in memory, use in response
3. **Respond naturally** - Use friendly, concise language
4. **Save important** - After important conversation consider `memorize()`

**Interaction examples:**
```
User: "Hi Venom, how are you?"
Chat Agent: "Hi! I'm doing great, thank you. Ready to help!"

User: "What is the capital of France?"
Chat Agent: "The capital of France is Paris."

User: "What do I have planned today?"
Chat Agent: [calls read_agenda(1)]
           "Today you have scheduled: 1. Team meeting at 10:00..."

User: "Remember that I like coffee at 8 AM"
Chat Agent: [calls memorize("User drinks coffee at 8:00", tags=["preferences"])]
           "Remembered! Coffee at 8 AM."
```

### 3. Google Calendar Integration

**Configuration:**
```bash
# In .env
ENABLE_GOOGLE_CALENDAR=true
GOOGLE_CALENDAR_CREDENTIALS_PATH=./config/google_calendar_credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=./config/google_calendar_token.json
VENOM_CALENDAR_ID=your_calendar_id  # NOT 'primary', separate calendar
```

**Usage examples:**
```
User: "What do I have tomorrow?"
→ read_agenda(days_ahead=1)

User: "Add meeting with John tomorrow at 2 PM"
→ schedule_task("Meeting with John", "2024-01-15T14:00:00", 60)
```

## System Integration

### Execution Flow

```
IntentManager: GENERAL_CHAT
        ↓
ChatAgent.execute(user_message)
        ↓
ChatAgent:
  1. recall(user_message) - check memory
  2. Generate response (LLM) with memory context
  3. Optionally: read_agenda() for calendar questions
  4. Optionally: memorize() for important information
  5. Return response
```

### Collaboration with Other Agents

- **IntentManager** - Passes general questions (GENERAL_CHAT)
- **MemorySkill** - Long-term conversation memory
- **Orchestrator** - Routes simple queries directly to Chat (without planning)

## Intent Types Handled by Chat

**GENERAL_CHAT:**
- Greetings ("Hi", "Hello")
- General questions ("What is the capital...", "What is...")
- Jokes and small talk
- Calendar commands ("What do I have tomorrow?")
- Memory management ("Remember that...")

**Not handled (passed to other agents):**
- CODE_GENERATION → CoderAgent
- COMPLEX_PLANNING → ArchitectAgent
- RESEARCH → ResearcherAgent
- KNOWLEDGE_SEARCH → LibrarianAgent / MemorySkill

## Configuration

```bash
# In .env
# Model for Chat Agent (usually fast, local)
AI_MODE=LOCAL
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1
LLM_MODEL_NAME=llama3  # or phi3, gemma

# Google Calendar (optional)
ENABLE_GOOGLE_CALENDAR=false

# Long-term memory
MEMORY_ROOT=./data/memory
```

## Metrics and Monitoring

**Key indicators:**
- Average response time (typically <2s for local models)
- Memory usage rate (% queries using `recall`)
- Number of memory saves (per session)
- Number of Google Calendar queries (per day)

## Best Practices

1. **Memory first** - Always check `recall()` before responding
2. **Save important** - Use `memorize()` for preferences, facts about user
3. **Brevity** - Responses short but complete
4. **Naturalness** - Avoid formal language, be friendly
5. **Calendar** - Use separate calendar (NOT 'primary') for Venom tasks

## Known Limitations

- No access to current events (requires ResearcherAgent + WebSearch)
- Google Calendar requires OAuth2 setup (credentials.json)
- Memory is vector-based (semantic), not always precise for dates/numbers
- No management of multiple conversation contexts simultaneously
- **Optimistic UI:** Messages are displayed immediately upon sending (optimistic update) and then reconciled with server status. This ensures conversation fluidity but requires correct ID synchronization (addressed in fix-095b).

## See also

- [THE_RESEARCHER.md](THE_RESEARCHER.md) - Searching current information
- [MEMORY_LAYER_GUIDE.md](../MEMORY_LAYER_GUIDE.md) - How short-term memory works
- [INTENT_RECOGNITION.md](INTENT_RECOGNITION.md) - Intent classification
