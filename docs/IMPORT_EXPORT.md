# Import & Export Formats

This guide documents the JSON/YAML formats accepted by Helix's import and export features.

## Test Cases

### Import

**Endpoint:** `POST /api/prompts/{prompt_id}/dataset/import` (file upload)

**Accepted formats:** `.json`, `.yaml`, `.yml`

Two structures are supported:

#### Format A: Array of cases

```json
[
  {
    "name": "Greeting",
    "description": "User greets, expects friendly response",
    "chat_history": [
      { "role": "user", "content": "Hello!" }
    ],
    "variables": {
      "customer_name": "Maria"
    },
    "expected_output": {
      "require_content": true
    },
    "tier": "normal",
    "tags": ["greeting", "basic"]
  }
]
```

#### Format B: Wrapper object

```json
{
  "cases": [
    {
      "name": "Greeting",
      "chat_history": [{ "role": "user", "content": "Hello!" }],
      "variables": {},
      "tier": "normal"
    }
  ]
}
```

#### YAML equivalent

```yaml
- name: Greeting
  description: User greets, expects friendly response
  chat_history:
    - role: user
      content: Hello!
  variables:
    customer_name: Maria
  expected_output:
    require_content: true
  tier: normal
  tags:
    - greeting
    - basic
```

### Test case fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | Human-readable name for the test case |
| `description` | string | No | What this test case validates |
| `chat_history` | array | Yes | Messages array (see format below) |
| `variables` | object | No | Template variable values (key-value pairs). Default: `{}` |
| `tools` | array | No | Tool definitions to include in the LLM call (overrides prompt-level tools) |
| `expected_output` | object | No | Scoring criteria (see below) |
| `tier` | string | No | Priority: `"critical"`, `"normal"` (default), or `"low"` |
| `tags` | array | No | String tags for filtering. Default: `[]` |
| `id` | string | No | UUID — auto-generated if omitted |

### Chat history format

Standard OpenAI message format:

```json
[
  { "role": "user", "content": "I'd like to order a pizza" },
  { "role": "assistant", "content": "Of course! What pizza would you like?" },
  { "role": "user", "content": "A large margherita, deliver to 123 Main St" }
]
```

Supported roles: `"user"`, `"assistant"`, `"system"`.

### Expected output format

The `expected_output` object controls how the test case is scored. All fields are optional:

```json
{
  "require_content": true,
  "must_contain": "human agent",
  "must_not_contain": "I don't know",
  "match_args": {
    "tool_name": "create_order"
  },
  "behavior_criteria": [
    "Must greet the customer by name",
    "Must offer help with orders"
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `require_content` | boolean | Fail if the response contains only tool calls with no spoken text |
| `must_contain` | string | Response must contain this substring (case-insensitive) |
| `must_not_contain` | string | Response must NOT contain this substring |
| `match_args` | object | Require a specific tool call. `tool_name` is required; optional arg matchers |
| `behavior_criteria` | array | Natural language criteria scored by the LLM judge |

### Priority tiers

| Tier | Weight | Behavior |
|------|--------|----------|
| `critical` | Hard constraint | Any failure rejects the candidate entirely |
| `normal` | 1.0x | Standard weighted scoring |
| `low` | 0.5x | Reduced weight in fitness calculation |

---

## Personas

### Export

**Endpoint:** `GET /api/prompts/{prompt_id}/personas/export`

Returns a JSON array of persona profiles:

```json
[
  {
    "id": "confused-customer",
    "role": "Confused customer",
    "traits": ["impatient", "easily confused", "verbose"],
    "communication_style": "Short sentences, many questions",
    "goal": "Trying to place an order but keeps changing their mind",
    "edge_cases": [
      "Asks the same question twice",
      "Provides invalid input"
    ],
    "behavior_criteria": [
      "Must use simple language",
      "Must stay patient"
    ],
    "language": "en",
    "channel": "text"
  }
]
```

### Import

**Endpoint:** `POST /api/prompts/{prompt_id}/personas/import`

**Content-Type:** `application/json`

Send a JSON array of persona objects. Existing personas with the same `id` are skipped.

```json
[
  {
    "id": "angry-caller",
    "role": "Angry customer",
    "traits": ["frustrated", "demanding"],
    "communication_style": "Aggressive, uses caps and exclamation marks",
    "goal": "Wants a refund for a cold delivery"
  }
]
```

### Persona fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier (e.g., `"confused-customer"`) |
| `role` | string | Yes | Short role description |
| `traits` | array | Yes | List of personality traits |
| `communication_style` | string | Yes | How this persona communicates |
| `goal` | string | Yes | What the persona is trying to achieve |
| `edge_cases` | array | No | Tricky behaviors to test. Default: `[]` |
| `behavior_criteria` | array | No | Expected bot behaviors for this persona. Default: `[]` |
| `language` | string | No | Language code. Default: `"en"` |
| `channel` | string | No | Communication channel. Default: `"text"` |

---

## Full example: test case with tool call scoring

```json
[
  {
    "name": "Order placement",
    "description": "Multi-turn order flow expects create_order tool call",
    "chat_history": [
      { "role": "user", "content": "I'd like to order a pizza" },
      { "role": "assistant", "content": "Of course! What pizza would you like?" },
      { "role": "user", "content": "A large margherita to 123 Main St, pay by card" }
    ],
    "variables": {
      "customer_name": "Ana",
      "order_history": ""
    },
    "expected_output": {
      "match_args": {
        "tool_name": "create_order",
        "items": ["margherita"],
        "address": "123 Main St"
      }
    },
    "tier": "critical",
    "tags": ["order", "tool-call", "multi-turn"]
  }
]
```
