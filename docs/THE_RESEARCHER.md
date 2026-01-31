# THE RESEARCHER - Knowledge Synthesis & Web Search

## Role

Researcher Agent is a research expert in the Venom system, specializing in finding and synthesizing knowledge from the Internet. It provides current documentation, code examples, best practices, and information about libraries and tools.

## Responsibilities

- **Information search** - Finding current data on the Internet (DuckDuckGo, Google Grounding)
- **Content extraction** - Downloading and cleaning text from web pages (trafilatura)
- **Knowledge synthesis** - Aggregating information from multiple sources into coherent response
- **Repository search** - Finding libraries and tools on GitHub
- **HuggingFace integration** - Finding models and datasets
- **Memory management** - Saving important knowledge to LanceDB

## Key Components

### 1. Available Tools

**WebSearchSkill** (`venom_core/execution/skills/web_skill.py`):
- `search(query, max_results)` - Internet search (DuckDuckGo)
- `scrape_text(url)` - Text extraction from page (trafilatura)
- `search_and_scrape(query, max_pages)` - Search and download content from top results

**GitHubSkill** (`venom_core/execution/skills/github_skill.py`):
- `search_repos(query, language, max_results)` - Repository search
- `get_repo_details(repo_name)` - Repository details
- `get_readme(repo_name)` - Repository README.md

**HuggingFaceSkill** (`venom_core/execution/skills/huggingface_skill.py`):
- `search_models(query, task, max_results)` - ML model search
- `search_datasets(query, max_results)` - Dataset search
- `get_model_details(model_id)` - Model details

**MemorySkill** (`venom_core/memory/memory_skill.py`):
- `save_fact(content, tags)` - Saves knowledge to LanceDB
- `search_memory(query)` - Searches vector memory

### 2. Google Grounding Integration (Gemini)

Researcher can use **Google Search Grounding** when Gemini API is available:

```python
# Automatic source addition to response
response_metadata = {
  "grounding_metadata": {
    "grounding_chunks": [
      {"title": "FastAPI Documentation", "uri": "https://fastapi.tiangolo.com/"},
      {"title": "Pydantic V2", "uri": "https://docs.pydantic.dev/"}
    ]
  }
}

# Output format:
"""
Agent response...

---
📚 Sources (Google Grounding):
[1] FastAPI Documentation - https://fastapi.tiangolo.com/
[2] Pydantic V2 - https://docs.pydantic.dev/
"""
```

**Google Grounding Advantages:**
- Always current results (Google Index)
- Automatic source citation
- Higher quality responses than DuckDuckGo
- Zero extraction costs (scraping) - text already in context

**Configuration:**
```bash
# In .env
GOOGLE_API_KEY=your_key_here
AI_MODE=HYBRID  # or CLOUD
HYBRID_CLOUD_PROVIDER=google
```

### 3. Usage Examples

**Example 1: Library documentation**
```
User: "How to use FastAPI with PostgreSQL?"
Action:
1. search("FastAPI PostgreSQL tutorial")
2. scrape_text(top_results[0])
3. save_fact(knowledge_synthesis, tags=["fastapi", "postgresql"])
4. Return response with examples
```

**Example 2: Repository search**
```
User: "Find library for JSON parsing in Python"
Action:
1. search_repos("JSON parser", language="python")
2. get_readme(top_repo)
3. Return description + link
```

**Example 3: ML model**
```
User: "Find model for sentiment analysis"
Action:
1. search_models("sentiment analysis", task="text-classification")
2. get_model_details(top_model)
3. Return description + usage instructions
```

**Example 4: Current price/information**
```
User: "What's the current price of Bitcoin?"
Action (with Google Grounding):
1. LLM Gemini with tools=[google_search_retrieval]
2. Automatic search + synthesis
3. Return response with sources
```

## System Integration

### Execution Flow

```
ArchitectAgent creates plan:
  Step 1: RESEARCHER - "Find PyGame documentation"
        ↓
TaskDispatcher calls ResearcherAgent.execute()
        ↓
ResearcherAgent:
  1. search("PyGame documentation collision detection")
  2. scrape_text(top 3 results)
  3. Knowledge synthesis (LLM)
  4. save_fact(synthesis, tags=["pygame", "game-dev"])
  5. Returns result with links
        ↓
CoderAgent uses knowledge for implementation
```

### Collaboration with Other Agents

- **ArchitectAgent** - Provides technical knowledge at project start
- **CoderAgent** - Passes documentation and examples for implementation
- **MemorySkill** - Saves important knowledge to long-term memory
- **ChatAgent** - Answers user questions about facts

## Configuration

```bash
# In .env
# Search mode
AI_MODE=LOCAL               # DuckDuckGo only
AI_MODE=HYBRID              # DuckDuckGo + optionally Google Grounding
AI_MODE=CLOUD               # Google Grounding preference

# Google Grounding (Gemini)
GOOGLE_API_KEY=your_key
HYBRID_CLOUD_PROVIDER=google

# Tavily AI (optional, better results than DuckDuckGo)
TAVILY_API_KEY=your_key

# HuggingFace
ENABLE_HF_INTEGRATION=true
HF_TOKEN=your_token

# GitHub
GITHUB_TOKEN=ghp_your_token
```

## Search Strategies

### 1. DuckDuckGo (Default)
- **Pros**: Free, private, no API limits
- **Cons**: Fewer results than Google, sometimes outdated
- **Use**: LOCAL mode, backup for HYBRID

### 2. Google Grounding (Gemini API)
- **Pros**: Best results, automatic sources, always current
- **Cons**: Requires API key, costs per request
- **Use**: HYBRID/CLOUD mode, factual questions

### 3. Tavily AI (Optional)
- **Pros**: AI-optimized search, higher quality than DDG
- **Cons**: Paid, API limits
- **Use**: Professional deployments

## Metrics and Monitoring

**Key indicators:**
- Number of search queries (per session)
- Average number of sources per response
- Cache usage rate (memory hit rate)
- Search + scraping time (average)
- Google Grounding vs DuckDuckGo ratio (in HYBRID mode)

## Best Practices

1. **Memory cache** - Always save important knowledge to `save_fact()`
2. **Verify sources** - Check publication date (prefer <1 year)
3. **Aggregate knowledge** - Don't copy raw text, synthesize key points
4. **Tag appropriately** - Use consistent tags for easier searching
5. **Google for facts** - Questions about price/news → Google Grounding

## Known Limitations

- DuckDuckGo has rate-limit restrictions (usually not a problem)
- Scraping can fail for JavaScript sites (trafilatura doesn't render JS)
- Google Grounding requires Gemini API (costs)
- No support for paid sources (paywalls, subscriptions)

## See also

- [THE_ARCHITECT.md](THE_ARCHITECT.md) - Planning with knowledge utilization
- [THE_CODER.md](THE_CODER.md) - Implementation based on documentation
- [MEMORY_LAYER_GUIDE.md](../MEMORY_LAYER_GUIDE.md)
- [GOOGLE_SEARCH_GROUNDING_INTEGRATION.md](../GOOGLE_SEARCH_GROUNDING_INTEGRATION.md) - Google Grounding
- [HYBRID_AI_ENGINE.md](HYBRID_AI_ENGINE.md) - LOCAL/HYBRID/CLOUD routing
