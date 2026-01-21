# Ollama LLM Integration

Penguin Overlord now supports optional LLM features powered by local Ollama models!

## Features

### 🤖 Smart Arch Linux Roasts
When enabled, the Arch banter feature uses an LLM to generate contextual, personalized roasts based on:
- What the user actually said
- Their username
- Arch Linux culture and stereotypes

Falls back gracefully to classic regex-based jokes if Ollama is unavailable.

### 💬 Future Enhancements (Coming Soon)
- Smart quote search and recommendations
- Contextual quote insights and explanations
- Conversational tech trivia

## Setup

### 1. Install Ollama

**Linux/Mac:**
```bash
curl https://ollama.ai/install.sh | sh
```

**Manual Installation:**
Download from [ollama.ai](https://ollama.ai)

### 2. Pull a Model

Recommended models (speed vs quality):

```bash
# Fast and lightweight (recommended)
ollama pull gemma2:2b

# Better quality, slower
ollama pull llama3.2:3b

# High quality, needs more resources
ollama pull llama3.1:8b
```

### 3. Enable LLM Features

Add to your `.env` file:

```env
# Enable LLM features (default: false)
ARCH_BANTER_LLM=true

# Ollama model to use (default: gemma2:2b)
OLLAMA_MODEL=gemma2:2b

# Enable Ollama globally (default: true if installed)
OLLAMA_ENABLED=true
```

### 4. Start Ollama

Ollama runs as a background service:

```bash
# Start Ollama
ollama serve

# Or if using systemd
systemctl start ollama
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ARCH_BANTER_LLM` | `false` | Enable LLM-generated Arch roasts |
| `OLLAMA_MODEL` | `gemma2:2b` | Which Ollama model to use |
| `OLLAMA_ENABLED` | `true` | Global Ollama feature toggle |

### Model Recommendations

- **gemma2:2b** (1.6GB) - Fast, good for jokes/roasts ⚡
- **llama3.2:3b** (2GB) - Balanced speed and quality ⚖️
- **llama3.1:8b** (4.7GB) - Best quality, slower 🎯

## Testing

Check if Ollama is working:

```bash
# List available models
ollama list

# Test generation
ollama run gemma2:2b "Say hello"

# Check Ollama is running
curl http://localhost:11434/api/tags
```

## How It Works

1. **Graceful Degradation**: If Ollama isn't available, features automatically fall back to classic behavior
2. **Async Processing**: LLM calls don't block Discord bot - 8-second timeout
3. **Context-Aware**: Uses actual message content to generate relevant responses
4. **No Cloud APIs**: Everything runs locally for privacy

## Example Comparisons

### Classic Mode (Regex)
```
User: "I use Arch btw"
Bot: "@user needs to touch grass! 🌱"
```

### LLM Mode (Contextual)
```
User: "Just spent 6 hours ricing my i3 setup on Arch"
Bot: "@user 6 hours on rice? That's not productivity, that's a lifestyle choice! 🍚✨"
```

## Troubleshooting

**Bot says "Ollama not available":**
- Check Ollama is installed: `ollama --version`
- Check Ollama is running: `curl http://localhost:11434/api/tags`
- Check model is pulled: `ollama list`

**LLM responses are slow:**
- Use a smaller model like `gemma2:2b`
- Check system resources (RAM/CPU)
- Increase timeout in code if needed

**Want to disable LLM:**
- Set `ARCH_BANTER_LLM=false` in `.env`
- Remove `ollama` from `requirements.txt`
- Bot will use classic regex jokes

## Privacy & Performance

- ✅ 100% local processing - no data sent to cloud
- ✅ Opt-in feature - disabled by default
- ✅ Graceful fallback if unavailable
- ✅ Fast response times (<2s typical)
- ✅ Low resource usage with gemma2:2b

## Future Plans

- Quote search with semantic understanding
- Tech trivia with conversational AI
- Custom roast styles per server
- Multi-language support
- Fine-tuned models for tech humor
