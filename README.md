# 🤖 Percival Weather - percival.OS MCP

**Version 0.0.2**

[![Python](https://img.shields.io/badge/python-3.10+-yellow.svg)]()
[![MCP](https://img.shields.io/badge/mcp-server-blue.svg)]()
[![percival.OS](https://img.shields.io/badge/percival.OS-ecosystem-orange.svg)](https://github.com/bill-kopp-ai-dev/percival.OS)

## 📋 Description
**Percival Weather** is an MCP server for weather, air quality, and time tools, refactored for practical Nanobot usage and standardized with **FastMCP**.

This server is part of the **percival.OS** ecosystem, a Personal Agentic Operating System designed for autonomy, security, and absolute privacy.

---

## 🛡️ percival.OS Principles
Like all components of `percival.OS`, this MCP server strictly follows our core principles:

- **Privacy & Transparency**: Weather queries are made via open APIs (Open-Meteo) without the need for invasive API keys or tracking.
- **Data Sovereignty**: Your location queries for weather forecasts are processed and presented only to you and your agent.
- **Hardened Security**: Input sanitization and validation (city names, variables, dates) to prevent malicious executions.
- **Transparency**: Based on the `isdaniel/mcp_weather_server` project, but with modernized architecture and deep integration with the Percival ecosystem.

---

## 🚀 Features & Tools

### Weather & Forecast
- `weather_get_current`: Get the current weather for a location.
- `weather_get_by_range`: Query history or forecasts by date range.
- `weather_get_details`: Detailed meteorological information.

### Air Quality
- `weather_get_air_quality`: Current air quality index.
- `weather_get_air_quality_details`: Breakdown of pollutants and metrics.

### Time & Timezone
- `weather_get_time`: Get local time from anywhere in the world.
- `weather_get_timezone`: Identify the timezone of coordinates or cities.
- `weather_convert_time`: Convert times between different timezones.

---

## ⚙️ Configuration in percival.OS (Nanobot)
Add the following configuration to your `~/.nanobot/config.json`:

```json
{
  "tools": {
    "mcpServers": {
      "weather": {
        "command": "/path/to/percival.OS_Dev/.venv/bin/python",
        "args": ["-m", "percival_weather_mcp"],
        "tool_timeout": 45
      }
    }
  }
}
```

---

## 🛠️ Development & Testing
This project uses `uv` for dependency management.

```bash
# Installation in shared environment
uv pip install -e ./mcp_servers/percival-weather-mcp

# Manual execution
uv run -m percival_weather_mcp --mode stdio
```

---

## 📚 About the Project
This server is an integral module of the **percival.OS** project. It provides essential environmental data so that Nanobot can assist in decisions based on weather and time.

- **Main Repository**: [https://github.com/bill-kopp-ai-dev/percival.OS](https://github.com/bill-kopp-ai-dev/percival.OS)
- **License**: MIT

---
*Developed with ❤️ by the percival.OS Team*
