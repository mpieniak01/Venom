# THE CHAT - Conversational Assistant

## Role

The Chat Agent is a friendly conversational assistant in the Venom system, specializing in natural conversations with users, answering general questions, and managing simple tasks without the need for complex planning.

## Responsibilities

- **Natural Conversation** - Answering questions in a friendly, helpful manner
- **Memory Integration** - Using and saving information to long-term memory
- **Calendar Management** - Integration with Google Calendar (reading, scheduling tasks)
- **General Knowledge** - Answering factual questions
- **Personal Assistant** - Help with daily tasks

## Key Components

### 1. Available Tools

**MemorySkill** (`venom_core/memory/memory_skill.py`):
- `recall(query)` - Retrieve information from long-term memory
- `memorize(content, tags)` - Save important information

**GoogleCalendarSkill** (`venom_core/execution/skills/google_calendar_skill.py`):
- `read_agenda(days_ahead)` - Read calendar for upcoming days
- `schedule_task(summary, start_time, duration_minutes, description)` - Add event

### 2. Operating Principles

**Order of Operations:**
1. **Memory First** - Always check `recall()` for saved information
2. **Use Knowledge** - If found in memory, use in response
3. **Respond Naturally** - Use friendly, concise language
4. **Save Important** - After important conversation consider `memorize()`

**Interaction Examples:**
```
User: "Hi Venom, how are you?"
Chat Agent: "Hi! I'm doing great, thanks. Ready to help!"

User: "What is the capital of France?"
Chat Agent: "The capital of France is Paris."

User: "What do I have planned today?"
Chat Agent: [calls read_agenda(1)]
           "Today you have: 1. Team meeting at 10:00..."

User: "Remember that I like coffee at 8am"
Chat Agent: [calls memorize("User drinks coffee at 8:00", tags=["preferences"])]
           "Got it! Coffee at 8am."
```

### 3. Google Calendar Integration

**Configuration:**
```bash
# In .env
ENABLE_GOOGLE_CALENDAR=true
GOOGLE_CALENDAR_CREDENTIALS_PATH=./data/config/google_calendar_credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=./data/config/google_calendar_token.json
VENOM_CALENDAR_ID=your_calendar_id  # NOT 'primary', separate calendar
```

**Usage Examples:**
```
User: "What do I have tomorrow?"
→ read_agenda(days_ahead=1)

User: "Add meeting with John tomorrow at 2pm"
→ schedule_task("Meeting with John", "2024-01-15T14:00:00", 60)
```

## Detailed Examples

### Example 1: Simple Conversation

```python
from venom_core.agents.chat import ChatAgent

chat = ChatAgent()

# Basic conversation
response = await chat.respond("How's the weather today?")
print(response.message)
# "I don't have real-time weather data, but I can help you find it online!"
```

### Example 2: Memory Usage

```python
# User wants to save preference
response = await chat.respond(
    "Remember that my favorite programming language is Python"
)

# Chat will:
# 1. Detect it's information to memorize
# 2. Call memorize("Favorite language: Python", tags=["preferences"])
# 3. Respond: "I'll remember that you love Python!"

# Later, user asks related question
response = await chat.respond(
    "What programming language should I use for this project?"
)

# Chat will:
# 1. Call recall("programming language preferences")
# 2. Find: "Favorite language: Python"
# 3. Respond: "Based on what I know, you prefer Python. Would you like to use it?"
```

### Example 3: Calendar Management

```python
# Check upcoming events
response = await chat.respond("What's on my calendar this week?")

# Chat will:
# 1. Call read_agenda(days_ahead=7)
# 2. Format events in readable list
# 3. Respond with schedule

# Add new event
response = await chat.respond(
    "Schedule a dentist appointment for Friday at 3pm"
)

# Chat will:
# 1. Parse: "Friday at 3pm"
# 2. Call schedule_task("Dentist appointment", datetime, 60)
# 3. Confirm: "Added dentist appointment for Friday, January 12 at 3:00 PM"
```

### Example 4: Multi-turn Conversation

```python
# Context-aware conversation
conversation = []

# Turn 1
response1 = await chat.respond("I'm learning Python", context=conversation)
conversation.append({"user": "I'm learning Python", "assistant": response1})
# "That's great! Python is an excellent language to learn."

# Turn 2 - Chat remembers context
response2 = await chat.respond("What should I learn first?", context=conversation)
# "For Python beginners, I recommend starting with variables, data types, and basic syntax."
```

## Integration with System

### Execution Flow

```
IntentManager: GENERAL_CHAT
        ↓
ChatAgent.execute(user_message)
        ↓
┌─────────────┬──────────────┬─────────────┐
│ Check Memory│  Process     │  Calendar   │
│  recall()   │  Message     │  (optional) │
└─────────────┴──────────────┴─────────────┘
        ↓
Generate Response
        ↓
Optional: memorize() if important
        ↓
Return to User
```

### Intent Classification

The Orchestrator routes to ChatAgent when:
- Intent is `GENERAL_CHAT`
- Task doesn't require code generation
- Task doesn't require complex planning
- Task is conversational in nature

## Advanced Features

### 1. Context Awareness

```python
# Chat maintains conversation context
chat = ChatAgent(max_context_turns=5)

# Context automatically managed
for message in user_messages:
    response = await chat.respond(message)
    # Last 5 turns kept in context
```

### 2. Personality Configuration

```env
# Configure chat personality
CHAT_PERSONALITY=friendly  # friendly, professional, casual, concise
CHAT_LANGUAGE=en          # en, pl, de
CHAT_RESPONSE_LENGTH=medium  # short, medium, long
```

```python
# Chat adapts tone based on config
# friendly: "Hey! I'd love to help with that!"
# professional: "I can assist you with that request."
# casual: "Sure thing! Let me help."
```

### 3. Smart Memory Triggers

```python
# Auto-detect when to save to memory
triggers = [
    "remember",
    "don't forget",
    "keep in mind",
    "note that",
    "my preference is"
]

# When detected, automatically memorize
if any(trigger in user_message.lower() for trigger in triggers):
    await chat.memorize_from_message(user_message)
```

### 4. Proactive Assistance

```python
# Chat can offer help based on memory
if chat.should_offer_help():
    # Check calendar for upcoming events
    upcoming = await chat.check_upcoming_events()
    
    if upcoming:
        await chat.proactive_reminder(
            "You have a meeting in 30 minutes!"
        )
```

## Configuration

**Environment Variables** (`.env`):
```bash
# Chat settings
ENABLE_CHAT_MEMORY=true
CHAT_MAX_CONTEXT_TURNS=5
CHAT_PERSONALITY=friendly

# Calendar integration
ENABLE_GOOGLE_CALENDAR=true
GOOGLE_CALENDAR_CREDENTIALS_PATH=./data/config/google_calendar_credentials.json

# Memory settings
MEMORY_VECTOR_DB=lancedb
MEMORY_EMBEDDING_MODEL=sentence-transformers
```

## Best Practices

### 1. Natural Language
Users can talk naturally:
- ✅ "What's up for tomorrow?"
- ✅ "Add meeting with Sarah next Tuesday"
- ✅ "Remember I like tea"
- ❌ Don't require formal syntax

### 2. Context Management
```python
# Keep context relevant
if conversation_length > 10:
    # Summarize older messages
    context = await chat.summarize_context(conversation)
```

### 3. Error Handling
```python
try:
    response = await chat.respond(message)
except MemoryError:
    # Graceful fallback without memory
    response = await chat.respond_without_memory(message)
except CalendarError:
    # Inform user calendar unavailable
    response = "I can't access your calendar right now, but I can help with other tasks!"
```

### 4. Privacy
```python
# Don't memorize sensitive data automatically
if chat.contains_sensitive_data(message):
    # Ask for confirmation
    confirmation = await ask_user("This looks sensitive. Should I remember it?")
    if confirmation:
        await chat.memorize(message)
```

## Metrics

```python
{
  "total_conversations": 1500,
  "total_messages": 8500,
  "average_response_time_ms": 850,
  "memory_recalls": 450,
  "memory_saves": 280,
  "calendar_reads": 120,
  "calendar_writes": 45,
  "user_satisfaction": 0.92
}
```

## Common Use Cases

### Daily Assistant
```
"What's on my schedule today?"
"Remind me to call mom tomorrow"
"What time is my dentist appointment?"
```

### Knowledge Retrieval
```
"What's my Wi-Fi password?" (from memory)
"What was the name of that restaurant we liked?"
"Do I have any allergies?" (from saved preferences)
```

### Quick Facts
```
"What's 15% of 200?"
"Convert 100 USD to EUR"
"What time is it in Tokyo?"
```

### Personal Preferences
```
"Remember I'm vegetarian"
"Note that I prefer morning meetings"
"Save this: my favorite color is blue"
```

## API Reference

### ChatAgent Methods

```python
class ChatAgent:
    async def respond(
        self,
        message: str,
        context: Optional[List[Dict]] = None
    ) -> ChatResponse:
        """Generate response to user message"""
        pass
    
    async def memorize(
        self,
        content: str,
        tags: List[str] = []
    ) -> bool:
        """Save information to memory"""
        pass
    
    async def recall(
        self,
        query: str
    ) -> Optional[str]:
        """Retrieve information from memory"""
        pass
    
    async def check_calendar(
        self,
        days_ahead: int = 1
    ) -> List[Event]:
        """Get upcoming calendar events"""
        pass
```

### ChatResponse Model

```python
@dataclass
class ChatResponse:
    message: str                       # Response text
    used_memory: bool                  # Used memory for response
    saved_to_memory: bool              # Saved new memory
    calendar_checked: bool             # Checked calendar
    confidence: float                  # Response confidence 0-1
```

## Related Documentation

- [Memory Layer](MEMORY_LAYER_GUIDE.md) *(Polish only)*
- [Google Calendar Integration](EXTERNAL_INTEGRATIONS.md) *(Polish only)*
- [Orchestrator](../core/flows/orchestrator.py)
- [Intent Recognition](INTENT_RECOGNITION.md) *(Polish only)*

---

**Version:** 1.0
**Last Updated:** 2024-12-30
