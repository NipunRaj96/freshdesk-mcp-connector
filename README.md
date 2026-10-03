# Freshdesk ticket reader for AI agents

This lets an AI agent look up support tickets in Freshdesk. It can search tickets, open one, and read the
conversation on it. It cannot change anything, so it is safe to point at a live help desk.

It follows MCP, a common standard that lets AI agents use outside tools, so any agent that supports MCP
(including Razorpay Agent Studio agents) can plug it in.

## What the agent can do

| Tool | What it does |
|---|---|
| `search_tickets` | Finds tickets that match a condition, such as `status:2 AND priority:>2` (open and more than medium priority). |
| `list_tickets` | Browses tickets, most recently updated first. Can narrow down by customer email or date. |
| `get_ticket` | Reads one ticket: what the customer wrote, who they are, and how quickly it was answered. |
| `list_ticket_conversations` | Reads every reply and internal note on a ticket. |

Two extras that matter for a payments team:

- **Payment ids are picked out for you.** If a customer writes "my payment pay_29QQoUBi66xm2f failed", that id
  is returned in a `razorpay_ids` list, so the agent can go straight to that payment. It recognises payment, order,
  refund, subscription, dispute, settlement, invoice and payment-link ids.
- **Customer text is marked as untrusted.** Every answer carries a reminder that the ticket text was written by a
  customer, so the agent should read it as information and never follow instructions hidden inside it.

The full description of each tool, in the format agents read, is in [`tools.json`](tools.json).

## What the agent cannot do

- Reply to customers, change a ticket, assign it, or delete it. The program only reads. A test checks this.
- See customer profiles, companies, the knowledge base, or attachments. Tickets only.
- See old tickets when browsing. Freshdesk only shows the last 30 days unless you give a date. Searching has no such limit.
- Get more than 300 results from one search. Narrow the search with dates instead.
- Read more than 2,000 characters of any one message. Longer ones are cut and marked.
- Hide internal notes. They are readable but labelled `private: true`. Tell your agent never to repeat those to customers.
  The connector cannot enforce this for you.

## Set it up

You need [uv](https://docs.astral.sh/uv/) (it installs Python for you).

```bash
uv sync
cp .env.example .env     # then fill in your Freshdesk address and key
```

Your Freshdesk key is under your profile picture, then **Profile Settings**, then **View API Key**.
`FRESHDESK_DOMAIN` is just the first part of your Freshdesk address (`acme` for `acme.freshdesk.com`).
Use the key of an agent with only the access you want the AI to have, not an admin.

Run the checks (no Freshdesk account needed):

```bash
uv run pytest -q
```

Start the connector:

```bash
set -a; source .env; set +a
uv run python server.py
```

To hook it up to an agent that reads a config file:

```json
{ "mcpServers": { "freshdesk": {
    "command": "uv",
    "args": ["--directory", "/path/to/this/folder", "run", "python", "server.py"],
    "env": { "FRESHDESK_DOMAIN": "acme", "FRESHDESK_API_KEY": "your-key" } } } }
```

### Trying it without a Freshdesk account

`mock_freshdesk.py` pretends to be Freshdesk on your own computer, with 45 made-up tickets. The only key it accepts is `mock-key`.

```bash
uv run python mock_freshdesk.py --port 8099 --limit 5 --window 10
```

In a second window:

```bash
export FRESHDESK_BASE_URL=http://127.0.0.1:8099/api/v2 FRESHDESK_API_KEY=mock-key
uv run python server.py
```

`--limit 5 --window 10` makes the pretend server say "too many requests" after 5 calls in 10 seconds, so you can watch the
connector slow down and carry on. The pretend server only knows the four things this connector asks for. Its answers follow
Freshdesk's public documentation, but it is not a replacement for trying a real account.

## Signing in

Freshdesk gives each person an API key, and the connector sends it with every request.
The key is read from your environment, never saved in files, and never shown in error messages.
Freshdesk does not offer a "log in with your account" option for this kind of connection, so a key is the way in.

## When Freshdesk says "slow down"

Freshdesk limits how many requests you can make per hour (3,000 to 5,000 depending on the plan). When it replies "too many
requests, wait N seconds", the connector waits that long (never more than a minute) and tries again, up to 3 times.
Short outages and dropped connections are retried the same way, waiting 1, 2, then 4 seconds. If it still fails, the agent gets
a plain message saying so instead of hanging. Every answer also says how many requests are left, so the agent can pace itself.

## Things to know

- One connector talks to one Freshdesk account. A team with many merchants should run one per merchant.
- The agent sees whatever the key's owner can see. Give it the narrowest access that works.
- Ticket text can contain personal details. The connector drops phone numbers from requester info but cannot clean the text customers wrote.

## What I would change before real use

- Keep each merchant's key in a proper secrets store and look it up per request, instead of in the environment.
- Offer merchants a "connect your account" button, so they never have to copy keys around.
- Share the request allowance across agents, because Freshdesk counts it per account, not per program.
- Get told about new tickets as they arrive, instead of asking again and again.
