# THE RESEARCHER - Knowledge Synthesis & Web Search

## Role

The Researcher Agent is the research expert in the Venom system, specializing in finding and synthesizing knowledge from the Internet. It provides current documentation, code examples, best practices, and information about libraries and tools.

## Responsibilities

- **Information Search** - Finding current data on the Internet (DuckDuckGo, Google Grounding)
- **Content Extraction** - Downloading and cleaning text from web pages (trafilatura)
- **Knowledge Synthesis** - Aggregating information from multiple sources into coherent response
- **Repository Search** - Finding libraries and tools on GitHub
- **HuggingFace Integration** - Searching for models and datasets
- **Memory Management** - Saving important knowledge to LanceDB

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
# Automatic source addition to responses
response_metadata = {
  "grounding_metadata": {
    "grounding_chunks": [
      {"title": "FastAPI Documentation", "uri": "https://fastapi.tiangolo.com/"},
      {"title": "Pydantic V2", "uri": "https://docs.pydantic.dev/"}
    ],
    "search_queries": ["FastAPI async routes", "Pydantic validators"]
  }
}
```

**Configuration** (`.env`):
```bash
GOOGLE_API_KEY=your_key
HYBRID_CLOUD_PROVIDER=google
HYBRID_CLOUD_MODEL=gemini-1.5-pro
ENABLE_GROUNDING=true
```

📖 **Full documentation:** [GOOGLE_SEARCH_GROUNDING_INTEGRATION.md](GOOGLE_SEARCH_GROUNDING_INTEGRATION.md)

### 3. Workflow

```
User Query
    ↓
Orchestrator detects RESEARCH intent
    ↓
ResearcherAgent activates
    ↓
┌─────────────────────┬─────────────────────┬──────────────────────┐
│  Web Search         │  Repository Search  │  Memory Search       │
├─────────────────────┼─────────────────────┼──────────────────────┤
│  WebSearchSkill     │   GitHubSkill       │   MemorySkill        │
│  search()           │   search_repos()    │   search_memory()    │
│  scrape_text()      │   get_readme()      │                      │
└─────────────────────┴─────────────────────┴──────────────────────┘
    ↓
Knowledge Synthesis
    ↓
Response with sources + optional memory save
```

## Usage Examples

### Example 1: Simple Web Search
```python
from venom_core.agents.researcher import ResearcherAgent

researcher = ResearcherAgent()

# Find current information
result = await researcher.research("What is the current Bitcoin price?")
# Returns: Current price + sources (CoinMarketCap, etc.)
```

### Example 2: Library Search
```python
# Find Python library for async HTTP
result = await researcher.research(
    "Find Python library for async HTTP requests with retry support"
)
# Returns:
# - httpx (recommendation)
# - aiohttp (alternative)
# - Examples from GitHub
# - Documentation links
```

### Example 3: Code Examples
```python
# Find implementation examples
result = await researcher.research(
    "Show me examples of FastAPI WebSocket implementation"
)
# Returns:
# - Code snippets from GitHub
# - Official documentation
# - Tutorial links
# - Best practices
```

### Example 4: With Memory Save
```python
# Research + save to memory
result = await researcher.research(
    "What are best practices for LanceDB indexing?",
    save_to_memory=True
)
# Saves important findings to LanceDB for future use
```

## Configuration

**Environment Variables** (`.env`):
```bash
# Web Search
WEB_SEARCH_MAX_RESULTS=5
WEB_SEARCH_TIMEOUT=30

# GitHub Search
GITHUB_TOKEN=ghp_your_token  # Optional, increases rate limits
GITHUB_MAX_RESULTS=5

# HuggingFace
HF_MAX_RESULTS=5

# Memory
ENABLE_MEMORY=true
LANCEDB_PATH=./data/lancedb
```

## Integration with Other Agents

### With ArchitectAgent
```python
# ArchitectAgent can request research during planning
plan = await architect.create_plan(
    "Build web scraper for news articles"
)
# Architect automatically calls Researcher for:
# - Best scraping libraries
# - Anti-bot techniques
# - Rate limiting patterns
```

### With CoderAgent
```python
# CoderAgent uses research for implementation
code = await coder.generate_code(
    "Create async HTTP client with exponential backoff"
)
# Coder calls Researcher for:
# - Library recommendations (httpx, tenacity)
# - Implementation examples
# - Best practices
```

## Quality Metrics

The Researcher tracks quality metrics:

```python
{
  "sources_found": 5,
  "sources_valid": 4,
  "synthesis_quality": 0.85,
  "response_time_ms": 2340,
  "memory_saved": true
}
```

## Best Practices

### 1. Specific Queries
❌ Bad: "Tell me about Python"
✅ Good: "What are best practices for Python async error handling?"

### 2. Context Inclusion
❌ Bad: "How to do it?"
✅ Good: "How to implement rate limiting in FastAPI endpoints?"

### 3. Source Verification
The Researcher provides sources - always check them:
```python
result = await researcher.research("...")
print(result.sources)  # List of URLs
print(result.confidence)  # 0.0-1.0
```

### 4. Memory Usage
Save important knowledge for reuse:
```python
# Research once
result = await researcher.research(
    "LanceDB indexing best practices",
    save_to_memory=True
)

# Later - retrieve from memory (faster)
cached = await memory_skill.search_memory("LanceDB indexing")
```

## Error Handling

```python
try:
    result = await researcher.research(query)
except WebSearchTimeoutError:
    # Fallback to memory
    result = await memory_skill.search_memory(query)
except NoResultsFoundError:
    # Rephrase query
    result = await researcher.research(rephrased_query)
```

## Troubleshooting

### Problem: No search results
**Solution:**
- Check internet connection
- Verify search engine accessibility (DuckDuckGo might be blocked)
- Try rephrasing query

### Problem: Low-quality results
**Solution:**
- Make query more specific
- Add technical context
- Use technical terminology

### Problem: Rate limiting
**Solution:**
- Set `GITHUB_TOKEN` for higher GitHub limits
- Reduce `MAX_RESULTS` parameters
- Add delays between requests

## Advanced Features

### 1. Multi-source Verification
```python
# Compare information from multiple sources
result = await researcher.research(
    query="Python async frameworks comparison",
    min_sources=3,
    verify_consistency=True
)
```

### 2. Focused Search
```python
# Search only in specific domains
result = await researcher.research(
    query="FastAPI tutorial",
    domains=["fastapi.tiangolo.com", "github.com"]
)
```

### 3. Recursive Research
```python
# Deep research with follow-up queries
result = await researcher.deep_research(
    query="Build production-ready REST API",
    depth=2  # Follow 2 levels of related topics
)
```

## API Reference

### ResearcherAgent Methods

```python
class ResearcherAgent:
    async def research(
        self,
        query: str,
        max_results: int = 5,
        save_to_memory: bool = False
    ) -> ResearchResult:
        """
        Main research method
        
        Args:
            query: Search query
            max_results: Maximum number of results
            save_to_memory: Save findings to LanceDB
            
        Returns:
            ResearchResult with synthesized knowledge and sources
        """
        pass
    
    async def search_repos(
        self,
        query: str,
        language: Optional[str] = None
    ) -> List[Repository]:
        """Search GitHub repositories"""
        pass
    
    async def search_models(
        self,
        query: str,
        task: Optional[str] = None
    ) -> List[Model]:
        """Search HuggingFace models"""
        pass
```

### ResearchResult Model

```python
@dataclass
class ResearchResult:
    answer: str                    # Synthesized answer
    sources: List[Source]          # Source list
    confidence: float              # Confidence 0.0-1.0
    metadata: Dict[str, Any]       # Additional metadata
    memory_id: Optional[str]       # LanceDB ID if saved
```

## Related Documentation

- [WebSearchSkill](../execution/skills/web_skill.py)
- [Google Grounding Integration](GOOGLE_SEARCH_GROUNDING_INTEGRATION.md)
- [Memory Layer](MEMORY_LAYER_GUIDE.md)
- [Orchestrator](../core/flows/orchestrator.py)

---

**Version:** 1.0
**Last Updated:** 2024-12-30
